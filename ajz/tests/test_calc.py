"""Tests for the AJZ calculation core.

The regression tests below are named after the v5.1 bug each one pins down. Those bugs
are documented in docs/AJZ_SPEC.md §6.2; the point of this file is that they cannot
silently come back.
"""

from __future__ import annotations

import pytest

from ajz.calc import (
    UnitsError,
    ajz_rating,
    ajz_score,
    ajz_value_score,
    alerts_for,
    assert_whole_percent,
    average_ajz_value,
    average_conviction,
    conviction_rating,
    opportunity_category,
    portfolio_quality_index,
    rank_stocks,
    score_stock,
)
from ajz.models import Alert, Category, Conviction, PEBasis, StockData


def make_stock(ticker="TEST", **kwargs):
    defaults = dict(
        revenue_growth=50.0,
        gross_margin=70.0,
        fcf_margin=40.0,
        roic=60.0,
        pe_ratio=20.0,
        pe_basis=PEBasis.FORWARD,
    )
    defaults.update(kwargs)
    return StockData(ticker=ticker, **defaults)


FULL_CONVICTION = Conviction(5, 5, 5, 5, 5)  # 25/25, Jeff's TSM example


# --- AJZ Score ----------------------------------------------------------------------


def test_ajz_score_matches_the_formula():
    # (2*114) + 75 + 45 + (0.5*90) = 228 + 75 + 45 + 45 = 393
    assert ajz_score(114, 75, 45, 90) == 393.0


def test_ajz_score_is_in_the_hundreds_for_a_high_growth_name():
    """Sanity-check against Copilot's own worked example: NVDA scored 382.

    Not an exact reproduction (his inputs were never written down), but it pins the
    order of magnitude, which is what the units bug destroys.
    """
    score = ajz_score(114, 75, 45, 90)
    assert 300 < score < 450


def test_ajz_score_is_none_when_any_input_missing():
    assert ajz_score(None, 75, 45, 90) is None
    assert ajz_score(114, None, 45, 90) is None
    assert ajz_score(114, 75, None, 90) is None
    assert ajz_score(114, 75, 45, None) is None


# --- AJZ Value Score ----------------------------------------------------------------


def test_ajz_value_score_divides_by_pe():
    assert ajz_value_score(382.0, 22.6) == pytest.approx(16.9, abs=0.1)


def test_ajz_value_score_is_none_not_zero_for_loss_making_company():
    """REGRESSION (v5.1): `IFERROR(G2/F2, 0)` turned a negative P/E into 0.

    Zero reads as "Weak", which is indistinguishable from a genuinely bad stock.
    A loss-making company must be excluded, not defamed.
    """
    assert ajz_value_score(300.0, -15.0) is None
    assert ajz_value_score(300.0, 0.0) is None
    assert ajz_value_score(300.0, None) is None


# --- Bands --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (20.0, "Elite"),
        (15.0, "Elite"),
        (12.0, "Excellent"),
        (10.0, "Excellent"),
        (8.0, "Strong"),
        (7.0, "Strong"),
        (6.0, "Good"),
        (5.0, "Good"),
        (4.0, "Fair"),
        (3.0, "Fair"),
        (1.0, "Weak"),
        (-5.0, "Weak"),
    ],
)
def test_ajz_rating_bands(value, expected):
    assert ajz_rating(value) == expected


@pytest.mark.parametrize(
    "score,expected",
    [(25, "Very High"), (21, "Very High"), (20, "High"), (16, "High"),
     (15, "Medium"), (11, "Medium"), (10, "Low"), (5, "Low")],
)
def test_conviction_rating_bands(score, expected):
    assert conviction_rating(score) == expected


# --- Conviction ---------------------------------------------------------------------


def test_conviction_sums_when_complete():
    assert Conviction(4, 5, 5, 5, 5).score == 24  # Jeff's NVDA example
    assert FULL_CONVICTION.score == 25  # his TSM example


def test_partial_conviction_is_none_not_a_partial_sum():
    """A partial sum lands in the 3-15 range and looks like a legitimate 'Low' score."""
    assert Conviction(5, 5, 5, None, None).score is None
    assert Conviction().score is None


def test_conviction_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        Conviction(6, 5, 5, 5, 5)
    with pytest.raises(ValueError):
        Conviction(0, 5, 5, 5, 5)


# --- Opportunity Matrix -------------------------------------------------------------


def test_matrix_core_holding():
    assert opportunity_category(16.9, 24) is Category.CORE_HOLDING


def test_matrix_aggressive_position():
    assert opportunity_category(8.0, 18) is Category.AGGRESSIVE


def test_defensive_compounder_accepts_high_not_just_very_high_conviction():
    """REGRESSION (v5.1): required conviction >= 21 for Defensive Compounder.

    Jeff's own scale calls 16-20 "High". A stock at AJZ 6 / conviction 20 was being
    classified "Avoid" when the framework says Defensive Compounder.
    """
    assert opportunity_category(6.0, 20) is Category.DEFENSIVE
    assert opportunity_category(3.5, 24) is Category.DEFENSIVE  # his AMZN example


def test_matrix_avoid_requires_genuinely_low_conviction():
    assert opportunity_category(4.0, 12) is Category.AVOID


def test_matrix_distinguishes_not_rated_from_unscored():
    """Two different failures that v5.1 collapsed into a silent "Avoid"."""
    assert opportunity_category(None, 24) is Category.NOT_RATED  # no usable P/E
    assert opportunity_category(9.0, None) is Category.UNSCORED  # conviction pending


