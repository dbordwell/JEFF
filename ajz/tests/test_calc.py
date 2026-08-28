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
    portfolio_quality_index,
    rank_stocks,
    score_stock,
)
from ajz.models import Alert, PEBasis, StockData


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
        (17.4, "Generational"),
        (10.1, "Generational"),
        (9.3, "Elite"),
        (7.1, "Elite"),
        (6.5, "Exceptional"),
        (5.0, "Exceptional"),
        (4.6, "Excellent"),
        (3.5, "Attractive"),
        (2.7, "Fair"),
        (1.9, "Expensive"),
        (-5.0, "Expensive"),
    ],
)
def test_ajz_rating_uses_jeffs_primary_screen_table(value, expected):
    """The bands are his v2.1 table and live on the Settings sheet now.

    The old hardcoded ladder (Elite/Excellent/Strong/Good/Fair/Weak) was ours, invented
    before he had written one. He has since written his own and revised it once.
    """
    assert ajz_rating(value) == expected


# --- Alerts -------------------------------------------------------------------------


def test_buy_alert_is_now_a_pure_value_test():
    """It used to require conviction as well. That half of the rule went with v2.1."""
    assert Alert.BUY in alerts_for(8.0)
    assert Alert.BUY not in alerts_for(6.0)


def test_warning_and_exit_alerts():
    assert Alert.WARNING in alerts_for(4.0)
    exit_alerts = alerts_for(2.0)
    assert Alert.EXIT in exit_alerts
    assert Alert.WARNING in exit_alerts


def test_upgrade_and_downgrade_come_from_jeffs_percentage_moves():
    """His v2.1 rule: more than 25% on the AJZ Score, more than 10% on forward P/E.

    Replaces movement measured in ranking places, which he never asked for and which is
    noise -- adding ten tickers shifts every rank below them with nothing having changed.
    """
    assert Alert.UPGRADE in alerts_for(8.0, score_moved_pct=30)
    assert Alert.DOWNGRADE in alerts_for(8.0, score_moved_pct=-30)
    assert alerts_for(8.0, score_moved_pct=10) == (Alert.BUY,)


def test_a_falling_pe_is_an_upgrade_because_the_stock_got_cheaper():
    """Direction matters and is inverted from the score: cheaper is better news."""
    assert Alert.UPGRADE in alerts_for(8.0, pe_moved_pct=-15)
    assert Alert.DOWNGRADE in alerts_for(8.0, pe_moved_pct=15)
    assert alerts_for(8.0, pe_moved_pct=-5) == (Alert.BUY,)


def test_crossing_a_category_upward_is_an_upgrade_on_its_own():
    assert Alert.UPGRADE in alerts_for(8.0, band_moved=1)


def test_crossing_a_category_downward_is_a_downgrade_not_an_upgrade():
    """REGRESSION (found on live data): band movement was a bool, so NET falling from
    "Fair" to "Expensive" fired UPGRADE and DOWNGRADE on the same row. A row that
    contradicts itself teaches Jeff the alert column is noise."""
    alerts = alerts_for(8.0, band_moved=-1)
    assert Alert.DOWNGRADE in alerts
    assert Alert.UPGRADE not in alerts


def test_no_alerts_for_unrateable_stock():
    assert alerts_for(None) == ()


# --- score_stock end to end ---------------------------------------------------------


def test_score_stock_happy_path():
    """Jeff's NVDA row, with all three of his category tables applied."""
    result = score_stock(make_stock(revenue_growth=114, gross_margin=75,
                                    fcf_margin=45, roic=90, pe_ratio=22.6))
    assert result.ajz_score == 393.0
    assert result.ajz_value_score == pytest.approx(17.4, abs=0.1)
    assert result.score_label == "Legendary"
    assert result.pe_label == "Premium"
    assert result.value_label == "Generational"
    assert result.is_rankable


def test_forward_pe_is_the_supplied_figure_not_a_re_derivation():
    """Jeff specified Forward P/E as "AJZ Score / AJZ Value Score", which is the P/E we
    were given. Same number, but surviving the case where the Value Score is missing."""
    result = score_stock(make_stock(pe_ratio=22.6))
    assert result.forward_pe == 22.6
    assert result.ajz_score / result.ajz_value_score == pytest.approx(22.6)


def test_a_loss_making_company_still_shows_its_pe():
    """Re-deriving Forward P/E from the Value Score would lose it exactly here, which is
    where it is most worth seeing."""
    result = score_stock(make_stock(pe_ratio=-8.0))
    assert result.ajz_value_score is None
    assert result.value_label is None
    assert result.forward_pe == -8.0


def test_score_stock_explains_itself_when_it_cannot_compute():
    """Every failure must carry a human-readable reason for the workbook to show."""
    result = score_stock(make_stock(roic=None))
    assert result.ajz_score is None
    assert result.score_label is None
    assert result.value_label is None
    assert any("roic" in n for n in result.notes)


def test_trailing_pe_is_flagged_in_notes():
    result = score_stock(make_stock(pe_basis=PEBasis.TRAILING))
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
        score_stock(make_stock("A", pe_ratio=20.0)),
        score_stock(make_stock("B", pe_ratio=20.0)),
    ]
    empties = [score_stock(StockData(ticker=f"E{i}")) for i in range(497)]

    avg_with_padding = average_ajz_value(real + empties)
    avg_without = average_ajz_value(real)

    assert avg_with_padding == avg_without
    assert avg_with_padding > 5  # not dragged to ~0 by the empty rows


def test_ranking_drops_unrankable_rows():
    """REGRESSION (v5.1): RANK() over $H$2:$H$500 ranked 490 empty rows."""
    stocks = [
        score_stock(make_stock("LOW", pe_ratio=100.0)),
        score_stock(make_stock("HIGH", pe_ratio=10.0)),
        score_stock(StockData(ticker="EMPTY")),
    ]
    ranked = rank_stocks(stocks)
    assert [s.ticker for s in ranked] == ["HIGH", "LOW"]


def test_portfolio_quality_index_has_no_fabricated_components():
    """REGRESSION (v5.1): two of its four components were hardcoded constants, so an
    empty workbook proudly displayed an index of exactly 25.

    With conviction gone this is one honest component: the average AJZ Value Score as a
    percentage of a 15.0 ceiling. No data still means None, never a number.
    """
    assert portfolio_quality_index([]) is None

    stocks = [score_stock(make_stock("A", pe_ratio=20.0))]
    index = portfolio_quality_index(stocks)
    expected = min(stocks[0].ajz_value_score / 15.0, 1.0) * 100
    assert index == pytest.approx(expected)


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
