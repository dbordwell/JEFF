"""Tests for the FMP adapter.

Field names and shapes here are VERIFIED against live Premium responses probed
2026-08-19 (raw responses in out/probe/). The synthetic values are chosen to make the
arithmetic legible; the field NAMES are real.

Note `freeCashFlowMarginTTM` appears nowhere — the probe confirmed no endpoint reports
FCF margin, so it is derived. An earlier draft of this file assumed that field existed,
which is exactly the guess-instead-of-verify habit that produced v5.1.
"""

from __future__ import annotations

import pytest
import requests

from ajz.calc import UnitsError
from ajz.fmp import (
    FIELD_MAP,
    FMPClient,
    RawBundle,
    make_fetcher,
    map_bundle,
    verify_field_map,
)
from ajz.models import PEBasis
from ajz.refresh import AuthError, FetchError, QuotaError


def bundle(ticker="NVDA", **overrides):
    payloads = {
        "profile": {"companyName": "NVIDIA Corporation", "sector": "Technology",
                    "marketCap": 3.2e12},
        "quote": {"price": 452.30},
        "financial-growth": {"revenueGrowth": 1.142},       # decimal ratio
        # FCF margin is derived: (price / P-FCF) / revenuePerShare.
        # (452.30 / 10.02882) / 100.0 = 45.1%
        "ratios-ttm": {"grossProfitMarginTTM": 0.750,       # decimal ratio
                       "priceToFreeCashFlowRatioTTM": 10.02882,
                       "revenuePerShareTTM": 100.0,
                       "priceToEarningsRatioTTM": 48.2},
        "key-metrics-ttm": {"returnOnInvestedCapitalTTM": 0.902},
        "analyst-estimates": {"epsAvg": 20.0},
    }
    payloads.update(overrides)
    return RawBundle(ticker=ticker, payloads=payloads)


# --- Units: the trap that would have made every stock read "Weak" ---------------------


def test_decimal_ratios_are_converted_to_whole_percent():
    """REGRESSION (spec §5.6): 0.75 must become 75, not stay 0.75.

    Left unconverted, every AJZ Score comes out ~100x too small and the whole dashboard
    reads "Weak" — looking like a data-loading failure rather than a units bug.
    """
    data = map_bundle(bundle())
    assert data.gross_margin == pytest.approx(75.0)
    assert data.fcf_margin == pytest.approx(45.1)
    assert data.roic == pytest.approx(90.2)
    assert data.revenue_growth == pytest.approx(114.2)


def test_conversion_is_deterministic_not_heuristic():
    """Conversion always multiplies by 100 — it never inspects the value to decide.

    An earlier version guessed per value ("looks like a ratio if abs < 1.5"). That is
    unsound in both directions: DDOG's real 0.23% ROIC got rejected as unconverted, and
    a company growing 200% (reported as 2.0) would have been recorded as 2%.
    A convention change is caught by the plausibility sentinel instead — see below.
    """
    from ajz.fmp import _to_percent

    assert _to_percent(0.75) == pytest.approx(75.0)
    assert _to_percent(0.0023252) == pytest.approx(0.23252)
    assert _to_percent(2.0) == pytest.approx(200.0)
    assert _to_percent(None) is None


def test_negative_margins_survive_conversion():
    """Loss-makers are the case v5.1 got wrong; their margins must stay negative."""
    data = map_bundle(bundle("RIVN", **{
        "ratios-ttm": {"grossProfitMarginTTM": -0.18, "freeCashFlowMarginTTM": -0.55},
        "key-metrics-ttm": {"returnOnInvestedCapitalTTM": -0.28},
    }))
    assert data.gross_margin == pytest.approx(-18.0)
    assert data.roic == pytest.approx(-28.0)


def test_units_guard_fires_on_an_unconvertible_value():
    """If normalisation is ever bypassed, the row must fail loudly, not ship."""
    from ajz.fmp import _to_percent

    assert _to_percent(0.75) == 75.0
    with pytest.raises(UnitsError):
        from ajz.calc import assert_whole_percent
        assert_whole_percent("X", gross_margin=0.75)


