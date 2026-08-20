"""Tests for the workbook generator.

These assert the properties that make the file safe in a non-technical user's hands:
no formulas, correct sheets protected, validation present, and no phantom empty rows.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from ajz.fixtures import sample_stocks
from ajz.status import RefreshState, RefreshStatus
from ajz.workbook import build_workbook

EXPECTED_SHEETS = [
    "Dashboard", "Top Rankings", "Opportunity Matrix",
    "Alerts", "Movers", "Conviction", "Universe", "Settings",
]
EDITABLE_SHEETS = {"Conviction", "Universe", "Settings"}


@pytest.fixture(scope="module")
def stocks():
    return sample_stocks()


@pytest.fixture(scope="module")
def saved(stocks):
    """Round-trip through bytes, so we test the real file rather than the object graph."""
    buffer = BytesIO()
    build_workbook(stocks).save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)


def test_has_exactly_the_expected_sheets(saved):
    assert saved.sheetnames == EXPECTED_SHEETS


def test_workbook_contains_no_formulas(saved):
    """REGRESSION (v5.1): the workbook was formula-driven and could go #REF!.

    Every value here is computed in Python and written as a static value, so nothing
    recalculates behind Jeff and nothing can break when he sorts or edits.
    """
    offenders = []
    for ws in saved.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    offenders.append(f"{ws.title}!{cell.coordinate}={cell.value}")
    assert offenders == [], f"formulas found: {offenders}"


def test_display_sheets_are_protected(saved):
    for name in EXPECTED_SHEETS:
        if name not in EDITABLE_SHEETS:
            assert saved[name].protection.sheet is True, f"{name} is not protected"


def test_conviction_score_cells_are_unlocked(saved):
    """Protection is on for the sheet, but the five score columns must be typeable."""
    ws = saved["Conviction"]
    for col in range(3, 8):  # the five 1-5 columns
        assert ws.cell(row=2, column=col).protection.locked is False


def test_conviction_sheet_has_1_to_5_validation(saved):
    """A typo must be refused at entry, not silently corrupt a score."""
    ws = saved["Conviction"]
    validations = ws.data_validations.dataValidation
    assert validations, "no data validation on the Conviction sheet"
    whole = [v for v in validations if v.type == "whole"]
    assert whole, "no whole-number validation found"
    assert whole[0].formula1 == "1"
    assert whole[0].formula2 == "5"


def test_universe_active_column_is_a_yes_no_list(saved):
    ws = saved["Universe"]
    lists = [v for v in ws.data_validations.dataValidation if v.type == "list"]
    assert lists and "YES,NO" in lists[0].formula1


def test_no_phantom_empty_rows_on_rankings(saved, stocks):
    """REGRESSION (v5.1): 499 pre-filled rows whose formulas returned 0.

    The rankings sheet must hold exactly one row per real stock, plus the header.
    """
    ws = saved["Top Rankings"]
    assert ws.max_row == len(stocks) + 1


def test_unrankable_stocks_are_shown_but_not_ranked(saved):
    """RIVN is loss-making: it must appear, with no rank number."""
    ws = saved["Top Rankings"]
    rows = {ws.cell(row=r, column=2).value: r for r in range(2, ws.max_row + 1)}
    assert "RIVN" in rows
    assert ws.cell(row=rows["RIVN"], column=1).value == "—"


def test_ranked_stocks_are_in_descending_value_order(saved):
    ws = saved["Top Rankings"]
    values = []
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == "—":
            break
        values.append(ws.cell(row=r, column=6).value)
    assert values == sorted(values, reverse=True)


def test_missing_values_render_as_dash_never_zero(saved):
    """REGRESSION (v5.1): missing data displayed as 0, which reads as a real bad score."""
    ws = saved["Top Rankings"]
    rows = {ws.cell(row=r, column=2).value: r for r in range(2, ws.max_row + 1)}
    snow = rows["SNOW"]  # missing ROIC -> no AJZ Score
    assert ws.cell(row=snow, column=5).value == "—"
    assert ws.cell(row=snow, column=6).value == "—"


def test_notes_explain_why_a_stock_could_not_be_scored(saved):
    ws = saved["Top Rankings"]
    rows = {ws.cell(row=r, column=2).value: r for r in range(2, ws.max_row + 1)}
    note = ws.cell(row=rows["SNOW"], column=12).value
    assert "roic" in note.lower()


def test_unscored_conviction_is_flagged_not_treated_as_zero(saved):
    """NET has fundamentals but no conviction: 'Needs Conviction', not 'Avoid'."""
    ws = saved["Top Rankings"]
    rows = {ws.cell(row=r, column=2).value: r for r in range(2, ws.max_row + 1)}
    assert ws.cell(row=rows["NET"], column=10).value == "Needs Conviction"


# --- Status banner ------------------------------------------------------------------


def _banner_of(stocks, status):
    buffer = BytesIO()
    build_workbook(stocks, status=status).save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)["Dashboard"].cell(row=4, column=2).value


def test_healthy_banner_states_the_date(stocks):
    when = datetime(2026, 8, 19, 6, 5)
    text = _banner_of(stocks, RefreshStatus(RefreshState.OK, data_as_of=when))
    assert "Data current as of" in text
    assert "2026" in text


def test_stale_banner_is_plain_english_and_dates_the_data(stocks):
    """Stale-but-labelled beats blank or wrong (spec §10)."""
    when = datetime(2026, 8, 18, 6, 5)
    text = _banner_of(stocks, RefreshStatus(RefreshState.STALE, data_as_of=when))
    assert "Could not reach the data provider" in text
    assert "18 Aug 2026" in text


def test_auth_error_tells_jeff_to_call_a_human(stocks):
    text = _banner_of(stocks, RefreshStatus(RefreshState.AUTH_ERROR))
    assert "call Dave" in text


def test_no_error_codes_or_jargon_in_any_banner(stocks):
    """Jeff must never see a status code, a URL, or the word 'API'."""
    jargon = ["API", "HTTP", "40", "50", "null", "None", "exception", "traceback"]
    for state in RefreshState:
        text = _banner_of(stocks, RefreshStatus(state, data_as_of=datetime(2026, 8, 19)))
        for term in jargon:
            assert term not in text, f"{state.value} banner leaked {term!r}: {text}"


def test_partial_refresh_lists_the_missing_tickers(stocks):
    status = RefreshStatus(
        RefreshState.PARTIAL, data_as_of=datetime(2026, 8, 19),
        missing_tickers=("XYZ", "ABC"),
    )
    buffer = BytesIO()
    build_workbook(stocks, status=status).save(buffer)
    buffer.seek(0)
    note = load_workbook(buffer)["Dashboard"].cell(row=5, column=2).value
    assert "2 tickers had no data today" in note
    assert "XYZ" in note and "ABC" in note


# --- Dashboard KPIs -----------------------------------------------------------------


def test_dashboard_shows_dash_not_zero_when_index_is_uncomputable(stocks):
    """REGRESSION (v5.1): an empty workbook proudly displayed a Quality Index of 25."""
    buffer = BytesIO()
    build_workbook([]).save(buffer)
    buffer.seek(0)
    ws = load_workbook(buffer)["Dashboard"]
    labels = {ws.cell(row=r, column=2).value: r for r in range(1, ws.max_row + 1)}
    row = labels["Portfolio Quality Index"]
    assert ws.cell(row=row, column=3).value == "—"


def test_empty_universe_still_produces_a_valid_workbook(stocks):
    """It must degrade to an honest empty dashboard, never crash."""
    buffer = BytesIO()
    build_workbook([]).save(buffer)
    buffer.seek(0)
    assert load_workbook(buffer).sheetnames == EXPECTED_SHEETS
