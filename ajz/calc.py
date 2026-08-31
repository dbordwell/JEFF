"""AJZ Rule 3.0 calculation core (spec §6). Pure functions, no I/O, no vendor imports.

Jeff's methodology, preserved exactly as written in `Spec Files/AI.docx`:

    AJZ Score       = (2 x RevenueGrowth%) + GrossMargin% + FCFMargin% + (0.5 x ROIC%)
    AJZ Value Score = AJZ Score / P/E
    Forward P/E     = AJZ Score / AJZ Value Score

Conviction was removed at Jeff's instruction in "Requested Changes for Items 2.1":
"Get Rid Of Conviction Calculation and references to same throughout. It doesn't do
anything and is subject to interpretation." It was Copilot's five-factor invention, not
his framework. Everything it fed -- the Opportunity Matrix buckets, half of each alert
rule -- now runs on the AJZ Value Score alone, which is what he calls the Primary Screen.

Every function here is written to fail loudly or return None rather than emit a
plausible-looking wrong number. That is a direct response to how v5.1 failed: it never
errored, it just quietly reported zeros that looked like "no data loaded yet".
"""

from __future__ import annotations

from .models import Alert, PEAbsence, ScoredStock, StockData
from .settings import DEFAULT_THRESHOLDS, Thresholds

# Band tables no longer live here. They are Jeff's, they change, and they are edited on
# the Settings sheet -- see ajz/bands.py. Hardcoding them here is what made the previous
# calibration a phone call instead of a cell edit.


def ajz_score(
    revenue_growth: float | None,
    gross_margin: float | None,
    fcf_margin: float | None,
    roic: float | None,
) -> float | None:
    """AJZ Score. All inputs are whole-number percentages (75.0, not 0.75).

    Returns None if any input is missing. A partial score is worse than no score:
    dropping a term silently shifts the stock down the rankings for a data reason
    rather than an investment reason.
    """
    parts = (revenue_growth, gross_margin, fcf_margin, roic)
    if any(p is None for p in parts):
        return None
    return (2 * revenue_growth) + gross_margin + fcf_margin + (0.5 * roic)


def ajz_value_score(score: float | None, pe_ratio: float | None) -> float | None:
    """AJZ Score divided by P/E.

    Returns None when P/E is missing or non-positive. A non-positive P/E means the
    company is loss-making, which makes the ratio meaningless -- not zero. v5.1's
    `IFERROR(G2/F2, 0)` turned exactly this case into 0, which reads as "Weak" and is
    indistinguishable from a stock that genuinely scores badly.
    """
    if score is None or pe_ratio is None or pe_ratio <= 0:
        return None
    return score / pe_ratio