# --- P/E ladder (spec §5.7) -----------------------------------------------------------


def test_forward_pe_is_computed_from_price_and_consensus_eps():
    data = map_bundle(bundle())
    assert data.pe_ratio == pytest.approx(452.30 / 20.0)
    assert data.pe_basis is PEBasis.FORWARD


def test_falls_back_to_trailing_pe_and_flags_it():
    """Never silently mix forward and trailing — the basis must be recorded."""
    data = map_bundle(bundle(**{"analyst-estimates": {}}))
    assert data.pe_ratio == pytest.approx(48.2)
    assert data.pe_basis is PEBasis.TRAILING


def test_loss_making_company_gets_no_pe_at_all():
    """REGRESSION (v5.1): a negative/zero P/E became 0, which reads as 'Weak'."""
    data = map_bundle(bundle("RIVN", **{
        "analyst-estimates": {"epsAvg": -3.2},
        "ratios-ttm": {"grossProfitMarginTTM": -0.18, "priceToEarningsRatioTTM": -12.0},
    }))
    assert data.pe_ratio is None
    assert data.pe_basis is None


def test_missing_price_does_not_produce_a_bogus_pe():
    data = map_bundle(bundle(**{"quote": {}, "ratios-ttm": {}}))
    assert data.pe_ratio is None


# --- Field mapping resilience ---------------------------------------------------------


def test_alternate_field_names_are_accepted():
    """FMP has renamed fields across versions; a rename must not silently yield None."""
    data = map_bundle(bundle(**{
        "profile": {"name": "NVIDIA", "sector": "Technology", "mktCap": 1.0},
        "key-metrics-ttm": {"roicTTM": 0.902},
    }))
    assert data.company == "NVIDIA"
    assert data.roic == pytest.approx(90.2)


def test_verify_field_map_reports_which_key_matched():
    found = verify_field_map(bundle())
    assert found["gross_margin"] == "grossProfitMarginTTM"
    assert found["roic"] == "returnOnInvestedCapitalTTM"


def test_verify_field_map_reports_none_for_a_missing_field():
    """A None here means the dashboard would look loaded but read wrong."""
    found = verify_field_map(bundle(**{"key-metrics-ttm": {}}))
    assert found["roic"] is None


def test_missing_endpoint_yields_none_not_zero():
    data = map_bundle(RawBundle(ticker="X", payloads={}))
    assert data.gross_margin is None
    assert data.roic is None
    assert data.pe_ratio is None


# --- HTTP error typing ----------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        response = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


def client(session):
    return FMPClient("secret-key", session=session, sleep=lambda _: None)


def test_401_becomes_an_auth_error():
    with pytest.raises(AuthError):
        client(FakeSession(FakeResponse(401))).get("profile", "NVDA")


def test_403_is_treated_as_auth_or_plan_gating():
    with pytest.raises(AuthError, match="plan"):
        client(FakeSession(FakeResponse(403))).get("analyst-estimates", "NVDA")


def test_429_becomes_a_quota_error():
    with pytest.raises(QuotaError):
        client(FakeSession(FakeResponse(429))).get("profile", "NVDA")


def test_server_errors_are_retried_then_give_up():
    session = FakeSession(FakeResponse(503))
    with pytest.raises(FetchError):
        client(session).get("profile", "NVDA")
    assert session.calls == 3


def test_transient_failure_then_success():
    session = FakeSession(
        requests.ConnectionError("boom"),
        FakeResponse(200, [{"companyName": "NVIDIA"}]),
    )
    assert client(session).get("profile", "NVDA") == {"companyName": "NVIDIA"}


