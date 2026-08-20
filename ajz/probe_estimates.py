"""Probe the analyst-estimates endpoint's ordering (spec §5.7).

    uv run python -m ajz.probe_estimates

Why this exists: the first probe run showed `limit=1` returning a FY2031 estimate for
NVDA — six years out. Used as "forward P/E" that gives 217.56 / 20 = 10.9, which would
make NVDA look permanently, absurdly cheap and pin it at rank 1 forever.

That is the exact failure class this project exists to eliminate: not a crash, but a
plausible number that is badly wrong. So before wiring estimates in, establish exactly
what the endpoint returns and in what order.
"""

from __future__ import annotations

import sys

import requests

from .config import MissingApiKeyError, load_api_key

BASE = "https://financialmodelingprep.com/stable"


def main() -> int:
    try:
        api_key = load_api_key()
    except MissingApiKeyError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    session = requests.Session()

    for ticker in ("NVDA", "ANET", "RIVN"):
        print(f"\n{'=' * 72}\n{ticker}\n{'=' * 72}")

        for label, params in [
            ("limit=20, period=annual", {"limit": 20, "period": "annual"}),
            ("limit=20, annual, sort=asc", {"limit": 20, "period": "annual", "sort": "asc"}),
        ]:
            try:
                response = session.get(
                    f"{BASE}/analyst-estimates",
                    params={"symbol": ticker, "apikey": api_key, **params},
                    timeout=20,
                )
                if response.status_code != 200:
                    print(f"  {label}: HTTP {response.status_code}")
                    continue
                rows = response.json()
            except (requests.RequestException, ValueError) as exc:
                print(f"  {label}: {type(exc).__name__}")
                continue

            if not isinstance(rows, list) or not rows:
                print(f"  {label}: empty")
                continue

            print(f"\n  {label}  -> {len(rows)} rows")
            for row in rows:
                print(f"      {row.get('date')}   epsAvg={row.get('epsAvg')!r:>12}"
                      f"   analysts={row.get('numAnalystsEps')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
