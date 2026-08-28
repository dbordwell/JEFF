"""Render a sample workbook from fixture data, for eyeballing during development.

    uv run python -m ajz.demo [output.xlsx]

Not part of the shipped product — Phase 4 replaces fixtures with the FMP adapter.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from .fixtures import sample_stocks
from .status import RefreshState, RefreshStatus
from .workbook import build_workbook


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "out/AJZ Dashboard.xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)

    stocks = sample_stocks()
    status = RefreshStatus(
        state=RefreshState.OK, data_as_of=datetime(2026, 8, 19, 6, 5)
    )
    build_workbook(stocks, status=status).save(target)

    ranked = [s for s in stocks if s.is_rankable]
    print(f"wrote {target}")
    print(f"  {len(stocks)} stocks, {len(ranked)} rankable")
    for s in sorted(ranked, key=lambda x: -x.ajz_value_score)[:5]:
        print(f"  {s.ticker:6} value={s.ajz_value_score:6.2f}  "
              f"{s.score_label or '—':<14}{s.pe_label or '—':<18}{s.value_label or '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
