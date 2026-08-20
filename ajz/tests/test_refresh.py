"""End-to-end refresh tests — the real code path Jeff's machine runs daily.

These replace the hand-rolled reconstruction in test_store.py: the conviction round-trip
is exercised through `refresh()` itself, so the test proves the shipping path preserves
his scores rather than proving a test helper does.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from openpyxl import load_workbook

from ajz.fixtures import sample_stocks
from ajz.models import Conviction
from ajz.refresh import (
    AuthError,
    FetchResult,
    QuotaError,
    fetcher_from_fixtures,
    refresh,
)
from ajz.status import RefreshState
from ajz.store import ConvictionReadError, read_existing

MONDAY = datetime(2026, 8, 17, 6, 0)
NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture
def paths(tmp_path):
    return {
        "workbook_path": tmp_path / "AJZ Dashboard.xlsx",
        "history_path": tmp_path / "history.sqlite",
        "backup_dir": tmp_path / "backups",
    }


@pytest.fixture
def seed():
    return [
        type("E", (), {"ticker": s.data.ticker, "company": s.data.company,
                       "sector": s.data.sector, "active": True, "notes": None})()
        for s in sample_stocks()
    ]


def run(paths, when=MONDAY, fetch=None, **kw):
    from ajz.store import UniverseEntry

    universe = [
        UniverseEntry(ticker=s.data.ticker, company=s.data.company, sector=s.data.sector)
        for s in sample_stocks()
    ]
    return refresh(
        fetch=fetch or fetcher_from_fixtures(),
        seed_universe=universe,
        now=when,
        **paths,
        **kw,
    )


def _set_conviction(path, ticker, scores):
    """Simulate Jeff typing (or clearing) scores on the Conviction sheet.

    Note the explicit `.value =` assignment. `ws.cell(row, col, value=None)` silently
    SKIPS the assignment in openpyxl, so passing None through the constructor would
    leave the old score in place and quietly make a clearing test pass.
    """
    wb = load_workbook(path)
    ws = wb["Conviction"]
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == ticker:
            for offset, value in enumerate(scores):
                ws.cell(row=row, column=3 + offset).value = value
            break
    else:
        raise AssertionError(f"{ticker} not found in Conviction sheet")
    wb.save(path)


# --- First run ------------------------------------------------------------------------


def test_first_run_creates_a_usable_workbook(paths):
    outcome = run(paths)
    assert outcome.written
    assert paths["workbook_path"].exists()
    assert outcome.status.state is RefreshState.OK
    assert len(outcome.ranked) > 0


def test_first_run_fires_no_movement_alerts(paths):
    """With no history, nothing has 'moved'. A wall of first-run alerts trains Jeff
    to ignore alerts entirely."""
    outcome = run(paths)
    movement = [a.value for s in outcome.stocks for a in s.alerts
                if a.value in {"UPGRADE", "DOWNGRADE"}]
    assert movement == []


# --- The conviction round-trip, through the real path ---------------------------------


def test_jeffs_scores_survive_a_refresh(paths):
    """THE critical guarantee. He scores a stock; tomorrow's refresh keeps it."""
    run(paths)
    _set_conviction(paths["workbook_path"], "NET", [5, 4, 3, 2, 1])

    run(paths, when=NEXT_MONDAY)

    assert read_existing(paths["workbook_path"]).conviction["NET"] == Conviction(5, 4, 3, 2, 1)


def test_no_conviction_is_lost_across_many_refreshes(paths):
    """Ten refreshes must not erode the data. Slow leaks are the dangerous kind."""
    run(paths)
    before = read_existing(paths["workbook_path"]).conviction

    for week in range(1, 11):
        run(paths, when=MONDAY + timedelta(days=7 * week))

    after = read_existing(paths["workbook_path"]).conviction
    for ticker, conviction in before.items():
        assert after[ticker] == conviction, f"{ticker} drifted"


def test_newly_scored_stock_becomes_classified_next_refresh(paths):
    """NET starts unscored; once Jeff scores it, it should leave 'Needs Conviction'."""
    outcome = run(paths)
    net = next(s for s in outcome.stocks if s.ticker == "NET")
    assert net.category.value == "Needs Conviction"

    _set_conviction(paths["workbook_path"], "NET", [5, 5, 5, 5, 5])
    outcome = run(paths, when=NEXT_MONDAY)

    net = next(s for s in outcome.stocks if s.ticker == "NET")
    assert net.conviction_score == 25
    assert net.category.value != "Needs Conviction"