def test_api_key_is_never_leaked_in_an_error_message():
    """Keys travel in query strings here; a leaked log is a leaked key."""
    with pytest.raises(FetchError) as exc:
        client(FakeSession(FakeResponse(418, text="teapot"))).get("profile", "NVDA")
    assert "secret-key" not in str(exc.value)


def test_empty_list_response_is_none_not_an_error():
    assert client(FakeSession(FakeResponse(200, []))).get("profile", "NOPE") is None


# --- Fetcher behaviour ----------------------------------------------------------------


def test_one_bad_ticker_does_not_fail_the_whole_refresh():
    """A single delisted symbol must not cost Jeff his morning refresh."""
    class Mixed:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None):
            self.calls += 1
            if params.get("symbol") == "BAD":
                return FakeResponse(404, text="not found")
            return FakeResponse(200, [{"companyName": "Good Co", "price": 10.0}])

    result = make_fetcher("k", session=Mixed())(["GOOD", "BAD"])
    assert "BAD" in result.missing
    assert [s.ticker for s in result.stocks] == ["GOOD"]


def test_auth_error_aborts_the_whole_fetch():
    """Global failures must propagate; retrying per-ticker just burns the quota."""
    with pytest.raises(AuthError):
        make_fetcher("k", session=FakeSession(FakeResponse(401)))(["A", "B"])


# --- The verification gate ------------------------------------------------------------


@pytest.mark.skip(reason="Enable after running `uv run python -m ajz.probe` with a live key")
def test_field_map_is_verified_against_live_responses():
    """Phase 0 gate (spec §5.4): every contract field must resolve against real data.

    Deliberately skipped until the probe has run. Un-skip it, point it at the recorded
    responses in out/probe/, and it becomes the regression test that stops a future FMP
    rename from silently emptying the dashboard.
    """
    import json
    from pathlib import Path

    recorded = json.loads(Path("out/probe/NVDA.json").read_text())
    found = verify_field_map(RawBundle(ticker="NVDA", payloads=recorded))
    unmapped = [field for field, key in found.items() if key is None]
    assert unmapped == [], f"unmapped contract fields: {unmapped}"


# --- Verified against live probe data (2026-08-19) ------------------------------------
# The three findings from `uv run python -m ajz.probe`. Each of these would have shipped
# a plausible-looking but wrong dashboard.

from datetime import date

from ajz.fmp import derive_fcf_margin, pick_forward_estimate

# Real NVDA rows, newest-first exactly as FMP returned them.
NVDA_ESTIMATES = [
    {"date": "2031-01-25", "epsAvg": 20, "numAnalystsEps": 12},
    {"date": "2030-01-25", "epsAvg": 12.29, "numAnalystsEps": 11},
    {"date": "2029-01-25", "epsAvg": 15.3216, "numAnalystsEps": 16},
    {"date": "2028-01-25", "epsAvg": 12.77625, "numAnalystsEps": 30},
    {"date": "2027-01-25", "epsAvg": 8.99738, "numAnalystsEps": 32},
    {"date": "2026-01-25", "epsAvg": 4.69388, "numAnalystsEps": 30},
    {"date": "2025-01-26", "epsAvg": 2.95192, "numAnalystsEps": 33},
]

TODAY = date(2026, 8, 19)


def test_forward_estimate_picks_next_fiscal_year_not_the_furthest_out():
    """REGRESSION: FMP returns estimates furthest-future first and ignores sort=asc.

    Taking row 0 gave NVDA the FY2031 estimate (epsAvg 20) -> forward P/E 10.9 instead
    of 24.2. Nothing looks broken; NVDA just sits at rank 1 forever.
    """
    chosen = pick_forward_estimate(NVDA_ESTIMATES, TODAY)
    assert chosen["date"] == "2027-01-25"
    assert chosen["epsAvg"] == pytest.approx(8.99738)


def test_forward_estimate_ignores_years_already_past():
    """FY2026 ended 2026-01-25, before today, so it is history not a forecast."""
    chosen = pick_forward_estimate(NVDA_ESTIMATES, TODAY)
    assert date.fromisoformat(chosen["date"]) > TODAY


