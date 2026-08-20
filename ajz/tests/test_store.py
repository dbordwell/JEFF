"""Tests for the conviction round-trip — the highest-risk correctness path (spec §7.3).

The governing invariant, restated because everything here serves it:

    NEVER write a workbook containing less conviction data than the one it replaces.

Conviction is the only irreplaceable data in the system. Every test below is either
proving the round-trip preserves it, or proving a failure aborts instead of degrading.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

from ajz.fixtures import sample_stocks
from ajz.models import Conviction
from ajz.store import (
    ConvictionReadError,
    WorkbookLockedError,
    atomic_save,
    backup_workbook,
    read_existing,
)
from ajz.workbook import build_workbook


@pytest.fixture
def live_file(tmp_path):
    """A generated workbook on disk, as Jeff would have after one refresh."""
    path = tmp_path / "AJZ Dashboard.xlsx"
    build_workbook(sample_stocks()).save(path)
    return path


def _edit_conviction(path, ticker, scores):
    """Simulate Jeff typing scores into the Conviction sheet."""
    wb = load_workbook(path)
    ws = wb["Conviction"]
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == ticker:
            for offset, value in enumerate(scores):
                ws.cell(row=row, column=3 + offset, value=value)
            break
    else:
        raise AssertionError(f"{ticker} not found in Conviction sheet")
    wb.save(path)


# --- The round-trip -------------------------------------------------------------------


def test_conviction_written_by_the_generator_reads_back_identically(live_file):
    """The read/write pair agree on layout.

    This is the narrow contract test: what `build_workbook` writes, `read_existing`
    reads. The full round-trip through an actual refresh lives in
    test_refresh.py::test_jeffs_scores_survive_a_refresh — that one exercises the
    shipping code path rather than reassembling one here.
    """
    _edit_conviction(live_file, "NET", [5, 4, 3, 2, 1])
    assert read_existing(live_file).conviction["NET"] == Conviction(5, 4, 3, 2, 1)


def test_every_scored_stock_round_trips_unchanged(live_file):
    """No score may be lost or altered by a write/read cycle."""
    before = read_existing(live_file)
    atomic_save(build_workbook(sample_stocks()), live_file)
    after = read_existing(live_file)

    for ticker, conviction in before.conviction.items():
        assert after.conviction[ticker] == conviction, f"{ticker} changed"
    assert after.scored_count == before.scored_count


def test_first_run_with_no_existing_file_is_not_an_error(tmp_path):
    result = read_existing(tmp_path / "does-not-exist.xlsx")
    assert result.conviction == {}
    assert result.universe == []


# --- Refusing to destroy data ---------------------------------------------------------


def test_unreadable_workbook_aborts_rather_than_overwriting(tmp_path):
    """A file that exists but cannot be parsed must never be silently replaced."""
    corrupt = tmp_path / "AJZ Dashboard.xlsx"
    corrupt.write_bytes(b"this is not a spreadsheet")
    with pytest.raises(ConvictionReadError):
        read_existing(corrupt)


def test_workbook_without_conviction_sheet_aborts(tmp_path):
    """Some other .xlsx sitting at the target path must not be clobbered."""
    foreign = tmp_path / "AJZ Dashboard.xlsx"
    wb = Workbook()
    wb.active.title = "Sheet1"
    wb.save(foreign)
    with pytest.raises(ConvictionReadError, match="Conviction"):
        read_existing(foreign)


# --- Tolerating messy human input -----------------------------------------------------


def test_text_scores_are_coerced_not_dropped(live_file):
    """Pasting bypasses data validation, so the reader never trusts the cell type."""
    _edit_conviction(live_file, "NET", ["5", " 4 ", 3.0, 2, 1])
    assert read_existing(live_file).conviction["NET"] == Conviction(5, 4, 3, 2, 1)


def test_out_of_range_score_is_ignored_with_a_warning_not_a_crash(live_file):
    _edit_conviction(live_file, "NET", [9, 4, 3, 2, 1])
    result = read_existing(live_file)
    assert result.conviction["NET"].predictability is None
    assert any("out-of-range" in w for w in result.warnings)


def test_garbage_score_is_ignored_with_a_warning(live_file):
    _edit_conviction(live_file, "NET", ["high", 4, 3, 2, 1])
    result = read_existing(live_file)
    assert result.conviction["NET"].predictability is None
    assert any("non-numeric" in w for w in result.warnings)


def test_partial_scores_are_preserved_as_partial(live_file):
    """Jeff scoring three of five must not be rounded up into a complete score."""
    _edit_conviction(live_file, "NET", [5, 4, 3, None, None])
    conviction = read_existing(live_file).conviction["NET"]
    assert conviction.predictability == 5
    assert not conviction.is_complete
    assert conviction.score is None


def test_tickers_are_normalised_to_uppercase(live_file):
    wb = load_workbook(live_file)
    ws = wb["Conviction"]
    ws.cell(row=2, column=1, value="  nvda  ")
    wb.save(live_file)
    assert "NVDA" in read_existing(live_file).conviction


# --- Universe -------------------------------------------------------------------------


def test_universe_round_trips(live_file):
    universe = read_existing(live_file).universe
    assert {e.ticker for e in universe} >= {"NVDA", "TSM", "AVGO"}
    assert all(e.active for e in universe)


def test_setting_active_to_no_is_respected(live_file):
    wb = load_workbook(live_file)
    ws = wb["Universe"]
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "BE":
            ws.cell(row=row, column=4, value="NO")
    wb.save(live_file)

    entry = next(e for e in read_existing(live_file).universe if e.ticker == "BE")
    assert entry.active is False


def test_blank_active_cell_defaults_to_included(live_file):
    """A stock Jeff typed in without filling Active must appear, not vanish."""
    wb = load_workbook(live_file)
    ws = wb["Universe"]
    new_row = ws.max_row + 1
    ws.cell(row=new_row, column=1, value="ASML")
    wb.save(live_file)

    entry = next(e for e in read_existing(live_file).universe if e.ticker == "ASML")
    assert entry.active is True


# --- Backups and atomic writes --------------------------------------------------------


def test_backup_is_written_before_replacement(live_file, tmp_path):
    backups = tmp_path / "backups"
    made = backup_workbook(live_file, backups, datetime(2026, 8, 19, 6, 5))
    assert made is not None and made.exists()
    assert read_existing(made).scored_count > 0


def test_backups_are_pruned_to_the_keep_limit(live_file, tmp_path):
    backups = tmp_path / "backups"
    for hour in range(35):
        backup_workbook(live_file, backups, datetime(2026, 8, 19, 0, 0, hour))
    assert len(list(backups.glob("*.xlsx"))) == 30


def test_atomic_save_leaves_no_temp_file_behind(live_file):
    atomic_save(build_workbook(sample_stocks()), live_file)
    assert not live_file.with_suffix(".xlsx.tmp").exists()


def test_atomic_save_does_not_corrupt_the_target_on_failure(live_file, monkeypatch):
    """If the replace fails, the file Jeff opens must still be the old, valid one."""
    original = read_existing(live_file).scored_count

    def boom(self, target):
        raise PermissionError("file is open in Excel")

    monkeypatch.setattr("pathlib.Path.replace", boom)
    with pytest.raises(WorkbookLockedError, match="open in Excel"):
        atomic_save(build_workbook(sample_stocks()), live_file)

    assert read_existing(live_file).scored_count == original
    assert not live_file.with_suffix(".xlsx.tmp").exists()