def test_a_backup_is_written_on_every_refresh_after_the_first(paths):
    run(paths)
    outcome = run(paths, when=NEXT_MONDAY)
    assert outcome.backup is not None and outcome.backup.exists()


# --- Failure handling -----------------------------------------------------------------


def test_auth_failure_leaves_the_existing_workbook_untouched(paths):
    run(paths)
    _set_conviction(paths["workbook_path"], "NET", [5, 4, 3, 2, 1])
    before = paths["workbook_path"].read_bytes()

    def failing(tickers):
        raise AuthError("401")

    outcome = run(paths, when=NEXT_MONDAY, fetch=failing)

    assert outcome.written is False
    assert outcome.status.state is RefreshState.AUTH_ERROR
    assert paths["workbook_path"].read_bytes() == before  # byte-identical


def test_quota_failure_does_not_blank_the_workbook(paths):
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())

    def over_quota(tickers):
        raise QuotaError("429")

    outcome = run(paths, when=NEXT_MONDAY, fetch=over_quota)
    assert outcome.written is False
    assert read_existing(paths["workbook_path"]).scored_count > 0


def test_partial_fetch_is_labelled_and_lists_the_missing(paths):
    def partial(tickers):
        full = fetcher_from_fixtures()(tickers)
        return FetchResult(stocks=full.stocks[:-2], missing=("XYZ", "ABC"))

    outcome = run(paths, fetch=partial)
    assert outcome.status.state is RefreshState.PARTIAL
    assert "XYZ" in outcome.status.note


def test_corrupt_existing_workbook_aborts_without_writing(paths):
    paths["workbook_path"].write_bytes(b"not a spreadsheet")
    with pytest.raises(ConvictionReadError):
        run(paths)
    assert paths["workbook_path"].read_bytes() == b"not a spreadsheet"


def test_empty_universe_is_refused_rather_than_producing_a_blank_file(paths):
    from ajz.refresh import refresh as do_refresh

    with pytest.raises(ValueError, match="No active tickers"):
        do_refresh(fetch=fetcher_from_fixtures(), seed_universe=[], now=MONDAY, **paths)


# --- History integration --------------------------------------------------------------


def test_rank_movement_produces_alerts_on_the_second_run(paths):
    """The alert v5.1 could never fire, because the data did not exist anywhere."""
    from ajz.history import History
    from ajz.calc import rank_stocks

    run(paths)

    # Rewrite last week's history so one stock appears to have climbed sharply.
    outcome = run(paths, when=NEXT_MONDAY, snapshot=False)
    ranked = rank_stocks(outcome.stocks)
    climber = ranked[0].ticker

    history = History(paths["history_path"])
    import sqlite3
    with sqlite3.connect(paths["history_path"]) as conn:
        conn.execute(
            "UPDATE snapshots SET rank = 15 WHERE ticker = ? AND snapshot_date = ?",
            (climber, MONDAY.date().isoformat()),
        )

    outcome = run(paths, when=NEXT_MONDAY)
    moved = next(s for s in outcome.stocks if s.ticker == climber)
    assert any(a.value == "UPGRADE" for a in moved.alerts)


def test_history_survives_workbook_regeneration(paths):
    from ajz.history import History

    run(paths)
    run(paths, when=NEXT_MONDAY)
    assert len(History(paths["history_path"]).snapshot_dates()) == 2


# --- Seeding the first run ------------------------------------------------------------


def test_seeded_first_run_is_immediately_useful(paths):
    """REGRESSION (v5.1): Jeff's first open must not be an empty grid.

    Without seeding, every stock reads 'Needs Conviction' and nothing is classified —
    which is exactly the workbook Copilot handed him.
    """
    from ajz.fixtures import sample_conviction

    outcome = run(paths, seed_conviction=sample_conviction())
    classified = [s for s in outcome.stocks if s.conviction_score is not None]
    assert len(classified) >= 15
    assert any(s.category.value == "Core Holding" for s in outcome.stocks)