def test_forward_pe_from_real_nvda_data_is_sane():
    data = map_bundle(bundle(**{
        "quote": {"price": 217.56},
        "analyst-estimates": pick_forward_estimate(NVDA_ESTIMATES, TODAY),
    }))
    assert data.pe_ratio == pytest.approx(24.18, abs=0.05)
    assert data.pe_basis is PEBasis.FORWARD


def test_no_future_estimate_falls_back_rather_than_using_a_stale_one():
    past_only = [r for r in NVDA_ESTIMATES if r["date"] < "2026-01-01"]
    assert pick_forward_estimate(past_only, TODAY) is None


def test_malformed_estimate_dates_are_skipped_not_crashed():
    rows = [{"date": None, "epsAvg": 1}, {"date": "not-a-date", "epsAvg": 2},
            {"date": "2027-01-25", "epsAvg": 8.99738}]
    assert pick_forward_estimate(rows, TODAY)["epsAvg"] == pytest.approx(8.99738)


# --- FCF margin derivation ------------------------------------------------------------


def test_fcf_margin_is_derived_from_ttm_ratios():
    """No endpoint reports FCF margin, so it is computed from price / P-FCF / rev-per-share.

    Real NVDA values: price 217.56, P/FCF 44.2534, revenuePerShareTTM 10.4377.
    """
    margin = derive_fcf_margin({
        "quote": {"price": 217.56},
        "ratios-ttm": {"priceToFreeCashFlowRatioTTM": 44.2534,
                       "revenuePerShareTTM": 10.4377},
    })
    assert margin == pytest.approx(47.1, abs=0.5)


def test_fcf_margin_falls_back_to_annual_statements():
    """Real NVDA FY2026: FCF 96,676M / revenue 215,938M = 44.8%."""
    margin = derive_fcf_margin({
        "cash-flow-statement": {"freeCashFlow": 96_676_000_000},
        "income-statement": {"revenue": 215_938_000_000},
    })
    assert margin == pytest.approx(44.77, abs=0.05)


def test_fcf_margin_handles_negative_free_cash_flow():
    """Loss-makers must produce a negative margin, not None and not zero."""
    margin = derive_fcf_margin({
        "cash-flow-statement": {"freeCashFlow": -1_500_000_000},
        "income-statement": {"revenue": 5_000_000_000},
    })
    assert margin == pytest.approx(-30.0)


def test_fcf_margin_is_none_when_nothing_is_available():
    assert derive_fcf_margin({}) is None


def test_fcf_margin_survives_zero_revenue():
    assert derive_fcf_margin({
        "cash-flow-statement": {"freeCashFlow": 100.0},
        "income-statement": {"revenue": 0},
    }) is None


def test_revenue_growth_uses_the_verified_field_name():
    """VERIFIED: the field is `revenueGrowth`; `growthRevenue` was a guess and is wrong."""
    data = map_bundle(bundle(**{"financial-growth": {"revenueGrowth": 0.654735}}))
    assert data.revenue_growth == pytest.approx(65.47, abs=0.01)


# --- Live-data findings, 2026-08-19 first end-to-end run -------------------------------


def test_tsm_currency_mismatch_uses_the_currency_safe_route():
    """REGRESSION: TSM is an ADR — price in USD, financials in TWD.

    The TTM route divides USD FCF-per-share by TWD revenue-per-share and returns 0.88%
    for a company whose real FCF margin is 28.5%. Statement figures share a currency,
    so their ratio is correct for any listing.
    """
    margin = derive_fcf_margin({
        "profile": {"price": 412.09, "currency": "USD"},
        "quote": {"price": 412.09},
        "ratios-ttm": {"priceToFreeCashFlowRatioTTM": 54.486,
                       "revenuePerShareTTM": 856.25},
        "income-statement": {"revenue": 3_848_510_949_000, "reportedCurrency": "TWD"},
        "cash-flow-statement": {"freeCashFlow": 1_097_584_006_000,
                                "reportedCurrency": "TWD"},
    })
    assert margin == pytest.approx(28.5, abs=0.1)


