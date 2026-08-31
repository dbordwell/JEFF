"""FMP adapter — the only module that knows a data vendor exists (spec §5.3).

Everything above this file speaks the §5.5 contract. Swapping vendors means rewriting
this one file and nothing else.

FIELD_MAP is VERIFIED against live Premium-tier responses (probed 2026-08-19, raw
responses in out/probe/). Three findings from that probe are baked in below:

  1. `analyst-estimates` returns rows FURTHEST-FUTURE FIRST, and ignores `sort=asc`.
     `limit=1` therefore yields a six-year-out estimate. For NVDA that made forward P/E
     read 10.9 instead of 24.2 — a plausible number that is badly wrong, which would
     have pinned NVDA at rank 1 permanently. See `pick_forward_estimate`.
  2. There is no FCF-margin field anywhere. It is derived; see `derive_fcf_margin`.
  3. Revenue growth is `revenueGrowth`, not `growthRevenue`.

Two things this module is strict about:

* **Units.** Providers return margins as decimals (0.75); the AJZ formula wants whole
  percent (75). Normalisation happens HERE, at the boundary, and every value is checked
  by `assert_whole_percent` before it leaves. Nothing downstream ever sees a ratio.
* **Failure typing.** HTTP failures become AuthError / QuotaError / FetchError, each of
  which maps to a plain-English banner. Jeff never sees a status code.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import requests

from .calc import UnitsError
from .config import redact
from .models import PEAbsence, PEBasis, StockData
from .refresh import AuthError, FetchError, FetchResult, QuotaError

log = logging.getLogger(__name__)

BASE = "https://financialmodelingprep.com/stable"
TIMEOUT = 20
MAX_RETRIES = 3
BACKOFF_SECONDS = 2.0

# --- Field mapping --------------------------------------------------------------------
# contract field -> (endpoint, candidate JSON keys in priority order)
#
# Multiple candidates per field on purpose: FMP has renamed fields across API versions,
# and accepting the first key that is present makes the adapter survive a rename instead
# of silently producing None. `verify_field_map()` reports which candidate actually hit.
FIELD_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "company": ("profile", ("companyName", "name")),
    "sector": ("profile", ("sector",)),
    "market_cap": ("profile", ("marketCap", "mktCap")),
    "price": ("quote", ("price",)),
    # VERIFIED: financial-growth.revenueGrowth (decimal, e.g. 0.6547)
    "revenue_growth": ("financial-growth", ("revenueGrowth", "growthRevenue")),
    # VERIFIED: ratios-ttm.grossProfitMarginTTM (decimal, e.g. 0.7415)
    "gross_margin": ("ratios-ttm", ("grossProfitMarginTTM", "grossProfitMargin")),
    # VERIFIED: key-metrics-ttm.returnOnInvestedCapitalTTM (decimal, e.g. 0.6299)
    "roic": ("key-metrics-ttm", ("returnOnInvestedCapitalTTM", "roicTTM")),
    # NOTE: fcf_margin is absent from every endpoint and is DERIVED — see
    # derive_fcf_margin(). It is deliberately not in this map.
    "forward_eps": ("analyst-estimates", ("epsAvg", "estimatedEpsAvg", "epsEstimated")),
}

# Fields that arrive as decimal ratios and must be multiplied by 100.
RATIO_FIELDS = {"revenue_growth", "gross_margin", "roic"}

# Endpoints fetched purely to derive FCF margin.
DERIVATION_ENDPOINTS = ("income-statement", "cash-flow-statement")


@dataclass(frozen=True)
class RawBundle:
    """Every endpoint's response for one ticker, before mapping."""

    ticker: str
    payloads: dict[str, dict[str, Any]]