# --- Alerts -------------------------------------------------------------------------


def test_buy_alert_needs_both_conditions():
    assert Alert.BUY in alerts_for(8.0, 22)
    assert Alert.BUY not in alerts_for(8.0, 19)
    assert Alert.BUY not in alerts_for(6.0, 22)


def test_warning_and_exit_alerts():
    assert Alert.WARNING in alerts_for(4.0, 20)
    exit_alerts = alerts_for(2.0, 12)
    assert Alert.EXIT in exit_alerts
    assert Alert.WARNING in exit_alerts


def test_upgrade_and_downgrade_come_from_rank_change():
    """REGRESSION (v5.1): the Upgrade Alert column had no formula at all."""
    assert Alert.UPGRADE in alerts_for(8.0, 22, rank_change=7)
    assert Alert.DOWNGRADE in alerts_for(8.0, 22, rank_change=-9)
    assert alerts_for(8.0, 22, rank_change=2) == (Alert.BUY,)


def test_no_alerts_for_unrateable_stock():
    assert alerts_for(None, 24) == ()


# --- score_stock end to end ---------------------------------------------------------


def test_score_stock_happy_path():
    result = score_stock(make_stock(revenue_growth=114, gross_margin=75,
                                    fcf_margin=45, roic=90, pe_ratio=22.6),
                         FULL_CONVICTION)
    assert result.ajz_score == 393.0
    assert result.ajz_value_score == pytest.approx(17.4, abs=0.1)
    assert result.ajz_rating == "Elite"
    assert result.conviction_score == 25
    assert result.category is Category.CORE_HOLDING
    assert result.is_rankable


def test_score_stock_explains_itself_when_it_cannot_compute():
    """Every failure must carry a human-readable reason for the workbook to show."""
    result = score_stock(make_stock(roic=None), FULL_CONVICTION)
    assert result.ajz_score is None
    assert result.category is Category.NOT_RATED
    assert any("roic" in n for n in result.notes)


def test_trailing_pe_is_flagged_in_notes():
    result = score_stock(make_stock(pe_basis=PEBasis.TRAILING), FULL_CONVICTION)
    assert any("trailing" in n.lower() for n in result.notes)


def test_pe_ratio_without_basis_is_rejected():
    """Forward and trailing P/E must never be mixed silently (spec §5.5)."""
    with pytest.raises(ValueError, match="pe_basis"):
        StockData(ticker="X", pe_ratio=20.0)


# --- Aggregates: the big v5.1 bug ---------------------------------------------------


def test_averages_ignore_unrankable_rows():
    """REGRESSION (v5.1): the single worst bug in the delivered workbook.

    499 pre-filled formula rows returned 0 rather than blank. Excel's AVERAGE skips
    blanks but counts zeros, so every headline number was divided by 499 and read ~0
    forever -- looking exactly like "the data didn't load".
    """
    real = [
        score_stock(make_stock("A", pe_ratio=20.0), FULL_CONVICTION),
        score_stock(make_stock("B", pe_ratio=20.0), FULL_CONVICTION),
    ]
    empties = [score_stock(StockData(ticker=f"E{i}")) for i in range(497)]

    avg_with_padding = average_ajz_value(real + empties)
    avg_without = average_ajz_value(real)

    assert avg_with_padding == avg_without
    assert avg_with_padding > 5  # not dragged to ~0 by the empty rows


def test_ranking_drops_unrankable_rows():
    """REGRESSION (v5.1): RANK() over $H$2:$H$500 ranked 490 empty rows."""
    stocks = [
        score_stock(make_stock("LOW", pe_ratio=100.0), FULL_CONVICTION),
        score_stock(make_stock("HIGH", pe_ratio=10.0), FULL_CONVICTION),
        score_stock(StockData(ticker="EMPTY")),
    ]
    ranked = rank_stocks(stocks)
    assert [s.ticker for s in ranked] == ["HIGH", "LOW"]


def test_average_conviction_ignores_unscored_stocks():
    stocks = [
        score_stock(make_stock("A"), Conviction(5, 5, 5, 5, 5)),
        score_stock(make_stock("B"), Conviction()),  # not yet scored
    ]
    assert average_conviction(stocks) == 25.0


def test_portfolio_quality_index_has_no_fabricated_components():
    """REGRESSION (v5.1): `(0.2*80) + (0.1*90)` hardcoded 25 fake points.

    An empty workbook displayed a Portfolio Quality Index of exactly 25. The honest
    behaviour for no data is None.
    """
    assert portfolio_quality_index([]) is None
    assert portfolio_quality_index([score_stock(StockData(ticker="X"))]) is None

    perfect = [score_stock(make_stock(pe_ratio=10.0), FULL_CONVICTION)]
    index = portfolio_quality_index(perfect)
    assert index == pytest.approx(100.0)  # elite value + 25/25 conviction


# --- Units guard --------------------------------------------------------------------


def test_units_guard_catches_decimal_ratios():
    """The trap that would have made every stock read "Weak" (spec §5.6)."""
    with pytest.raises(UnitsError, match="decimal ratio"):
        assert_whole_percent("NVDA", gross_margin=0.75)


def test_units_guard_passes_whole_percentages():
    assert_whole_percent("NVDA", gross_margin=75.0, roic=90.0, fcf_margin=45.0)


def test_units_guard_allows_zero_and_none():
    assert_whole_percent("X", gross_margin=0.0, roic=None)


def test_units_guard_catches_negative_decimal_ratios():
    with pytest.raises(UnitsError):
        assert_whole_percent("X", fcf_margin=-0.12)
