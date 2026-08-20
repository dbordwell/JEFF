"""Workbook generator (spec §9).

Writes the finished Excel file Jeff opens. Design rules, all of them reactions to how
v5.1 failed in his hands:

* **Every cell is a static value.** No formulas, no cross-sheet references. Nothing in
  the file can go #REF!, and nothing recalculates behind him. The generator is the only
  thing that computes.
* **Only two sheets are editable** — Conviction and Universe. The rest are protected, so
  he cannot accidentally type over his own dashboard.
* **Data validation on every score cell**, so a typo is refused at entry rather than
  silently corrupting a conviction score.
* **Nothing is written for a row that does not exist.** v5.1 pre-filled 499 empty rows
  with formulas that returned 0; every average then divided by 499 and read ~0 forever.
"""

from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from . import theme
from .calc import (
    average_ajz_value,
    average_conviction,
    portfolio_quality_index,
    rank_stocks,
)
from .models import Category, Conviction, ScoredStock
from .settings import DEFAULT_THRESHOLDS, Thresholds
from .status import RefreshStatus

THIN = Side(style="thin", color=theme.RULE)
CELL_BORDER = Border(bottom=THIN)


def _fill(argb: str | None) -> PatternFill | None:
    if argb is None:
        return None
    return PatternFill("solid", fgColor=argb)


def _write_header(ws: Worksheet, row: int, headers: list[str], widths: list[int]) -> None:
    for col, (label, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.font = Font(name=theme.FONT, bold=True, color=theme.INK_INVERSE, size=11)
        cell.fill = _fill(theme.HEADER_FILL)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[row].height = 28


def _style_body(cell, *, bold: bool = False, ink: str = theme.INK_PRIMARY,
                number_format: str | None = None, align: str = "left") -> None:
    cell.font = Font(name=theme.FONT, bold=bold, color=ink, size=11)
    cell.alignment = Alignment(horizontal=align, vertical="center")
    cell.border = CELL_BORDER
    if number_format:
        cell.number_format = number_format


def _protect(ws: Worksheet) -> None:
    """Read-only, but with no password.

    A password would produce a prompt, and a prompt is a thing Jeff has to understand.
    This only stops accidental typing, which is the actual risk.
    """
    # Note: never assign `protection.password`, not even None — openpyxl runs the
    # legacy hasher on whatever it is given and blows up on None. Leaving it unset is
    # what produces the passwordless protection we actually want.
    ws.protection.sheet = True
    ws.protection.selectLockedCells = True
    ws.protection.selectUnlockedCells = True


# --- Sheet 1: Dashboard ---------------------------------------------------------------


def _build_dashboard(ws: Worksheet, stocks: list[ScoredStock], status: RefreshStatus) -> None:
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 44

    title = ws.cell(row=2, column=2, value="AJZ Dashboard")
    title.font = Font(name=theme.FONT, bold=True, size=24, color=theme.INK_PRIMARY)

    # --- Status banner. The whole error-reporting surface (spec §10).
    ws.merge_cells(start_row=4, start_column=2, end_row=4, end_column=4)
    banner = ws.cell(row=4, column=2, value=status.headline)
    banner.fill = _fill(theme.BANNER_FILL[status.state.value])
    banner.font = Font(
        name=theme.FONT, bold=True, size=12, color=theme.BANNER_INK[status.state.value]
    )
    banner.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[4].height = 30

    row = 5
    if status.note:
        ws.merge_cells(start_row=5, start_column=2, end_row=5, end_column=4)
        note = ws.cell(row=5, column=2, value=status.note)
        note.font = Font(name=theme.FONT, size=10, color=theme.INK_SECONDARY, italic=True)
        note.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        row = 6

    # --- KPI tiles. Hero numbers, not charts: each answers one question at a glance.
    rankable = [s for s in stocks if s.is_rankable]
    counts = {c: sum(1 for s in stocks if s.category is c) for c in Category}

    tiles: list[tuple[str, object, str]] = [
        ("Portfolio Quality Index", portfolio_quality_index(stocks), "0.0"),
        ("Average AJZ Value Score", average_ajz_value(stocks), "0.00"),
        ("Average Conviction", average_conviction(stocks), "0.0"),
        ("Stocks ranked", len(rankable), "0"),
        ("Core Holdings", counts[Category.CORE_HOLDING], "0"),
        ("Aggressive Positions", counts[Category.AGGRESSIVE], "0"),
        ("Defensive Compounders", counts[Category.DEFENSIVE], "0"),
        ("Buy alerts", sum(1 for s in stocks if any(a.value == "BUY" for a in s.alerts)), "0"),
        ("Warning alerts", sum(1 for s in stocks if any(a.value == "WARNING" for a in s.alerts)), "0"),
        ("Awaiting your conviction scores", counts[Category.UNSCORED], "0"),
        ("Not rated (no usable P/E)", counts[Category.NOT_RATED], "0"),
    ]

    row += 2
    for label, value, fmt in tiles:
        label_cell = ws.cell(row=row, column=2, value=label)
        label_cell.font = Font(name=theme.FONT, size=11, color=theme.INK_SECONDARY)
        label_cell.alignment = Alignment(vertical="center")

        # None is rendered as an em-dash, never as 0. v5.1's Portfolio Quality Index
        # displayed a confident "25" on an empty workbook because two of its four
        # components were hardcoded constants.
        value_cell = ws.cell(row=row, column=3, value=value if value is not None else "—")
        value_cell.font = Font(
            name=theme.FONT, bold=True, size=14,
            color=theme.INK_PRIMARY if value is not None else theme.INK_MUTED,
        )
        value_cell.alignment = Alignment(horizontal="right", vertical="center")
        if value is not None:
            value_cell.number_format = fmt
        ws.row_dimensions[row].height = 22
        row += 1

    row += 1
    hint = ws.cell(
        row=row, column=2,
        value="To score a stock's conviction, use the Conviction sheet. "
              "To add or remove a stock, use the Universe sheet.",
    )
    hint.font = Font(name=theme.FONT, size=10, italic=True, color=theme.INK_MUTED)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)

    _protect(ws)


