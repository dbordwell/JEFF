"""Phase 0: pin the data contract against live FMP responses (spec §5.4).

    uv run python -m ajz.probe

This is the step whose absence killed v5.1. Copilot wrote instructions referencing
fields and objects it never verified existed — `tblUniverse`, the `API_Key` named range,
and a `/profile` endpoint that does not return a single one of the five AJZ inputs.

So: before writing one line of the adapter, ask the API what it actually returns.

The probe answers three questions in one run:
  1. Which endpoints does this key's tier actually reach?
  2. What are the real field names?
  3. Are ratios decimals (0.75) or whole percent (75)? — the §5.6 units trap.

It prints a report and writes the raw responses to `out/probe/` so field mapping is
done against evidence rather than memory. It never prints the API key.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .config import MissingApiKeyError, load_api_key, redact

BASE = "https://financialmodelingprep.com/stable"
TIMEOUT = 20

# One megacap, one mid-cap, one loss-maker. The loss-maker matters: it is the case that
# produced v5.1's "everything reads Weak" behaviour.
PROBE_TICKERS = sys.argv[1:] or ["NVDA", "ANET", "RIVN"]

# Candidate endpoints. Everything the seven contract fields could plausibly come from;
# the probe reports which exist, which are gated, and what each returns.
ENDPOINTS: list[tuple[str, str, dict[str, Any]]] = [
    ("profile", "profile", {}),
    ("quote", "quote", {}),
    ("key-metrics-ttm", "key-metrics-ttm", {}),
    ("ratios-ttm", "ratios-ttm", {}),
    ("financial-growth", "financial-growth", {"limit": 1, "period": "annual"}),
    ("income-statement", "income-statement", {"limit": 1, "period": "annual"}),
    ("cash-flow-statement", "cash-flow-statement", {"limit": 1, "period": "annual"}),
    ("analyst-estimates", "analyst-estimates", {"limit": 2, "period": "annual"}),
]

# What we are hunting for, and the substrings that betray each one.
WANTED: dict[str, tuple[str, ...]] = {
    "revenue_growth": ("revenuegrowth", "growthrevenue"),
    "gross_margin": ("grossprofitmargin", "grossmargin"),
    "fcf_margin": ("freecashflowmargin", "fcfmargin"),
    "roic": ("returnoninvestedcapital", "roic"),
    "forward_eps": ("epsavg", "estimatedeps", "epsestimated", "netincomeavg"),
    "price": ("price",),
    "market_cap": ("marketcap",),
    "sector": ("sector",),
    "free_cash_flow": ("freecashflow",),
    "revenue": ("revenue",),
}


@dataclass
class EndpointReport:
    name: str
    url: str
    status: int | None = None
    error: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.fields)


def _get(session, endpoint: str, ticker: str, params: dict, api_key: str) -> EndpointReport:
    url = f"{BASE}/{endpoint}"
    display = f"{url}?symbol={ticker}"
    report = EndpointReport(name=endpoint, url=display)
    try:
        response = session.get(
            url, params={"symbol": ticker, "apikey": api_key, **params}, timeout=TIMEOUT
        )
        report.status = response.status_code
        if response.status_code != 200:
            report.error = redact(response.text[:200], api_key)
            return report
        payload = response.json()
    except requests.RequestException as exc:
        report.error = redact(str(exc), api_key)
        return report
    except json.JSONDecodeError as exc:
        report.error = f"response was not JSON: {exc}"
        return report

    record = payload[0] if isinstance(payload, list) and payload else payload
    if isinstance(record, dict):
        report.fields = record
    else:
        report.error = f"unexpected shape: {type(payload).__name__}"
    return report


def _classify_units(value: Any) -> str:
    """Guess whether a ratio arrived as a decimal or as whole percent (spec §5.6)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if value == 0:
        return "zero"
    if -1.5 < value < 1.5:
        return "DECIMAL (needs x100)"
    return "whole percent"


def _find(reports: list[EndpointReport], needles: tuple[str, ...]) -> list[tuple[str, str, Any]]:
    hits: list[tuple[str, str, Any]] = []
    for report in reports:
        for key, value in report.fields.items():
            lowered = key.lower()
            if any(n in lowered for n in needles):
                hits.append((report.name, key, value))
    return hits


def main() -> int:
    try:
        api_key = load_api_key()
    except MissingApiKeyError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    out_dir = Path("out/probe")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    all_reports: dict[str, list[EndpointReport]] = {}

    for ticker in PROBE_TICKERS:
        print(f"\n{'=' * 78}\n{ticker}\n{'=' * 78}")
        reports = [_get(session, ep, ticker, params, api_key) for _, ep, params in ENDPOINTS]
        all_reports[ticker] = reports

        for report in reports:
            if report.ok:
                print(f"  OK       {report.name:24} {len(report.fields):3} fields")
            elif report.status == 403:
                print(f"  GATED    {report.name:24} not available on this plan tier")
            else:
                print(f"  FAILED   {report.name:24} status={report.status} {report.error or ''}")

        (out_dir / f"{ticker}.json").write_text(
            json.dumps({r.name: r.fields for r in reports if r.ok}, indent=2, default=str),
            encoding="utf-8",
        )

    # --- The report that actually decides the adapter's field mapping.
    print(f"\n\n{'=' * 78}\nCONTRACT FIELD MAPPING  (spec §5.5)\n{'=' * 78}")
    nvda = all_reports.get("NVDA", [])
    for wanted, needles in WANTED.items():
        hits = _find(nvda, needles)
        if not hits:
            print(f"\n  {wanted:16} NOT FOUND — needs deriving or another endpoint")
            continue
        print(f"\n  {wanted}")
        for endpoint, key, value in hits[:6]:
            units = _classify_units(value) if wanted.endswith(("margin", "growth", "roic")) else ""
            print(f"      {endpoint:22} {key:42} = {value!r:>16} {units}")

    print(f"\n\nRaw responses written to {out_dir}/")
    print("Next: pin ajz/fmp.py's FIELD_MAP against the names above, not against memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
