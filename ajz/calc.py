"""AJZ Rule 3.0 calculation core (spec §6). Pure functions, no I/O, no vendor imports.

Jeff's methodology, preserved exactly as written in `Spec Files/AI.docx`:

    AJZ Score       = (2 x RevenueGrowth%) + GrossMargin% + FCFMargin% + (0.5 x ROIC%)
    AJZ Value Score = AJZ Score / P/E
    Conviction      = sum of five 1-5 scores

Every function here is written to fail loudly or return None rather than emit a
plausible-looking wrong number. That is a direct response to how v5.1 failed: it never
errored, it just quietly reported zeros that looked like "no data loaded yet".
"""

from __future__ import annotations

from .models import Alert, Category, Conviction, ScoredStock, StockData
from .settings import DEFAULT_THRESHOLDS, Thresholds

# --- Band thresholds (spec §6) -------------------------------------------------------
# Ordered high -> low; first match wins.
AJZ_VALUE_BANDS: tuple[tuple[float, str], ...] = (
    (15.0, "Elite"),
    (10.0, "Excellent"),
    (7.0, "Strong"),
    (5.0, "Good"),
    (3.0, "Fair"),
    (float("-inf"), "Weak"),
)

CONVICTION_BANDS: tuple[tuple[int, str], ...] = (
    (21, "Very High"),
    (16, "High"),
    (11, "Medium"),
    (0, "Low"),
)

# Opportunity Matrix cutoffs (spec §6.1)
# Legacy module-level constants kept for reference; the live values now come from
# Thresholds (ajz/settings.py) so Jeff can tune them without a code change.


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


def ajz_rating(value_score: float | None) -> str | None:
    """Heat-map band for an AJZ Value Score (spec §6)."""
    if value_score is None:
        return None
    for floor, label in AJZ_VALUE_BANDS:
        if value_score >= floor:
            return label
    return "Weak"  # unreachable: last band floor is -inf


def conviction_rating(score: int | None) -> str | None:
    """Band label for a conviction score (spec §6)."""
    if score is None:
        return None
    for floor, label in CONVICTION_BANDS:
        if score >= floor:
            return label
    return "Low"


def opportunity_category(
    value_score: float | None,
    conviction_score: int | None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Category:
    """Opportunity Matrix bucket (spec §6.1).

    Note the corrected Defensive Compounder rule. v5.1 required conviction >= 21 there,
    which sent Low-AJZ + conviction 16-20 to "Avoid" even though Jeff's own scale calls
    16-20 "High". A stock at AJZ 6 / conviction 20 was being told to Avoid when the
    framework says Defensive Compounder.
    """
    if value_score is None:
        return Category.NOT_RATED
    if conviction_score is None:
        return Category.UNSCORED

    strong_value = value_score >= thresholds.strong_value
    if strong_value and conviction_score >= thresholds.core_conviction:
        return Category.CORE_HOLDING
    if strong_value and conviction_score >= thresholds.aggressive_conviction:
        return Category.AGGRESSIVE
    if not strong_value and conviction_score >= thresholds.aggressive_conviction:
        return Category.DEFENSIVE
    return Category.AVOID


def alerts_for(
    value_score: float | None,
    conviction_score: int | None,
    rank_change: int | None = None,
    entered_top_10: bool = False,
    entered_core: bool = False,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[Alert, ...]:
    """Alert set for one row (spec §6.4).

    History-dependent alerts (UPGRADE/DOWNGRADE) take their inputs as arguments rather
    than reaching for a store, so this stays a pure function.
    """
    if value_score is None:
        return ()

    found: list[Alert] = []

    if (conviction_score is not None
            and value_score > thresholds.buy_value
            and conviction_score > thresholds.buy_conviction):
        found.append(Alert.BUY)

    if rank_change is not None and rank_change >= thresholds.mover_places:
        found.append(Alert.UPGRADE)
    elif entered_top_10 or entered_core:
        found.append(Alert.UPGRADE)

    if value_score < thresholds.warning_value:
        found.append(Alert.WARNING)

    if (value_score < thresholds.exit_value and conviction_score is not None
            and conviction_score < thresholds.exit_conviction):
        found.append(Alert.EXIT)

    if rank_change is not None and rank_change <= -thresholds.mover_places:
        found.append(Alert.DOWNGRADE)

    return tuple(found)


def score_stock(
    data: StockData,
    conviction: Conviction | None = None,
    rank_change: int | None = None,
    entered_top_10: bool = False,
    entered_core: bool = False,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> ScoredStock:
    """Evaluate one ticker end to end. The main entry point of the calculation core."""
    conviction = conviction or Conviction()
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
        if data.pe_ratio is None:
            notes.append("No AJZ Value Score: no P/E available")
        else:
            notes.append("No AJZ Value Score: company is loss-making (P/E <= 0)")

    # Surfaced so a trailing-P/E row is visibly different in the workbook rather than
    # quietly blended with forward-P/E rows.
    if data.pe_basis is not None and data.pe_basis.value == "trailing":
        notes.append("Uses trailing P/E (no forward estimate available)")

    cscore = conviction.score
    if cscore is None and value is not None:
        notes.append("Needs conviction scoring")

    return ScoredStock(
        data=data,
        conviction=conviction,
        ajz_score=score,
        ajz_value_score=value,
        ajz_rating=ajz_rating(value),
        conviction_score=cscore,
        conviction_rating=conviction_rating(cscore),
        category=opportunity_category(value, cscore, thresholds),
        alerts=alerts_for(value, cscore, rank_change, entered_top_10, entered_core,
                          thresholds),
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


def average_ajz_value(stocks: list[ScoredStock]) -> float | None:
    values = [s.ajz_value_score for s in stocks if s.is_rankable]
    return sum(values) / len(values) if values else None


def average_conviction(stocks: list[ScoredStock]) -> float | None:
    """Average conviction over stocks that actually have a conviction score."""
    scores = [s.conviction_score for s in stocks if s.conviction_score is not None]
    return sum(scores) / len(scores) if scores else None


def portfolio_quality_index(stocks: list[ScoredStock]) -> float | None:
    """Portfolio Quality Index (spec §6.3).

    Only the two components we genuinely compute, reweighted to sum to 100%.
    v5.1 shipped `(0.4*avg) + (0.3*avg) + (0.2*80) + (0.1*90)` -- two hardcoded
    constants contributing 25 fabricated points, so an empty workbook proudly
    displayed an index of exactly 25.

    Both components are normalised to 0-100 before weighting:
      - AJZ Value: 15+ is "Elite", so 15 maps to 100.
      - Conviction: max is 25, so 25 maps to 100.
    """
    avg_value = average_ajz_value(stocks)
    avg_conviction = average_conviction(stocks)
    if avg_value is None or avg_conviction is None:
        return None

    value_component = min(avg_value / 15.0, 1.0) * 100
    conviction_component = (avg_conviction / 25.0) * 100
    return (0.60 * value_component) + (0.40 * conviction_component)


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