# --- Sheet 2: Top Rankings ------------------------------------------------------------


def _build_rankings(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    headers = ["Rank", "Ticker", "Company", "Sector", "AJZ Score", "AJZ Value",
               "Rating", "Conviction", "Conviction Rating", "Category", "Rank Δ", "Notes"]
    widths = [7, 10, 30, 22, 11, 11, 12, 11, 16, 22, 8, 40]
    _write_header(ws, 1, headers, widths)

    ranked = rank_stocks(stocks)
    unrankable = [s for s in stocks if not s.is_rankable]

    row = 2
    for position, s in enumerate(ranked, start=1):
        _write_ranking_row(ws, row, s, position)
        row += 1

    # Unrankable rows are shown but never ranked — they are visible so Jeff knows they
    # exist, and excluded so they cannot pollute an average.
    for s in unrankable:
        _write_ranking_row(ws, row, s, None)
        row += 1

    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(row - 1, 1)}"
    _protect(ws)


def _write_ranking_row(ws: Worksheet, row: int, s: ScoredStock, position: int | None) -> None:
    d = s.data
    rank_cell = ws.cell(row=row, column=1, value=position if position else "—")
    _style_body(rank_cell, bold=True, align="center",
                ink=theme.INK_PRIMARY if position else theme.INK_MUTED)

    _style_body(ws.cell(row=row, column=2, value=d.ticker), bold=True)
    _style_body(ws.cell(row=row, column=3, value=d.company or ""))
    _style_body(ws.cell(row=row, column=4, value=d.sector or ""), ink=theme.INK_SECONDARY)

    _style_body(ws.cell(row=row, column=5, value=s.ajz_score if s.ajz_score is not None else "—"),
                number_format="0.0" if s.ajz_score is not None else None, align="right")
    _style_body(ws.cell(row=row, column=6, value=s.ajz_value_score if s.ajz_value_score is not None else "—"),
                bold=True, number_format="0.00" if s.ajz_value_score is not None else None, align="right")

    rating = ws.cell(row=row, column=7, value=s.ajz_rating or "—")
    _style_body(rating, bold=True, align="center",
                ink=theme.AJZ_BAND_INK.get(s.ajz_rating, theme.INK_MUTED))
    if s.ajz_rating and theme.AJZ_BAND_FILL.get(s.ajz_rating):
        rating.fill = _fill(theme.AJZ_BAND_FILL[s.ajz_rating])

    _style_body(ws.cell(row=row, column=8, value=s.conviction_score if s.conviction_score is not None else "—"),
                align="center")

    crating = ws.cell(row=row, column=9, value=s.conviction_rating or "—")
    _style_body(crating, align="center",
                ink=theme.CONVICTION_BAND_INK.get(s.conviction_rating, theme.INK_MUTED))
    if s.conviction_rating and theme.CONVICTION_BAND_FILL.get(s.conviction_rating):
        crating.fill = _fill(theme.CONVICTION_BAND_FILL[s.conviction_rating])

    cat = ws.cell(row=row, column=10, value=s.category.value)
    _style_body(cat, bold=True, align="center",
                ink=theme.CATEGORY_INK.get(s.category.value, theme.INK_PRIMARY))
    if theme.CATEGORY_FILL.get(s.category.value):
        cat.fill = _fill(theme.CATEGORY_FILL[s.category.value])

    _style_body(ws.cell(row=row, column=11, value="—"), align="center", ink=theme.INK_MUTED)
    _style_body(ws.cell(row=row, column=12, value="; ".join(s.notes)),
                ink=theme.INK_MUTED)