def test_ttm_route_is_refused_for_a_cross_currency_listing():
    """With no statements available, a USD/TWD mix must yield None rather than nonsense."""
    margin = derive_fcf_margin({
        "profile": {"price": 412.09, "currency": "USD"},
        "quote": {"price": 412.09},
        "ratios-ttm": {"priceToFreeCashFlowRatioTTM": 54.486,
                       "revenuePerShareTTM": 856.25},
        "income-statement": {"reportedCurrency": "TWD"},
    })
    assert margin is None


def test_genuinely_tiny_roic_is_not_rejected():
    """REGRESSION: DDOG's real ROIC is 0.0023 -> 0.233%.

    The old heuristic guard treated any sub-1% value as an unconverted ratio and dropped
    the row. A true value must survive.
    """
    data = map_bundle(bundle("DDOG", **{
        "key-metrics-ttm": {"returnOnInvestedCapitalTTM": 0.0023252},
    }))
    assert data.roic == pytest.approx(0.23252, abs=1e-4)


def test_high_growth_is_not_silently_divided_by_a_hundred():
    """A company growing 200% reports 2.0. The old heuristic recorded that as 2%."""
    data = map_bundle(bundle(**{"financial-growth": {"revenueGrowth": 2.0}}))
    assert data.revenue_growth == pytest.approx(200.0)


def test_a_unit_convention_flip_is_caught_by_the_gross_margin_sentinel():
    """Gross margin cannot exceed 100%, so a doubled conversion is unmistakable."""
    with pytest.raises(UnitsError, match="plausible range"):
        map_bundle(bundle(**{"ratios-ttm": {"grossProfitMarginTTM": 75.0}}))


def test_cross_currency_listing_falls_back_to_trailing_pe():
    """REGRESSION: TSM trades USD, reports TWD, and estimates carry no currency field.

    price 412.09 USD / epsAvg 1100.32 TWD = P/E 0.37 -> AJZ Value 222.66, parking TSM
    at rank 1 ahead of everything. FMP's own trailing P/E (27.24) is correct, so the
    §5.7 ladder drops to it and flags the row.
    """
    data = map_bundle(RawBundle(ticker="TSM", payloads={
        "profile": {"companyName": "TSMC", "currency": "USD", "price": 412.09},
        "quote": {"price": 412.09},
        "analyst-estimates": {"date": "2029-12-31", "epsAvg": 1100.3217},
        "ratios-ttm": {"grossProfitMarginTTM": 0.59,
                       "priceToEarningsRatioTTM": 27.240},
        "key-metrics-ttm": {"returnOnInvestedCapitalTTM": 0.30},
        "financial-growth": {"revenueGrowth": 0.35},
        "income-statement": {"revenue": 3_848_510_949_000, "reportedCurrency": "TWD"},
        "cash-flow-statement": {"freeCashFlow": 1_097_584_006_000,
                                "reportedCurrency": "TWD"},
    }))
    assert data.pe_ratio == pytest.approx(27.240)
    assert data.pe_basis is PEBasis.TRAILING
    assert data.fcf_margin == pytest.approx(28.5, abs=0.1)


def test_same_currency_listing_still_gets_forward_pe():
    """A US company must not be penalised by the cross-currency guard."""
    data = map_bundle(bundle(**{
        "profile": {"companyName": "NVIDIA", "currency": "USD", "sector": "Technology"},
        "income-statement": {"reportedCurrency": "USD"},
    }))
    assert data.pe_basis is PEBasis.FORWARD


def test_unknown_currency_metadata_does_not_block_forward_pe():
    """Most payloads omit currency; absence must not silently downgrade everything."""
    data = map_bundle(bundle())
    assert data.pe_basis is PEBasis.FORWARD