def test_seed_never_overrides_what_jeff_typed(paths):
    """His edits are absolute. A seed may fill an empty file, never overwrite him."""
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    _set_conviction(paths["workbook_path"], "NVDA", [1, 1, 1, 1, 1])

    outcome = run(paths, when=NEXT_MONDAY, seed_conviction=sample_conviction())

    nvda = next(s for s in outcome.stocks if s.ticker == "NVDA")
    assert nvda.conviction_score == 5, "the seed overwrote Jeff's own score"


def test_jeff_can_clear_a_seeded_score_and_it_stays_cleared(paths):
    """A seed that refilled gaps every run would make un-scoring impossible."""
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    _set_conviction(paths["workbook_path"], "NVDA", [None, None, None, None, None])

    outcome = run(paths, when=NEXT_MONDAY, seed_conviction=sample_conviction())

    nvda = next(s for s in outcome.stocks if s.ticker == "NVDA")
    assert nvda.conviction_score is None
    assert nvda.category.value == "Needs Conviction"


# --- Settings round-trip (spec §6.5) --------------------------------------------------


def _set_setting(path, key, value):
    """Simulate Jeff editing the Settings sheet, matching on the hidden key column."""
    wb = load_workbook(path)
    ws = wb["Settings"]
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=4).value == key:
            ws.cell(row=row, column=2).value = value
            break
    else:
        raise AssertionError(f"setting {key!r} not found")
    wb.save(path)


def _category_of(outcome, ticker):
    return next(s for s in outcome.stocks if s.ticker == ticker).category.value


def test_a_threshold_edit_survives_the_refresh(paths):
    """His edit must still be there after the nightly rewrite, like conviction.

    That it also *takes effect* is proved by the test below.
    """
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    _set_setting(paths["workbook_path"], "strong_value", 3.0)

    run(paths, when=NEXT_MONDAY)

    assert read_existing(paths["workbook_path"]).settings["strong_value"] == 3.0


def test_lowering_the_cutoff_makes_aggressive_reachable(paths):
    """The live-data problem, solved by Jeff rather than by a code change.

    HOOD scores ~3.6 with conviction 18. At the default cutoff of 7 it is a Defensive
    Compounder; drop the cutoff below its score and it becomes the Aggressive Position
    the bucket was designed for.
    """
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    assert _category_of(run(paths, when=NEXT_MONDAY), "HOOD") == "Defensive Compounder"

    _set_setting(paths["workbook_path"], "strong_value", 3.0)
    outcome = run(paths, when=NEXT_MONDAY + timedelta(days=7))
    assert _category_of(outcome, "HOOD") == "Aggressive Position"


def test_a_bad_setting_falls_back_without_stopping_the_refresh(paths):
    """A typo must cost a default, not a morning's dashboard."""
    run(paths)
    _set_setting(paths["workbook_path"], "warning_value", "five")

    outcome = run(paths, when=NEXT_MONDAY)
    assert outcome.written is True
    assert any("not a number" in w for w in outcome.warnings)


def test_clearing_a_setting_restores_its_default(paths):
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    _set_setting(paths["workbook_path"], "strong_value", 3.0)
    run(paths, when=NEXT_MONDAY)

    _set_setting(paths["workbook_path"], "strong_value", None)
    outcome = run(paths, when=NEXT_MONDAY + timedelta(days=7))

    # Back to the default cutoff of 7, so HOOD returns to Defensive.
    assert _category_of(outcome, "HOOD") == "Defensive Compounder"


def test_settings_and_conviction_edits_coexist(paths):
    """Both editable sheets must survive the same rewrite."""
    from ajz.fixtures import sample_conviction

    run(paths, seed_conviction=sample_conviction())
    _set_setting(paths["workbook_path"], "strong_value", 4.0)
    _set_conviction(paths["workbook_path"], "NET", [5, 4, 3, 2, 1])

    run(paths, when=NEXT_MONDAY)

    saved = read_existing(paths["workbook_path"])
    assert saved.settings["strong_value"] == 4.0
    assert saved.conviction["NET"] == Conviction(5, 4, 3, 2, 1)


def test_a_workbook_without_a_settings_sheet_still_refreshes(paths):
    """Older workbooks predate this sheet; defaults are the right answer for them."""
    run(paths)
    wb = load_workbook(paths["workbook_path"])
    del wb["Settings"]
    wb.save(paths["workbook_path"])

    outcome = run(paths, when=NEXT_MONDAY)
    assert outcome.written is True
