"""Tests for Jeff's tunable thresholds (spec §6.5)."""

from __future__ import annotations

import pytest

from ajz.calc import alerts_for, opportunity_category
from ajz.models import Alert, Category
from ajz.settings import DEFAULT_THRESHOLDS, Thresholds, from_mapping


def test_defaults_reproduce_jeffs_original_framework():
    """An untouched Settings sheet must behave exactly as his Copilot chat described."""
    t = DEFAULT_THRESHOLDS
    assert (t.strong_value, t.core_conviction, t.aggressive_conviction) == (7.0, 21, 16)
    assert (t.warning_value, t.exit_value) == (5.0, 3.0)


def test_lowering_the_value_cutoff_promotes_stocks():
    """The main lever. AJZ Value 6 / conviction 24 is Defensive by default."""
    assert opportunity_category(6.0, 24) is Category.DEFENSIVE
    relaxed = Thresholds(strong_value=5.0)
    assert opportunity_category(6.0, 24, relaxed) is Category.CORE_HOLDING


def test_aggressive_becomes_reachable_when_the_value_cutoff_drops():
    """HOOD-like: AJZ Value 4.66, conviction 18. Unreachable at 7, Aggressive at 4.5."""
    assert opportunity_category(4.66, 18) is Category.DEFENSIVE
    tuned = Thresholds(strong_value=4.5)
    assert opportunity_category(4.66, 18, tuned) is Category.AGGRESSIVE


def test_widening_the_aggressive_band_downward_captures_medium_conviction():
    """His PROSE says Aggressive is 'High AJZ + Medium conviction', and Medium is 11-15.

    His EXAMPLES used 16-20 (BE 18, HOOD 18, MELI 19 all labelled Aggressive). The
    implementation followed the examples. This proves the prose reading is one setting
    away if that is what he actually meant.
    """
    prose_reading = Thresholds(aggressive_conviction=11, core_conviction=16)
    assert opportunity_category(9.0, 13, prose_reading) is Category.AGGRESSIVE
    assert opportunity_category(9.0, 18, prose_reading) is Category.CORE_HOLDING


def test_equal_conviction_levels_close_the_aggressive_band_entirely():
    """A configuration where the bucket can never be reached must be detectable."""
    closed = Thresholds(core_conviction=16, aggressive_conviction=16)
    assert closed.aggressive_is_reachable is False
    assert opportunity_category(9.0, 18, closed) is Category.CORE_HOLDING
    assert DEFAULT_THRESHOLDS.aggressive_is_reachable is True


def test_core_below_aggressive_is_rejected():
    """Inverted levels would make Aggressive unreachable in a confusing way."""
    with pytest.raises(ValueError, match="Aggressive"):
        Thresholds(core_conviction=15, aggressive_conviction=20)


def test_exit_stricter_than_warning_is_rejected():
    with pytest.raises(ValueError, match="exit"):
        Thresholds(warning_value=3.0, exit_value=5.0)


# --- Alerts ---------------------------------------------------------------------------


def test_raising_the_warning_bar_makes_warnings_rarer():
    """Live data fires WARNING on ~13 of 24 names, which trains Jeff to ignore them."""
    assert Alert.WARNING in alerts_for(4.5, 20)
    quieter = Thresholds(warning_value=3.0)
    assert Alert.WARNING not in alerts_for(4.5, 20, thresholds=quieter)


def test_buy_alert_follows_its_own_thresholds():
    assert Alert.BUY not in alerts_for(6.0, 22)
    easier = Thresholds(buy_value=5.0)
    assert Alert.BUY in alerts_for(6.0, 22, thresholds=easier)


def test_mover_sensitivity_is_tunable():
    assert Alert.UPGRADE not in alerts_for(8.0, 22, rank_change=3)
    sensitive = Thresholds(mover_places=3)
    assert Alert.UPGRADE in alerts_for(8.0, 22, rank_change=3, thresholds=sensitive)


# --- Reading the Settings sheet -------------------------------------------------------


def test_values_are_read_from_a_mapping():
    thresholds, warnings = from_mapping({"strong_value": "5", "warning_value": 3.5})
    assert thresholds.strong_value == 5.0
    assert thresholds.warning_value == 3.5
    assert warnings == []


def test_conviction_settings_are_coerced_to_whole_numbers():
    thresholds, _ = from_mapping({"core_conviction": "20.0"})
    assert thresholds.core_conviction == 20
    assert isinstance(thresholds.core_conviction, int)


def test_a_typo_falls_back_to_that_fields_default_without_stopping_the_refresh():
    """A dashboard using one default beats no dashboard at all."""
    thresholds, warnings = from_mapping({"strong_value": "seven"})
    assert thresholds.strong_value == DEFAULT_THRESHOLDS.strong_value
    assert any("not a number" in w for w in warnings)


def test_blank_cells_are_ignored_rather_than_treated_as_zero():
    """REGRESSION in spirit (v5.1): blank must never mean 0."""
    thresholds, warnings = from_mapping({"strong_value": "", "warning_value": None})
    assert thresholds == DEFAULT_THRESHOLDS
    assert warnings == []


def test_an_impossible_combination_falls_back_to_defaults_with_a_warning():
    thresholds, warnings = from_mapping(
        {"core_conviction": 15, "aggressive_conviction": 20}
    )
    assert thresholds == DEFAULT_THRESHOLDS
    assert any("Aggressive" in w for w in warnings)


def test_unreachable_aggressive_band_is_warned_about():
    _, warnings = from_mapping({"core_conviction": 16, "aggressive_conviction": 16})
    assert any("never be reached" in w for w in warnings)


def test_unknown_keys_are_ignored():
    thresholds, _ = from_mapping({"nonsense": 1, "strong_value": 6})
    assert thresholds.strong_value == 6.0


def test_describe_covers_every_tunable_field():
    """The Settings sheet is generated from describe(), so it must not miss a field."""
    from dataclasses import fields

    described = {key for key, _, _, _ in DEFAULT_THRESHOLDS.describe()}
    assert described == {f.name for f in fields(Thresholds)}
