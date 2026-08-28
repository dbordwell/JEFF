"""Tests for the weekly snapshot store (spec §8)."""

from __future__ import annotations

from datetime import date

import pytest

from ajz.calc import rank_stocks, score_stock
from ajz.history import History
from ajz.models import PEBasis, StockData

WEEK_1 = date(2026, 8, 12)
WEEK_2 = date(2026, 8, 19)


def make(ticker: str, pe: float):
    """Lower P/E -> higher AJZ Value Score -> better rank."""
    return score_stock(
        StockData(
            ticker=ticker, revenue_growth=50.0, gross_margin=70.0, fcf_margin=40.0,
            roic=60.0, pe_ratio=pe, pe_basis=PEBasis.FORWARD,
        )
    )


@pytest.fixture
def store(tmp_path):
    return History(tmp_path / "history.sqlite")


def test_snapshot_records_one_row_per_ranked_stock(store):
    ranked = rank_stocks([make("A", 10), make("B", 20)])
    assert store.record_snapshot(ranked, WEEK_1) == 2
    assert store.snapshot_dates() == [WEEK_1]


def test_rerunning_the_same_day_overwrites_rather_than_duplicating(store):
    """A manual re-run must not corrupt the series."""
    ranked = rank_stocks([make("A", 10), make("B", 20)])
    store.record_snapshot(ranked, WEEK_1)
    store.record_snapshot(ranked, WEEK_1)
    assert store.snapshot_dates() == [WEEK_1]
    assert store.previous_ranks(WEEK_2) == {"A": 1, "B": 2}


def test_first_run_reports_no_previous_ranks(store):
    """REGRESSION: an empty history must not read as 'everything moved'."""
    assert store.previous_ranks(WEEK_1) == {}


def test_rank_change_is_positive_when_a_stock_improves(store):
    store.record_snapshot(rank_stocks([make("A", 10), make("B", 20)]), WEEK_1)
    # B overtakes A in week 2.
    changes = store.rank_changes(rank_stocks([make("B", 5), make("A", 10)]), WEEK_2)
    by_ticker = {c.ticker: c for c in changes}
    assert by_ticker["B"].change == 1  # rank 2 -> 1
    assert by_ticker["A"].change == -1  # rank 1 -> 2


def test_new_entries_have_no_rank_change(store):
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    changes = store.rank_changes(rank_stocks([make("A", 10), make("NEW", 20)]), WEEK_2)
    new = next(c for c in changes if c.ticker == "NEW")
    assert new.is_new and new.change is None


def test_movers_respect_the_five_place_threshold(store):
    week1 = [make(t, pe) for t, pe in
             [("A", 10), ("B", 11), ("C", 12), ("D", 13), ("E", 14),
              ("F", 15), ("G", 16), ("H", 17)]]
    store.record_snapshot(rank_stocks(week1), WEEK_1)

    # H jumps from rank 8 to rank 1; B slips one place.
    week2 = [make(t, pe) for t, pe in
             [("H", 1), ("A", 10), ("B", 11), ("C", 12), ("D", 13),
              ("E", 14), ("F", 15), ("G", 16)]]
    upgrades, downgrades = store.movers(rank_stocks(week2), WEEK_2)

    assert [c.ticker for c in upgrades] == ["H"]
    assert upgrades[0].change == 7
    assert downgrades == []  # a one-place slip is not a downgrade


def test_new_entries_are_excluded_from_movers(store):
    """Otherwise the first run is a wall of alerts, which trains Jeff to ignore them."""
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    upgrades, downgrades = store.movers(
        rank_stocks([make("NEW", 1), make("A", 10)]), WEEK_2
    )
    assert upgrades == [] and downgrades == []


def test_history_survives_independently_of_the_workbook(tmp_path):
    """Regenerating the workbook must never destroy history (spec §8)."""
    path = tmp_path / "history.sqlite"
    History(path).record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    # A brand-new History object over the same file — as a fresh process would do.
    assert History(path).previous_ranks(WEEK_2) == {"A": 1}


def test_unrankable_stocks_never_enter_history(store):
    """Only ranked rows are snapshotted, so history cannot inherit the v5.1 zero-rows bug."""
    loss_maker = score_stock(
        StockData(ticker="RIVN", revenue_growth=10.0, gross_margin=-5.0,
                  fcf_margin=-20.0, roic=-8.0)
    )
    assert store.record_snapshot(rank_stocks([make("A", 10), loss_maker]), WEEK_1) == 1
    assert "RIVN" not in store.previous_ranks(WEEK_2)


# --- Movement, which is what the Movers sheet actually needs ---------------------------


def test_previous_metrics_returns_score_value_and_band(store):
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    metrics = store.previous_metrics(WEEK_2)
    score, value, band = metrics["A"]
    assert score == pytest.approx(240.0)
    assert value == pytest.approx(24.0)
    assert band == "Generational"


def test_forward_pe_is_recoverable_from_what_we_already_store(store):
    """Jeff's 10% forward-P/E rule needs no schema change: P/E is Score / Value Score."""
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    score, value, _ = store.previous_metrics(WEEK_2)["A"]
    assert score / value == pytest.approx(10.0)


def test_no_baseline_is_distinguishable_from_nothing_having_moved(store):
    """The Movers sheet says different things in these two cases, so the store has to
    tell them apart. "Nothing moved" on a first run would be a claim we cannot make."""
    assert store.has_prior_snapshot(WEEK_1) is False
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    assert store.has_prior_snapshot(WEEK_2) is True


def test_previous_metrics_is_empty_when_there_is_no_prior_snapshot(store):
    store.record_snapshot(rank_stocks([make("A", 10)]), WEEK_1)
    assert store.previous_metrics(WEEK_1) == {}
