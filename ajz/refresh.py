"""The refresh orchestration — the sequence that runs once a day (spec §3).

    read existing  ->  back up  ->  fetch  ->  score  ->  snapshot  ->  write

Ordering is a safety property, not a style choice. Jeff's own edits — his universe, his
category tables — are read and backed up BEFORE anything can fail, so no failure
downstream can cost him work he typed. If the read fails we abort having written nothing.

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
from .models import ScoredStock, StockData
from .settings import Thresholds, from_mapping
from .status import RefreshState, RefreshStatus
from .store import (
    WorkbookReadError,
    UniverseEntry,
    WorkbookLockedError,
    assert_writable,
    atomic_save,
    archive_conviction,
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
    now: datetime | None = None,
    snapshot: bool = True,
) -> RefreshOutcome:
    """Run one refresh. Raises only for conditions where writing would lose data."""
    now = now or datetime.now()
    today = now.date()

    # 0. Can we write at all? The write is the last thing that happens, so asking here
    #    turns "seventeen seconds of work, then a locked file" into an immediate answer.
    #    It is not a substitute for the check inside atomic_save -- he can open the
    #    workbook while the refresh runs -- it just stops the common case being slow.
    assert_writable(workbook_path)

    # 1. Read Jeff's data first. A failure here is fatal by design: if we cannot prove
    #    what he had, we must not overwrite it. This propagates to the caller.
    saved = read_existing(workbook_path)
    warnings = list(saved.warnings)

    # 2. Back it up before anything else can go wrong.
    backup = backup_workbook(workbook_path, backup_dir, now)

    #    Backups prune at thirty, so they are not a home for data we are deleting on
    #    purpose. Jeff's conviction scores were five hand judgements per stock that no
    #    API can regenerate; v2.1 removes the feature, not his notes. This takes one
    #    permanent copy on the first refresh after the upgrade and never runs again.
    archived = archive_conviction(workbook_path, backup_dir.parent)
    if archived is not None:
        warnings.append(
            f"Conviction has been removed as you asked. Your scores were saved to "
            f"{archived.name} first, in case you ever want them back."
        )

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

    # 5. Score.
    #
    # Jeff's threshold and category-table edits, read back from the Settings sheet. Bad
    # input falls back to that field's default with a warning rather than stopping the
    # refresh — a dashboard using one default beats no dashboard, and he refreshes on
    # demand with nobody to call.
    thresholds, threshold_warnings = from_mapping(saved.settings)
    warnings.extend(threshold_warnings)

    scored = [score_stock(data, thresholds=thresholds) for data in fetched]

    # 6. Snapshot, then fold movement back into the alerts.
    history = History(history_path)
    scored = _apply_movement(scored, history, today, thresholds)
    if snapshot:
        history.record_snapshot(rank_stocks(scored), today)

    status = RefreshStatus(state=state, data_as_of=now, missing_tickers=missing)

    # 7. Write atomically. A locked file aborts cleanly, leaving the good copy in place.
    atomic_save(
        build_workbook(scored, status=status, thresholds=thresholds,
                       movement=movement_report(scored, history, today, thresholds)),
        workbook_path,
    )

    return RefreshOutcome(
        status=status, stocks=scored, written=True, backup=backup,
        warnings=tuple(warnings),
    )


def _apply_movement(
    scored: list[ScoredStock],
    history: History,
    today: date,
    thresholds: Thresholds,
) -> list[ScoredStock]:
    """Re-score each stock with how far it has moved since the last snapshot.

    Jeff's v2.1 rules: the AJZ Score moving more than 25%, the forward P/E moving more
    than 10%, or the stock crossing into a different category on any of his three tables.

    This replaces movement measured in ranking places. Places moved was never something
    he asked for, and it is noise: adding ten tickers to the universe shifts everything
    below them without a single company having changed. A 25% move in the score is a
    fact about the business.

    Percentages are computed against the absolute value of the previous score so a
    company crossing from negative to positive reads as an improvement rather than
    flipping sign and reporting a collapse.
    """
    previous = history.previous_metrics(today)
    if not previous:
        return scored   # first run: nothing to compare against, so nothing has "moved"

    out: list[ScoredStock] = []
    for s in scored:
        prior = previous.get(s.ticker)
        if prior is None:
            out.append(s)   # new to the universe; it has not moved, it has arrived
            continue

        prior_score, prior_value, prior_band = prior
        prior_pe = (prior_score / prior_value
                    if prior_score is not None and prior_value else None)

        out.append(score_stock(
            s.data,
            score_moved_pct=_pct_change(prior_score, s.ajz_score),
            pe_moved_pct=_pct_change(prior_pe, s.forward_pe),
            band_moved=_band_direction(thresholds, prior_band, s.value_label),
            thresholds=thresholds,
        ))
    return out


def movement_report(
    scored: list[ScoredStock],
    history: History,
    today: date,
    thresholds: Thresholds,
) -> dict:
    """Rows for the Movers sheet, plus whether we have a baseline to compare against.

    Reports three kinds of movement, all of which Jeff asked for by name: the AJZ Score
    moving more than his percentage, the forward P/E moving more than his percentage, and
    a stock changing category on any of his three tables.

    `has_baseline` is separate from an empty row list on purpose. "We have nothing to
    compare against" and "nothing moved" are different facts, and only one of them means
    the market was quiet.
    """
    if not history.has_prior_snapshot(today):
        return {"has_baseline": False, "rows": []}

    previous = history.previous_metrics(today)
    rows: list[dict] = []

    for s in scored:
        prior = previous.get(s.ticker)
        if prior is None:
            continue
        prior_score, prior_value, prior_band = prior
        prior_pe = (prior_score / prior_value
                    if prior_score is not None and prior_value else None)

        score_pct = _pct_change(prior_score, s.ajz_score)
        if score_pct is not None and abs(score_pct) >= thresholds.mover_score_pct:
            rows.append({
                "ticker": s.ticker, "company": s.data.company,
                "what": "AJZ Score",
                "was": f"{prior_score:.1f}", "now": f"{s.ajz_score:.1f}",
                "change": f"{score_pct:+.1f}%", "improved": score_pct > 0,
            })

        pe_pct = _pct_change(prior_pe, s.forward_pe)
        if pe_pct is not None and abs(pe_pct) >= thresholds.mover_pe_pct:
            rows.append({
                "ticker": s.ticker, "company": s.data.company,
                "what": "Forward P/E",
                "was": f"{prior_pe:.1f}", "now": f"{s.forward_pe:.1f}",
                # A falling P/E is the stock getting cheaper, which is the good direction.
                "change": f"{pe_pct:+.1f}%", "improved": pe_pct < 0,
            })

        if (prior_band is not None and s.value_label is not None
                and prior_band != s.value_label):
            rows.append({
                "ticker": s.ticker, "company": s.data.company,
                "what": "Changed category",
                "was": prior_band, "now": s.value_label,
                "change": "—",
                "improved": _band_rank(thresholds, s.value_label)
                            < _band_rank(thresholds, prior_band),
            })

    rows.sort(key=lambda r: (r["ticker"], r["what"]))
    return {"has_baseline": True, "rows": rows}


def _band_direction(thresholds: Thresholds, before: str | None,
                    after: str | None) -> int:
    """+1 if the stock moved to a better category, -1 to a worse one, 0 for no move.

    Direction rather than "did it change", because a change alone cannot tell UPGRADE
    from DOWNGRADE, and guessing UPGRADE made falling stocks fire both at once.
    """
    if before is None or after is None or before == after:
        return 0
    delta = _band_rank(thresholds, before) - _band_rank(thresholds, after)
    return 1 if delta > 0 else -1 if delta < 0 else 0


def _band_rank(thresholds: Thresholds, label: str | None) -> int:
    """Position of a band in the table, 0 being the best. Unknown labels sort last.

    A label can be unknown legitimately: Jeff renames his categories, so last week's
    snapshot may hold a word that no longer appears in this week's table.
    """
    for index, band in enumerate(thresholds.value_bands.bands):
        if band.label == label:
            return index
    return len(thresholds.value_bands.bands)


def _pct_change(before: float | None, after: float | None) -> float | None:
    """Percent change, or None when there is nothing meaningful to compare.

    A zero baseline has no percentage change — every move from zero is infinite. Saying
    None is honest; returning a large number would fire an alert on arithmetic rather
    than on anything that happened to the company.
    """
    if before is None or after is None or before == 0:
        return None
    return (after - before) / abs(before) * 100.0


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
    "RefreshOutcome", "WorkbookReadError", "WorkbookLockedError",
    "fetcher_from_fixtures", "make_seed_universe", "refresh", "replace",
]
