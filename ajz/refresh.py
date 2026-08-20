"""The refresh orchestration — the sequence that runs once a day (spec §3).

    read existing  ->  back up  ->  fetch  ->  score  ->  snapshot  ->  write

Ordering is a safety property, not a style choice. Conviction is read and backed up
BEFORE anything can fail, so no failure downstream can cost Jeff his scores. If the read
fails we abort having written nothing.

The data source is injected as `fetch`, so this whole path is testable without a network
and the FMP adapter (Phase 4) drops in without touching this file.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Protocol

from .calc import rank_stocks, score_stock
from .history import History
from .models import Conviction, ScoredStock, StockData
from .settings import Thresholds, from_mapping
from .status import RefreshState, RefreshStatus
from .store import (
    ConvictionReadError,
    UniverseEntry,
    WorkbookLockedError,
    atomic_save,
    backup_workbook,
    read_existing,
)
from .workbook import build_workbook


class FetchError(RuntimeError):
    """Base for data-source failures. Each maps to a banner state, never to a crash."""

    state = RefreshState.STALE


class AuthError(FetchError):
    state = RefreshState.AUTH_ERROR


class QuotaError(FetchError):
    state = RefreshState.QUOTA


@dataclass(frozen=True)
class FetchResult:
    stocks: list[StockData]
    missing: tuple[str, ...] = ()


class Fetcher(Protocol):
    def __call__(self, tickers: list[str]) -> FetchResult: ...


@dataclass(frozen=True)
class RefreshOutcome:
    status: RefreshStatus
    stocks: list[ScoredStock]
    written: bool
    backup: Path | None = None
    warnings: tuple[str, ...] = ()

    @property
    def ranked(self) -> list[ScoredStock]:
        return rank_stocks(self.stocks)


def refresh(
    workbook_path: Path,
    fetch: Fetcher,
    *,
    history_path: Path,
    backup_dir: Path,
    seed_universe: list[UniverseEntry] | None = None,
    seed_conviction: dict[str, Conviction] | None = None,
    now: datetime | None = None,
    snapshot: bool = True,
) -> RefreshOutcome:
    """Run one refresh. Raises only for conditions where writing would lose data."""
    now = now or datetime.now()
    today = now.date()

    # Seeds apply ONLY on a genuine first run. Once the workbook exists, it is the
    # system of record and Jeff's edits are absolute — including a deliberately CLEARED
    # score. A seed that refilled gaps on every run would make un-scoring impossible,
    # which is a worse bug than an empty first run.
    is_first_run = not workbook_path.exists()

    # 1. Read Jeff's data first. A failure here is fatal by design: if we cannot prove
    #    what he had, we must not overwrite it. This propagates to the caller.
    saved = read_existing(workbook_path)
    warnings = list(saved.warnings)

    # 2. Back it up before anything else can go wrong.
    backup = backup_workbook(workbook_path, backup_dir, now)

    # 3. Decide the universe. Jeff's edited sheet wins; the seed is only for first run.
    universe = saved.universe or list(seed_universe or [])
    tickers = [e.ticker for e in universe if e.active]
    if not tickers:
        raise ValueError(
            "No active tickers. Add at least one to the Universe sheet before refreshing."
        )

    # 4. Fetch. Any failure degrades to a labelled stale workbook rather than an error
    #    dialog — but only if we already have something to show.
    state = RefreshState.OK
    missing: tuple[str, ...] = ()
    try:
        result = fetch(tickers)
        fetched = result.stocks
        missing = result.missing
        if missing:
            state = RefreshState.PARTIAL
    except FetchError as exc:
        state = exc.state
        fetched = []
        warnings.append(f"fetch failed: {exc}")

    if not fetched:
        # Nothing new to show. Leave the existing workbook exactly as it is rather than
        # rewriting it with empty data — stale-but-intact beats fresh-but-blank.
        return RefreshOutcome(
            status=RefreshStatus(state=state if state is not RefreshState.OK
                                 else RefreshState.STALE, data_as_of=None),
            stocks=[],
            written=False,
            backup=backup,
            warnings=tuple(warnings),
        )

    # 5. Score, carrying Jeff's conviction forward by ticker.
    #
    #    `seed_conviction` fills in scores ONLY for stocks the workbook has never held.
    #    Without it, the very first run renders every stock as "Needs Conviction" and
    #    Jeff opens an empty grid — exactly the failure v5.1 handed him. His own chats
    #    already contain worked scores (NVDA 24, TSM 25, AVGO 23...), so shipping those
    #    pre-filled means his first open is immediately useful.
    #
    #    Anything he has since typed always wins: saved data is never overwritten by a
    #    seed, only absent data is filled.
    conviction_by_ticker = dict(seed_conviction or {}) if is_first_run else {}
    conviction_by_ticker.update(saved.conviction)

    # Jeff's threshold edits, read back from the Settings sheet (spec §6.5). Bad input
    # falls back to that field's default with a warning rather than stopping the
    # refresh — a dashboard using one default beats no dashboard.
    thresholds, threshold_warnings = from_mapping(saved.settings)
    warnings.extend(threshold_warnings)

    scored = [
        score_stock(data, conviction_by_ticker.get(data.ticker, Conviction()),
                    thresholds=thresholds)
        for data in fetched
    ]

    # 6. Snapshot, then fold rank movement back into the alerts.
    history = History(history_path)
    ranked = rank_stocks(scored)
    scored = _apply_rank_changes(scored, ranked, history, today, thresholds)
    if snapshot:
        history.record_snapshot(rank_stocks(scored), today)

    status = RefreshStatus(state=state, data_as_of=now, missing_tickers=missing)

    # 7. Write atomically. A locked file aborts cleanly, leaving the good copy in place.
    atomic_save(build_workbook(scored, status=status, thresholds=thresholds),
                workbook_path)

    return RefreshOutcome(
        status=status, stocks=scored, written=True, backup=backup,
        warnings=tuple(warnings),
    )


def _apply_rank_changes(
    scored: list[ScoredStock],
    ranked: list[ScoredStock],
    history: History,
    today: date,
    thresholds: Thresholds,
) -> list[ScoredStock]:
    """Re-score ranked stocks with their rank movement, so UPGRADE/DOWNGRADE can fire.

    This is the piece v5.1 could not have: its Upgrade Alert column was empty because
    the information simply did not exist anywhere in the workbook.
    """
    changes = {c.ticker: c for c in history.rank_changes(ranked, today)}
    positions = {s.ticker: i for i, s in enumerate(ranked, start=1)}

    out: list[ScoredStock] = []
    for s in scored:
        change = changes.get(s.ticker)
        if change is None or change.change is None:
            out.append(s)
            continue
        rescored = score_stock(
            s.data,
            s.conviction,
            rank_change=change.change,
            entered_top_10=(positions.get(s.ticker, 999) <= 10
                            and (change.previous_rank or 999) > 10),
            thresholds=thresholds,
        )
        out.append(rescored)
    return out


def make_seed_universe(entries: list[tuple[str, str, str]]) -> list[UniverseEntry]:
    """Build a starting universe from (ticker, company, sector) triples."""
    return [UniverseEntry(ticker=t, company=c, sector=s) for t, c, s in entries]


def fetcher_from_fixtures() -> Callable[[list[str]], FetchResult]:
    """A Fetcher backed by the sample data, for end-to-end tests and demos."""
    from .fixtures import sample_stocks

    catalogue = {s.data.ticker: s.data for s in sample_stocks()}

    def fetch(tickers: list[str]) -> FetchResult:
        found = [catalogue[t] for t in tickers if t in catalogue]
        absent = tuple(t for t in tickers if t not in catalogue)
        return FetchResult(stocks=found, missing=absent)

    return fetch


__all__ = [
    "AuthError", "FetchError", "FetchResult", "Fetcher", "QuotaError",
    "RefreshOutcome", "ConvictionReadError", "WorkbookLockedError",
    "fetcher_from_fixtures", "make_seed_universe", "refresh", "replace",
]
