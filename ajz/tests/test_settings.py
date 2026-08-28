"""Settings: what Jeff can change without calling anyone."""

from __future__ import annotations

from ajz.bands import DEFAULT_SCORE_BANDS, DEFAULT_VALUE_BANDS, Band
from ajz.settings import (
    DEFAULT_THRESHOLDS,
    TABLE_PREFIX,
    Thresholds,
    from_mapping,
)


def test_defaults_reproduce_jeffs_v21_tables_exactly():
    t = DEFAULT_THRESHOLDS
    assert t.score_bands.label_for(281.4) == "Legendary"
    assert t.value_bands.label_for(11.82) == "Generational"
    assert t.pe_bands.label_for(232.5) == "Bubble"
    assert (t.mover_score_pct, t.mover_pe_pct) == (25.0, 10.0)


def test_an_empty_sheet_yields_the_defaults():
    thresholds, warnings = from_mapping({})
    assert thresholds == DEFAULT_THRESHOLDS
    assert warnings == []


def test_he_can_retune_a_scalar():
    thresholds, warnings = from_mapping({"mover_pe_pct": 15})
    assert thresholds.mover_pe_pct == 15.0
    assert warnings == []


def test_a_percent_sign_typed_into_a_percent_field_is_accepted():
    """The label says 'moved more than', the unit is percent, so he may well type '25%'."""
    thresholds, warnings = from_mapping({"mover_score_pct": "30%"})
    assert thresholds.mover_score_pct == 30.0
    assert warnings == []


def test_a_typo_in_one_cell_costs_that_cell_and_not_the_refresh():
    thresholds, warnings = from_mapping({"mover_pe_pct": "abuot 10"})
    assert thresholds.mover_pe_pct == DEFAULT_THRESHOLDS.mover_pe_pct
    assert len(warnings) == 1


def test_he_can_replace_a_whole_band_table():
    rows = [("Cheap enough", 8.0), ("Too dear", 2.0)]
    thresholds, warnings = from_mapping({f"{TABLE_PREFIX}value_bands": rows})
    assert thresholds.value_bands.label_for(9) == "Cheap enough"
    assert thresholds.value_bands.label_for(1) == "Too dear"
    assert warnings == []


def test_he_can_add_a_band_which_is_the_edit_he_actually_made_between_v20_and_v21():
    """v2.0 had an open-ended '5.0+ Exceptional' top band; v2.1 split it three ways.
    That exact edit must be doable in Excel, not by us."""
    rows = [(b.label, b.floor) for b in DEFAULT_VALUE_BANDS.bands]
    rows.insert(0, ("Once In A Lifetime", 20.0))
    thresholds, warnings = from_mapping({f"{TABLE_PREFIX}value_bands": rows})
    assert len(thresholds.value_bands.bands) == 8
    assert thresholds.value_bands.label_for(25) == "Once In A Lifetime"
    assert thresholds.value_bands.label_for(11.82) == "Generational"
    assert warnings == []


def test_he_can_rename_a_band_which_is_the_other_edit_he_made():
    """'Fair' -> 'Fair to Poor' between v2.0 and v2.1. Renaming must not need code."""
    rows = [(b.label, b.floor) for b in DEFAULT_SCORE_BANDS.bands]
    rows[-1] = ("Utterly Dead", rows[-1][1])
    thresholds, _ = from_mapping({f"{TABLE_PREFIX}score_bands": rows})
    assert thresholds.score_bands.label_for(10) == "Utterly Dead"


def test_clearing_a_table_restores_the_shipped_one_rather_than_leaving_stocks_unlabelled():
    thresholds, warnings = from_mapping({f"{TABLE_PREFIX}score_bands": []})
    assert thresholds.score_bands == DEFAULT_SCORE_BANDS
    assert warnings == []


def test_a_broken_row_is_dropped_and_reported_but_the_rest_of_the_table_survives():
    rows = [("Good", 10.0), ("Broken", "no idea"), ("Bad", 1.0)]
    thresholds, warnings = from_mapping({f"{TABLE_PREFIX}value_bands": rows})
    assert [b.label for b in thresholds.value_bands.bands] == ["Good", "Bad"]
    assert len(warnings) == 1


def test_exit_above_warning_is_refused_but_his_tables_are_not_thrown_away():
    """One contradictory number must not cost him seven bands he typed by hand."""
    rows = [("Mine", 9.0), ("Also mine", 1.0)]
    thresholds, warnings = from_mapping({
        "exit_value": 9, "warning_value": 2,
        f"{TABLE_PREFIX}value_bands": rows,
    })
    assert thresholds.exit_value == DEFAULT_THRESHOLDS.exit_value
    assert thresholds.value_bands.label_for(9.5) == "Mine"
    assert any("exit" in w.lower() for w in warnings)


def test_unknown_keys_are_ignored_rather_than_crashing():
    """A workbook written by a future version must still open in this one."""
    thresholds, warnings = from_mapping({"some_future_setting": 4})
    assert thresholds == DEFAULT_THRESHOLDS


def test_describe_covers_every_scalar_so_no_setting_is_invisible_on_the_sheet():
    """A setting that exists in code but not on the sheet is one he has to phone about."""
    described = {key for key, _, _, _ in Thresholds().describe()}
    scalars = {f.name for f in Thresholds.__dataclass_fields__.values()
               if not f.name.endswith("_bands")}
    assert described == scalars
