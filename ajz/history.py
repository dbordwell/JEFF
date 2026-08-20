"""Weekly snapshot store (spec §8).

Excel formulas fundamentally cannot snapshot themselves — a cell cannot remember what it
said last week. That is why v5.1's `AJZ_History`, `Rank_Movers`, and the Upgrade Alert
column were all permanently empty: they were specified as formulas, and no formula can
do this job.

History therefore lives OUTSIDE the workbook, in SQLite. Two consequences that matter:

* Regenerating the workbook can never destroy history.
* If Jeff deletes or moves the workbook, his history survives.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .models import ScoredStock

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date   TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    ajz_score       REAL,
    ajz_value_score REAL,
    conviction      INTEGER,
    rank            INTEGER,
    category        TEXT,
    PRIMARY KEY (snapshot_date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON snapshots(ticker, snapshot_date);
"""


@dataclass(frozen=True)
class RankChange:
    ticker: str
    current_rank: int
    previous_rank: int | None

    @property
    def change(self) -> int | None:
        """Positive means improved. Rank 8 -> 3 is +5."""
        if self.previous_rank is None:
            return None
        return self.previous_rank - self.current_rank

    @property
    def is_new(self) -> bool:
        return self.previous_rank is None


class History:
    """SQLite-backed snapshot store. Safe to construct against a non-existent file."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record_snapshot(self, ranked: list[ScoredStock], when: date) -> int:
        """Store one weekly snapshot.

        Idempotent by (date, ticker): re-running a refresh on the same day overwrites
        rather than duplicating, so a manual re-run cannot corrupt the series.
        """
        rows = [
            (
                when.isoformat(),
                s.ticker,
                s.ajz_score,
                s.ajz_value_score,
                s.conviction_score,
                position,
                s.category.value,
            )
            for position, s in enumerate(ranked, start=1)
        ]
        if not rows:
            return 0

        with closing(self._connect()) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO snapshots "
                "(snapshot_date, ticker, ajz_score, ajz_value_score, conviction, "
                " rank, category) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def snapshot_dates(self) -> list[date]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT DISTINCT snapshot_date FROM snapshots ORDER BY snapshot_date DESC"
            )
            return [date.fromisoformat(r[0]) for r in cur.fetchall()]

    def previous_ranks(self, before: date) -> dict[str, int]:
        """Ranks from the most recent snapshot strictly before `before`.

        Returns {} when there is no prior snapshot — the first-run case, which is normal
        and must not be treated as "everything moved".
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT snapshot_date FROM snapshots WHERE snapshot_date < ? "
                "ORDER BY snapshot_date DESC LIMIT 1",
                (before.isoformat(),),
            )
            row = cur.fetchone()
            if row is None:
                return {}
            cur = conn.execute(
                "SELECT ticker, rank FROM snapshots WHERE snapshot_date = ?", (row[0],)
            )
            return {ticker: rank for ticker, rank in cur.fetchall()}

    def rank_changes(self, ranked: list[ScoredStock], when: date) -> list[RankChange]:
        """Rank movement for each currently-ranked stock versus the prior snapshot."""
        previous = self.previous_ranks(when)
        return [
            RankChange(
                ticker=s.ticker,
                current_rank=position,
                previous_rank=previous.get(s.ticker),
            )
            for position, s in enumerate(ranked, start=1)
        ]

    def movers(self, ranked: list[ScoredStock], when: date, threshold: int = 5
               ) -> tuple[list[RankChange], list[RankChange]]:
        """(upgrades, downgrades) — moves of at least `threshold` places.

        New entries are excluded from both. A stock appearing for the first time has not
        "moved"; treating it as a huge upgrade would make every first run a wall of
        alerts, which is how an alert system teaches people to ignore it.
        """
        changes = [c for c in self.rank_changes(ranked, when) if not c.is_new]
        upgrades = sorted(
            [c for c in changes if c.change >= threshold],
            key=lambda c: -c.change,
        )
        downgrades = sorted(
            [c for c in changes if c.change <= -threshold],
            key=lambda c: c.change,
        )
        return upgrades, downgrades