def _first_present(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _to_percent(value: Any) -> float | None:
    """Convert an FMP decimal ratio to whole-number percent (spec §5.6).

    DETERMINISTIC, not heuristic. An earlier version only multiplied when the value
    "looked like" a ratio (abs < 1.5). Live data killed that idea twice:

      * DDOG's real ROIC is 0.0023 -> 0.23%. The heuristic converted it, then the
        plausibility guard rejected the row as "still a ratio". A true value, dropped.
      * A company growing 200% reports revenueGrowth as 2.0. The heuristic would have
        left it alone and recorded 2% growth instead of 200% — silent, and badly wrong.

    The probe established that FMP returns these fields as decimals, so the adapter
    simply knows its vendor's convention. A convention change is caught by
    `_assert_plausible` (a 75% gross margin arriving as 75 becomes 7500, which is
    impossible) rather than by guessing per value.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


# Sanity bounds in whole percent. These catch a vendor convention flip without
# rejecting genuinely tiny values. Gross margin is the reliable sentinel: it cannot
# exceed 100%, so a doubled conversion shows up immediately.
PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "gross_margin": (-500.0, 100.5),
    "fcf_margin": (-10_000.0, 200.0),
    "roic": (-10_000.0, 10_000.0),
    "revenue_growth": (-100.0, 100_000.0),
}


def _assert_plausible(ticker: str, **fields: float | None) -> None:
    for name, value in fields.items():
        if value is None:
            continue
        low, high = PLAUSIBLE_RANGE.get(name, (-1e9, 1e9))
        if not low <= value <= high:
            raise UnitsError(
                f"{ticker}: {name}={value:.4g}% is outside the plausible range "
                f"[{low}, {high}]. Either the provider changed units or the value is "
                f"bad — refusing to publish it (spec §5.6)."
            )


def pick_forward_estimate(rows: list[dict[str, Any]], today: date | None = None
                          ) -> dict[str, Any] | None:
    """The NEXT fiscal year's estimate — not the furthest-out one.

    FMP returns annual estimates newest-first and ignores `sort=asc`, so naively taking
    the first row yields a five-or-six-year-out projection. For NVDA on 2026-08-19 that
    was FY2031 (epsAvg 20, only 12 analysts) rather than FY2027 (epsAvg 9.00, 32
    analysts) — a forward P/E of 10.9 instead of 24.2.

    Nothing would have looked broken. NVDA would simply have sat at rank 1 forever.
    """
    today = today or date.today()
    future: list[tuple[date, dict[str, Any]]] = []

    for row in rows or []:
        raw = row.get("date")
        if not raw:
            continue
        try:
            when = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if when > today:
            future.append((when, row))

    if not future:
        return None
    future.sort(key=lambda pair: pair[0])
    return future[0][1]  # nearest future fiscal year end


def derive_fcf_margin(payloads: dict[str, dict[str, Any]]) -> float | None:
    """FCF margin as whole percent. No endpoint provides it, so it is computed.

    ANNUAL STATEMENTS ARE PRIMARY, and the reason is currency.

    Foreign ADRs report financials in their local currency while their price is quoted
    in USD. TSM is the live example that caught this: price 412.09 USD,
    revenuePerShareTTM 856.25 TWD, reportedCurrency "TWD". The TTM route divides a
    USD-based FCF-per-share by a TWD revenue-per-share and yields 0.88% — for a company
    whose real FCF margin is 28.5%.

    Free cash flow and revenue from the statement pair are BOTH in reportedCurrency, so
    the ratio cancels currency entirely and is correct for any listing. The TTM route
    survives only as a fallback for when statements are unavailable.

      1. Annual: cash-flow-statement.freeCashFlow / income-statement.revenue  [currency-safe]
      2. TTM:    (price / priceToFreeCashFlowRatioTTM) / revenuePerShareTTM   [USD-only]
    """
    cash_flow = payloads.get("cash-flow-statement") or {}
    income = payloads.get("income-statement") or {}
    free_cash_flow = _as_float(cash_flow.get("freeCashFlow"))
    revenue = _as_float(income.get("revenue"))

    if free_cash_flow is not None and revenue:
        # Same-statement currencies must agree, or the ratio is meaningless.
        cf_currency = cash_flow.get("reportedCurrency")
        is_currency = income.get("reportedCurrency")
        if not cf_currency or not is_currency or cf_currency == is_currency:
            return (free_cash_flow / revenue) * 100.0

    ratios = payloads.get("ratios-ttm") or {}
    quote = payloads.get("quote") or {}
    profile = payloads.get("profile") or {}

    # Only safe when the company reports in the same currency it trades in.
    reported = income.get("reportedCurrency") or cash_flow.get("reportedCurrency")
    traded = profile.get("currency")
    if reported and traded and reported != traded:
        log.warning("skipping TTM FCF route for a cross-currency listing "
                    "(reports %s, trades %s)", reported, traded)
        return None

    price = _as_float(quote.get("price") or profile.get("price"))
    p_fcf = _as_float(ratios.get("priceToFreeCashFlowRatioTTM"))
    revenue_per_share = _as_float(ratios.get("revenuePerShareTTM"))

    if price and p_fcf and revenue_per_share:
        return ((price / p_fcf) / revenue_per_share) * 100.0

    return None


def map_bundle(bundle: RawBundle, as_of: date | None = None) -> StockData:
    """Turn raw endpoint payloads into one §5.5 contract record."""
    values: dict[str, Any] = {}
    for contract_field, (endpoint, candidates) in FIELD_MAP.items():
        record = bundle.payloads.get(endpoint) or {}
        values[contract_field] = _first_present(record, candidates)

    for name in RATIO_FIELDS:
        values[name] = _to_percent(values.get(name))

    # Not in FIELD_MAP: no endpoint reports it (verified by probe).
    values["fcf_margin"] = derive_fcf_margin(bundle.payloads)

    # Forward P/E from price and consensus next-year EPS. Falls back per §5.7 rather
    # than emitting 0, which is what made every v5.1 row read "Weak".
    price = values.get("price")
    forward_eps = values.get("forward_eps")
    pe_ratio, pe_basis, pe_absence = _resolve_pe(price, forward_eps, bundle)

    data = StockData(
        ticker=bundle.ticker,
        company=values.get("company"),
        sector=values.get("sector"),
        market_cap=_as_float(values.get("market_cap")),
        price=_as_float(price),
        revenue_growth=values.get("revenue_growth"),
        gross_margin=values.get("gross_margin"),
        fcf_margin=values.get("fcf_margin"),
        roic=values.get("roic"),
        pe_ratio=pe_ratio,
        pe_basis=pe_basis,
        pe_absence=pe_absence,
        as_of=as_of or date.today(),
        source="fmp",
    )

    # Belt and braces: the guard runs on every row, so a units regression fails loudly
    # at the boundary instead of quietly producing a dashboard of "Weak".
    try:
        _assert_plausible(
            data.ticker,
            revenue_growth=data.revenue_growth,
            gross_margin=data.gross_margin,
            fcf_margin=data.fcf_margin,
            roic=data.roic,
        )
    except UnitsError as exc:
        log.warning("%s", exc)
        raise

    return data


def _reports_in_trading_currency(bundle: RawBundle) -> bool:
    """Whether the company reports financials in the currency it trades in.

    False for foreign ADRs. TSM trades in USD but reports in TWD, and
    `analyst-estimates` carries NO currency field — its epsAvg of 1100.32 is TWD while
    price is 412.09 USD. Dividing them gave a P/E of 0.77 and an AJZ Value Score of
    222.66, which parked TSM at rank 1 ahead of everything else.
    """
    income = bundle.payloads.get("income-statement") or {}
    cash_flow = bundle.payloads.get("cash-flow-statement") or {}
    profile = bundle.payloads.get("profile") or {}

    reported = income.get("reportedCurrency") or cash_flow.get("reportedCurrency")
    traded = profile.get("currency")
    if not reported or not traded:
        return True  # unknown: assume consistent, and let the ratio sanity check catch it
    return str(reported).upper() == str(traded).upper()


def _resolve_pe(price: Any, forward_eps: Any, bundle: RawBundle
                ) -> tuple[float | None, PEBasis | None, PEAbsence | None]:
    """P/E fallback ladder (spec §5.7). Never returns 0.

    The third element records WHY there is no P/E when there is none, because the two
    causes send a stock to different places in Jeff's head. An estimate that exists and
    is negative means the company is not expected to earn anything next year. No
    estimate at all means nobody is covering the symbol -- which is also what a ticker
    that does not exist looks like from here.
    """
    price_value = _as_float(price)
    eps_value = _as_float(forward_eps)

    # Forward P/E requires price and EPS in the SAME currency. For cross-currency
    # listings we cannot compute it without an FX rate, so we drop to trailing — which
    # FMP computes correctly (TSM: 27.24). Guessing an FX rate would be worse than
    # honestly showing a flagged trailing figure.
    if price_value and eps_value and eps_value > 0 and _reports_in_trading_currency(bundle):
        return price_value / eps_value, PEBasis.FORWARD, None

    # No usable forward estimate -> trailing P/E, explicitly flagged so the workbook can
    # show it. Forward and trailing must never be silently mixed.
    ratios = bundle.payloads.get("ratios-ttm") or {}
    trailing = _as_float(_first_present(ratios, ("priceToEarningsRatioTTM", "peRatioTTM")))
    if trailing and trailing > 0:
        return trailing, PEBasis.TRAILING, None

    # Nothing usable. Distinguish "the estimate says it will lose money" from "there is
    # no estimate", and treat a zero or negative trailing P/E as corroborating the
    # former -- a company already losing money, with no positive projection, is the
    # pre-profit case rather than an uncovered one.
    if eps_value is not None and eps_value <= 0:
        return None, None, PEAbsence.NOT_PROFITABLE
    if trailing is not None and trailing <= 0:
        return None, None, PEAbsence.NOT_PROFITABLE
    return None, None, PEAbsence.NO_ESTIMATE


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --- HTTP ------------------------------------------------------------------------------


class FMPClient:
    """Thin HTTP client with typed failures and retry on transient errors."""

    def __init__(self, api_key: str, session: requests.Session | None = None,
                 base: str = BASE, sleep=time.sleep):
        self._api_key = api_key
        self._session = session or requests.Session()
        self._base = base
        self._sleep = sleep

    def get(self, endpoint: str, ticker: str, **params: Any) -> dict[str, Any] | None:
        """One endpoint for one ticker. Returns the first record, or None if empty."""
        url = f"{self._base}/{endpoint}"
        query = {"symbol": ticker, "apikey": self._api_key, **params}

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._session.get(url, params=query, timeout=TIMEOUT)
            except requests.RequestException as exc:
                last_error = exc
                self._sleep(BACKOFF_SECONDS * (attempt + 1))
                continue

            if response.status_code in (401, 403):
                raise AuthError(
                    f"FMP rejected the API key or the plan does not include "
                    f"{endpoint} (HTTP {response.status_code})."
                )
            if response.status_code == 429:
                raise QuotaError("FMP request limit reached (HTTP 429).")
            if response.status_code >= 500:
                last_error = FetchError(f"FMP server error {response.status_code}")
                self._sleep(BACKOFF_SECONDS * (attempt + 1))
                continue
            if response.status_code != 200:
                raise FetchError(
                    redact(f"FMP returned HTTP {response.status_code} for {endpoint}",
                           self._api_key)
                )

            payload = response.json()
            if isinstance(payload, list):
                return payload[0] if payload else None
            return payload if isinstance(payload, dict) else None

        raise FetchError(
            redact(f"Could not reach FMP after {MAX_RETRIES} attempts: {last_error}",
                   self._api_key)
        )

    def get_list(self, endpoint: str, ticker: str, **params: Any) -> list[dict[str, Any]]:
        """Full list response. Needed for estimates, where row ORDER is the whole problem."""
        url = f"{self._base}/{endpoint}"
        query = {"symbol": ticker, "apikey": self._api_key, **params}
        response = self._session.get(url, params=query, timeout=TIMEOUT)
        if response.status_code in (401, 403):
            raise AuthError(f"FMP rejected the key or gated {endpoint}.")
        if response.status_code == 429:
            raise QuotaError("FMP request limit reached (HTTP 429).")
        if response.status_code != 200:
            raise FetchError(
                redact(f"FMP returned HTTP {response.status_code} for {endpoint}",
                       self._api_key)
            )
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def bundle(self, ticker: str, today: date | None = None) -> RawBundle:
        """Fetch every endpoint the contract needs for one ticker."""
        endpoints = {endpoint for endpoint, _ in FIELD_MAP.values()}
        endpoints.discard("analyst-estimates")  # handled separately, see below
        endpoints.update(DERIVATION_ENDPOINTS)

        payloads: dict[str, dict[str, Any]] = {}
        for endpoint in sorted(endpoints):
            extra: dict[str, Any] = {}
            if endpoint in {"financial-growth", *DERIVATION_ENDPOINTS}:
                extra = {"limit": 1, "period": "annual"}
            record = self.get(endpoint, ticker, **extra)
            if record:
                payloads[endpoint] = record

        # Estimates need the full list so the NEXT fiscal year can be selected. Taking
        # row 0 here would silently produce a years-out forward P/E.
        rows = self.get_list("analyst-estimates", ticker, limit=12, period="annual")
        chosen = pick_forward_estimate(rows, today)
        if chosen:
            payloads["analyst-estimates"] = chosen

        return RawBundle(ticker=ticker, payloads=payloads)


def make_fetcher(api_key: str, session: requests.Session | None = None):
    """Build a `Fetcher` for `refresh()`.

    A ticker that fails individually is reported as missing rather than failing the whole
    run — one delisted symbol must not cost Jeff his morning refresh. Auth and quota
    errors DO propagate, because those are global and retrying per-ticker just burns
    what is left of the quota.
    """
    client = FMPClient(api_key, session=session)

    def fetch(tickers: list[str]) -> FetchResult:
        stocks: list[StockData] = []
        missing: list[str] = []
        for ticker in tickers:
            try:
                bundle = client.bundle(ticker)
                if not bundle.payloads:
                    missing.append(ticker)
                    continue
                stocks.append(map_bundle(bundle))
            except (AuthError, QuotaError):
                raise
            except (FetchError, UnitsError) as exc:
                log.warning("skipping %s: %s", ticker, exc)
                missing.append(ticker)
        return FetchResult(stocks=stocks, missing=tuple(missing))

    return fetch


def verify_field_map(bundle: RawBundle) -> dict[str, str | None]:
    """Which candidate key actually matched, per contract field.

    Run this against a live bundle after probing. A None means the adapter is silently
    producing no data for that field — the exact failure mode that makes a dashboard
    look loaded but read wrong.
    """
    found: dict[str, str | None] = {}
    for contract_field, (endpoint, candidates) in FIELD_MAP.items():
        record = bundle.payloads.get(endpoint) or {}
        found[contract_field] = next(
            (key for key in candidates if key in record and record[key] is not None), None
        )
    return found