# --- Sheet 3: Opportunity Matrix ------------------------------------------------------


def _build_matrix(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    """Jeff's 2x2, laid out as an actual 2x2 rather than a list with a category column."""
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    for col in "BCD":
        ws.column_dimensions[col].width = 34

    title = ws.cell(row=2, column=2, value="Opportunity Matrix")
    title.font = Font(name=theme.FONT, bold=True, size=20)

    sub = ws.cell(row=3, column=2, value="AJZ Value Score vs Conviction")
    sub.font = Font(name=theme.FONT, size=11, italic=True, color=theme.INK_SECONDARY)

    quadrants = [
        (5, 2, Category.CORE_HOLDING, "High AJZ · Very High Conviction"),
        (5, 3, Category.AGGRESSIVE, "High AJZ · High Conviction"),
        (16, 2, Category.DEFENSIVE, "Lower AJZ · High Conviction"),
        (16, 3, Category.AVOID, "Lower AJZ · Lower Conviction"),
    ]

    for top, col, category, caption in quadrants:
        head = ws.cell(row=top, column=col, value=category.value)
        head.fill = _fill(theme.CATEGORY_FILL.get(category.value) or theme.NEUTRAL_FILL)
        head.font = Font(name=theme.FONT, bold=True, size=12,
                         color=theme.CATEGORY_INK.get(category.value, theme.INK_PRIMARY))
        head.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[top].height = 24

        cap = ws.cell(row=top + 1, column=col, value=caption)
        cap.font = Font(name=theme.FONT, size=9, italic=True, color=theme.INK_MUTED)
        cap.alignment = Alignment(horizontal="center")

        members = [s for s in rank_stocks(stocks) if s.category is category]
        for offset, s in enumerate(members[:8]):
            cell = ws.cell(
                row=top + 2 + offset,
                value=f"{s.data.ticker}   {s.ajz_value_score:.1f}   ({s.conviction_score})",
                column=col,
            )
            cell.font = Font(name=theme.FONT, size=11)
            cell.alignment = Alignment(horizontal="center")
        if len(members) > 8:
            more = ws.cell(row=top + 10, column=col, value=f"+{len(members) - 8} more")
            more.font = Font(name=theme.FONT, size=9, italic=True, color=theme.INK_MUTED)
            more.alignment = Alignment(horizontal="center")

    _protect(ws)


# --- Sheet 4: Alerts ------------------------------------------------------------------


def _build_alerts(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    headers = ["Alert", "Ticker", "Company", "AJZ Value", "Conviction", "Why"]
    widths = [14, 10, 30, 12, 12, 52]
    _write_header(ws, 1, headers, widths)

    severity = {"EXIT": 0, "WARNING": 1, "DOWNGRADE": 2, "BUY": 3, "UPGRADE": 4}
    rows: list[tuple[str, ScoredStock]] = [
        (a.value, s) for s in stocks for a in s.alerts
    ]
    rows.sort(key=lambda r: (severity.get(r[0], 9), -(r[1].ajz_value_score or 0)))

    if not rows:
        cell = ws.cell(row=2, column=1, value="No alerts today.")
        cell.font = Font(name=theme.FONT, italic=True, color=theme.INK_MUTED)
        _protect(ws)
        return

    for row, (alert, s) in enumerate(rows, start=2):
        badge = ws.cell(row=row, column=1, value=alert)
        _style_body(badge, bold=True, align="center", ink=theme.ALERT_INK[alert])
        badge.fill = _fill(theme.ALERT_FILL[alert])

        _style_body(ws.cell(row=row, column=2, value=s.data.ticker), bold=True)
        _style_body(ws.cell(row=row, column=3, value=s.data.company or ""))
        _style_body(ws.cell(row=row, column=4, value=s.ajz_value_score),
                    number_format="0.00", align="right")
        _style_body(ws.cell(row=row, column=5, value=s.conviction_score or "—"), align="center")
        _style_body(ws.cell(row=row, column=6, value=_explain(alert, s)),
                    ink=theme.INK_SECONDARY)

    ws.freeze_panes = "A2"
    _protect(ws)


def _explain(alert: str, s: ScoredStock) -> str:
    """Every alert says why, in words. Jeff should never have to reverse-engineer a rule."""
    v = s.ajz_value_score
    c = s.conviction_score
    if alert == "BUY":
        return f"AJZ Value {v:.1f} is above 7 and conviction {c} is above 20."
    if alert == "WARNING":
        return f"AJZ Value {v:.1f} has fallen below 5."
    if alert == "EXIT":
        return f"AJZ Value {v:.1f} is below 3 and conviction {c} is below 15."
    if alert == "UPGRADE":
        return "Moved up sharply in the rankings since last week."
    if alert == "DOWNGRADE":
        return "Fell sharply in the rankings since last week."
    return ""


# --- Sheet 5: Movers ------------------------------------------------------------------


def _build_movers(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    headers = ["Ticker", "Company", "This week", "Last week", "Change"]
    widths = [10, 30, 12, 12, 12]
    _write_header(ws, 1, headers, widths)

    # Populated once the history store lands in Phase 3. Saying so is better than an
    # empty sheet that looks broken — v5.1 shipped three of these with no explanation.
    cell = ws.cell(row=2, column=1,
                   value="Rank changes appear here after the second weekly refresh.")
    cell.font = Font(name=theme.FONT, italic=True, color=theme.INK_MUTED)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=5)
    _protect(ws)


# --- Sheet 6: Conviction (EDITABLE) ---------------------------------------------------


def _build_conviction(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    """The only sheet Jeff is meant to type in (spec §7.3)."""
    headers = ["Ticker", "Company", "Revenue Predictability", "Competitive Moat",
               "Management Execution", "Balance Sheet Resilience", "Industry Tailwind",
               "Total", "Rating"]
    widths = [10, 28, 16, 16, 16, 16, 16, 9, 13]
    _write_header(ws, 1, headers, widths)

    intro = ws.cell(row=1, column=len(headers) + 2,
                    value="Score each column 1–5. Leave blank if undecided — a partly "
                          "scored stock is left out of the rankings rather than guessed at.")
    intro.font = Font(name=theme.FONT, size=10, italic=True, color=theme.INK_SECONDARY)

    # Refuses a typo at entry rather than letting it silently corrupt a score.
    validator = DataValidation(
        type="whole", operator="between", formula1=1, formula2=5, allow_blank=True,
        showErrorMessage=True, errorTitle="Score must be 1 to 5",
        error="Enter a whole number from 1 (weakest) to 5 (strongest), or leave blank.",
    )
    ws.add_data_validation(validator)

    for row, s in enumerate(sorted(stocks, key=lambda x: x.data.ticker), start=2):
        _style_body(ws.cell(row=row, column=1, value=s.data.ticker), bold=True)
        _style_body(ws.cell(row=row, column=2, value=s.data.company or ""))

        for offset, field in enumerate(Conviction.COMPONENTS):
            col = 3 + offset
            cell = ws.cell(row=row, column=col, value=getattr(s.conviction, field))
            _style_body(cell, align="center")
            cell.protection = Protection(locked=False)
            validator.add(cell)

        total = ws.cell(row=row, column=8, value=s.conviction_score or "—")
        _style_body(total, bold=True, align="center")

        rating = ws.cell(row=row, column=9, value=s.conviction_rating or "Not scored")
        _style_body(rating, align="center",
                    ink=theme.CONVICTION_BAND_INK.get(s.conviction_rating, theme.INK_MUTED))
        if s.conviction_rating and theme.CONVICTION_BAND_FILL.get(s.conviction_rating):
            rating.fill = _fill(theme.CONVICTION_BAND_FILL[s.conviction_rating])

    ws.freeze_panes = "C2"
    _protect(ws)  # protection is on, but the score cells above are explicitly unlocked


# --- Sheet 8: Settings (EDITABLE) -----------------------------------------------------


def _build_settings(ws: Worksheet, stocks: list[ScoredStock],
                    thresholds: Thresholds) -> None:
    """Jeff's decision cut-offs (spec §6.5).

    Deliberately NOT here: the AJZ Score weights. Those are AJZ Rule 3.0 itself — he
    wrote "Keep Unchanged" beside them, and altering them changes what a score means,
    breaking comparability with every stored snapshot. What IS here are the lines that
    turn scores into decisions, which are investment judgements and therefore his.

    Column D holds the field key and is hidden: the read-back matches on it rather than
    on the label text, so re-wording a label can never silently orphan a setting.
    """
    headers = ["Setting", "Your value", "What it does"]
    widths = [42, 13, 66]
    _write_header(ws, 1, headers, widths)
    ws.column_dimensions["D"].hidden = True

    intro = ws.cell(row=1, column=6,
                    value="Change a number in the 'Your value' column and it takes "
                          "effect at the next refresh. Clear a cell to restore its default.")
    intro.font = Font(name=theme.FONT, size=10, italic=True, color=theme.INK_SECONDARY)

    positive = DataValidation(
        type="decimal", operator="greaterThanOrEqual", formula1=0, allow_blank=True,
        showErrorMessage=True, errorTitle="Must be zero or more",
        error="Enter a number, or clear the cell to use the default.",
    )
    ws.add_data_validation(positive)

    for row, (key, label, value, explanation) in enumerate(thresholds.describe(), start=2):
        _style_body(ws.cell(row=row, column=1, value=label))

        cell = ws.cell(row=row, column=2, value=value)
        _style_body(cell, bold=True, align="center")
        cell.protection = Protection(locked=False)
        positive.add(cell)

        _style_body(ws.cell(row=row, column=3, value=explanation), ink=theme.INK_MUTED)
        ws.cell(row=row, column=4, value=key)

    row = len(thresholds.describe()) + 3

    # Immediate feedback on what the current settings actually produce. Without this,
    # a setting that empties a bucket is invisible until he goes hunting for it — which
    # is exactly how "Aggressive Position" sat unreachable without anyone noticing.
    heading = ws.cell(row=row, column=1, value="With these settings, your list looks like:")
    heading.font = Font(name=theme.FONT, bold=True, size=11)
    row += 1

    counts = {c: sum(1 for s in stocks if s.category is c) for c in Category}
    for category in (Category.CORE_HOLDING, Category.AGGRESSIVE, Category.DEFENSIVE,
                     Category.AVOID, Category.UNSCORED, Category.NOT_RATED):
        _style_body(ws.cell(row=row, column=1, value=f"    {category.value}"),
                    ink=theme.INK_SECONDARY)
        _style_body(ws.cell(row=row, column=2, value=counts[category]), align="center")
        if counts[category] == 0 and category is Category.AGGRESSIVE:
            _style_body(
                ws.cell(row=row, column=3,
                        value="Nothing qualifies. Lower the 'High AJZ Value' number, or "
                              "widen the gap between the Core and Aggressive conviction "
                              "levels."),
                ink=theme.INK_SECONDARY)
        row += 1

    if not thresholds.aggressive_is_reachable:
        warning = ws.cell(
            row=row + 1, column=1,
            value="Note: Core and Aggressive require the same conviction, so no stock "
                  "can ever be an Aggressive Position.",
        )
        warning.font = Font(name=theme.FONT, size=10, italic=True, color=theme.INK_PRIMARY)
        warning.fill = _fill(theme.STATUS_WARNING)

    ws.freeze_panes = "A2"
    _protect(ws)


# --- Sheet 7: Universe (EDITABLE) -----------------------------------------------------


def _build_universe(ws: Worksheet, stocks: list[ScoredStock]) -> None:
    headers = ["Ticker", "Company", "Sector", "Active", "Notes"]
    widths = [12, 30, 24, 10, 46]
    _write_header(ws, 1, headers, widths)

    intro = ws.cell(row=1, column=7,
                    value="Add a ticker to include it. Set Active to NO to hide one "
                          "without losing its conviction scores.")
    intro.font = Font(name=theme.FONT, size=10, italic=True, color=theme.INK_SECONDARY)

    active_validator = DataValidation(
        type="list", formula1='"YES,NO"', allow_blank=False, showErrorMessage=True,
        errorTitle="Active must be YES or NO", error="Choose YES or NO.",
    )
    ws.add_data_validation(active_validator)

    for row, s in enumerate(sorted(stocks, key=lambda x: x.data.ticker), start=2):
        for col, value in enumerate(
            [s.data.ticker, s.data.company or "", s.data.sector or "", "YES", ""], start=1
        ):
            cell = ws.cell(row=row, column=col, value=value)
            _style_body(cell, bold=(col == 1))
            cell.protection = Protection(locked=False)
        active_validator.add(ws.cell(row=row, column=4))

    # Blank editable rows so adding a stock is obvious rather than a guess.
    for row in range(len(stocks) + 2, len(stocks) + 12):
        for col in range(1, 6):
            cell = ws.cell(row=row, column=col)
            cell.protection = Protection(locked=False)
            cell.border = CELL_BORDER
        active_validator.add(ws.cell(row=row, column=4))

    ws.freeze_panes = "A2"
    _protect(ws)


# --- Entry point ----------------------------------------------------------------------


def build_workbook(
    stocks: list[ScoredStock],
    status: RefreshStatus | None = None,
    generated_at: datetime | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Workbook:
    """Build the complete workbook. Pure: takes data, returns a Workbook, touches no disk."""
    from .status import RefreshState

    status = status or RefreshStatus(
        state=RefreshState.OK, data_as_of=generated_at or datetime(2026, 8, 19, 6, 5)
    )

    wb = Workbook()
    wb.remove(wb.active)

    builders = [
        ("Dashboard", lambda ws: _build_dashboard(ws, stocks, status)),
        ("Top Rankings", lambda ws: _build_rankings(ws, stocks)),
        ("Opportunity Matrix", lambda ws: _build_matrix(ws, stocks)),
        ("Alerts", lambda ws: _build_alerts(ws, stocks)),
        ("Movers", lambda ws: _build_movers(ws, stocks)),
        ("Conviction", lambda ws: _build_conviction(ws, stocks)),
        ("Universe", lambda ws: _build_universe(ws, stocks)),
        ("Settings", lambda ws: _build_settings(ws, stocks, thresholds)),
    ]

    for name, builder in builders:
        builder(wb.create_sheet(title=name))

    return wb