def ajz_rating(
    value_score: float | None, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> str | None:
    """Primary Screen category for an AJZ Value Score, from Jeff's editable table."""
    return thresholds.value_bands.label_for(value_score)


def alerts_for(
    value_score: float | None,
    score_moved_pct: float | None = None,
    pe_moved_pct: float | None = None,
    band_moved: int = 0,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[Alert, ...]:
    """Alert set for one row.

    Reshaped to Jeff's v2.1 request. The old UPGRADE/DOWNGRADE pair keyed off places
    moved in the ranking, which he never asked for; he asked for movement in the numbers
    themselves -- "anything where the AJZ Score has moved more than 25% or the forward
    P/E has moved more than 10%". Rank movement is noise when the universe changes size;
    a 25% score move is a fact about the company.

    `band_moved` is a direction, not a flag: +1 for a move to a better category, -1 for
    worse, 0 for none. It was a bool, and a bool made a stock that fell from "Fair" to
    "Expensive" fire UPGRADE and DOWNGRADE at once -- a row contradicting itself teaches
    Jeff that the alert column is noise, which costs more than the missing alert would.

    Movement inputs arrive as arguments rather than being fetched, so this stays pure.
    """
    if value_score is None:
        return ()

    found: list[Alert] = []

    if value_score > thresholds.buy_value:
        found.append(Alert.BUY)

    moved_up = (score_moved_pct is not None
                and score_moved_pct >= thresholds.mover_score_pct)
    moved_down = (score_moved_pct is not None
                  and score_moved_pct <= -thresholds.mover_score_pct)
    # A P/E move is directionally inverted: a cheaper stock is better news.
    pe_up = pe_moved_pct is not None and pe_moved_pct <= -thresholds.mover_pe_pct
    pe_down = pe_moved_pct is not None and pe_moved_pct >= thresholds.mover_pe_pct

    if moved_up or pe_up or band_moved > 0:
        found.append(Alert.UPGRADE)

    if value_score < thresholds.warning_value:
        found.append(Alert.WARNING)

    if value_score < thresholds.exit_value:
        found.append(Alert.EXIT)

    if moved_down or pe_down or band_moved < 0:
        found.append(Alert.DOWNGRADE)

    return tuple(found)


# What the Notes column says for a row that has a quality score but nothing to value it
# against. Worded as plain English rather than as a fault, because for most of these
# rows it is not one: Jeff wants pre-profit companies tracked, and "no forward P/E" is a
# stage of life, not a defect.
_NO_VALUE_NOTES = {
    PEAbsence.NOT_PROFITABLE:
        "Ranked on AJZ Score only: not expected to be profitable next year, so there "
        "is no forward P/E to value it against.",
    PEAbsence.NO_ESTIMATE:
        "Ranked on AJZ Score only: no analyst estimates for this symbol, so there is "
        "no forward P/E. Worth checking the ticker is right.",
}


def _no_value_note(data: StockData) -> str:
    """Why this row has no AJZ Value Score, in the most specific terms we can justify."""
    if data.pe_absence is not None:
        return _NO_VALUE_NOTES[data.pe_absence]
    if data.pe_ratio is None:
        return "Ranked on AJZ Score only: no forward P/E available."
    # A P/E that exists but is not positive. The adapter never produces this, but a
    # hand-built row can, and it is exactly v5.1's IFERROR(...,0) case.
    return "No AJZ Value Score: company is loss-making (P/E <= 0)"


def score_stock(
    data: StockData,
    score_moved_pct: float | None = None,
    pe_moved_pct: float | None = None,
    band_moved: int = 0,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> ScoredStock:
    """Evaluate one ticker end to end. The main entry point of the calculation core."""
    notes: list[str] = []

    score = ajz_score(
        data.revenue_growth, data.gross_margin, data.fcf_margin, data.roic
    )
    if score is None:
        missing = [
            name
            for name in ("revenue_growth", "gross_margin", "fcf_margin", "roic")
            if getattr(data, name) is None
        ]
        notes.append(f"No AJZ Score: missing {', '.join(missing)}")

    value = ajz_value_score(score, data.pe_ratio)
    if score is not None and value is None:
        notes.append(_no_value_note(data))

    # Surfaced so a trailing-P/E row is visibly different in the workbook rather than
    # quietly blended with forward-P/E rows.
    if data.pe_basis is not None and data.pe_basis.value == "trailing":
        notes.append("Uses trailing P/E (no forward estimate available)")

    return ScoredStock(
        data=data,
        ajz_score=score,
        ajz_value_score=value,
        score_label=thresholds.score_bands.label_for(score),
        pe_label=thresholds.pe_bands.label_for(data.pe_ratio),
        value_label=thresholds.value_bands.label_for(value),
        alerts=alerts_for(value, score_moved_pct, pe_moved_pct, band_moved, thresholds),
        notes=tuple(notes),
    )


# --- Aggregates ----------------------------------------------------------------------
# Every aggregate below filters to rankable rows first. This is the fix for v5.1's
# single worst bug: it averaged over 499 formula-filled rows that returned 0 rather
# than blank, so AVERAGE counted them and every headline number read ~0 forever.


def rank_stocks(stocks: list[ScoredStock]) -> list[ScoredStock]:
    """Rankable stocks sorted by AJZ Value Score, best first. Unrankable are dropped."""
    rankable = [s for s in stocks if s.is_rankable]
    return sorted(rankable, key=lambda s: s.ajz_value_score, reverse=True)


def rank_pre_profit(stocks: list[ScoredStock]) -> list[ScoredStock]:
    """Pre-profit stocks sorted by AJZ Score, best first.

    A separate ordering rather than a separate sort key on one list, because the two
    lists are not comparable and must never be merged: an AJZ Score of 140 and an AJZ
    Value Score of 14 are different quantities in different units.

    AJZ Score is the right lens for these. It is revenue growth, gross margin, FCF
    margin and ROIC -- none of which needs positive earnings -- so it says something
    true about a pre-profit company, where AJZ Value Score cannot say anything at all.
    """
    pre_profit = [s for s in stocks if s.is_pre_profit]
    return sorted(pre_profit, key=lambda s: s.ajz_score, reverse=True)


def average_ajz_value(stocks: list[ScoredStock]) -> float | None:
    values = [s.ajz_value_score for s in stocks if s.is_rankable]
    return sum(values) / len(values) if values else None


def portfolio_quality_index(stocks: list[ScoredStock]) -> float | None:
    """Average AJZ Value Score normalised to 0-100.

    v5.1 shipped `(0.4*avg) + (0.3*avg) + (0.2*80) + (0.1*90)` -- two hardcoded constants
    contributing 25 fabricated points, so an empty workbook proudly displayed an index of
    exactly 25. With conviction gone this is now a single honest component rather than a
    weighted blend, so the weights disappear too: an average expressed as a percentage of
    a 15.0 "Generational-plus" ceiling, and nothing else.
    """
    avg_value = average_ajz_value(stocks)
    if avg_value is None:
        return None
    return min(avg_value / 15.0, 1.0) * 100


# --- Units guard (spec §5.6) ---------------------------------------------------------


class UnitsError(ValueError):
    """Raised when a percentage looks like a decimal ratio rather than whole percent."""


def assert_whole_percent(ticker: str, **fields: float | None) -> None:
    """Guard against the decimals-vs-percent trap.

    Providers return gross margin as 0.75; the AJZ formula wants 75. Wire it in raw
    and every score comes out ~100x too small, every stock reads "Weak", and it looks
    exactly like a data-loading failure rather than a units bug.

    Heuristic: a non-zero margin whose absolute value is < 1.0 is almost certainly a
    decimal ratio. Real margins between -1% and 1% exist but are vanishingly rare among
    the large-caps in this universe, and a false positive here is a loud, cheap failure
    while a false negative is a silently wrong dashboard.
    """
    for name, value in fields.items():
        if value is None or value == 0:
            continue
        if abs(value) < 1.0:
            raise UnitsError(
                f"{ticker}: {name}={value} looks like a decimal ratio, not whole "
                f"percent. Expected e.g. 75.0 for 75%, not 0.75. "
                f"Normalise at the adapter boundary (spec §5.6)."
            )
