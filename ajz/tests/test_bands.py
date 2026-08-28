"""Band tables: Jeff's three categorisation tables from 'Requested Changes for Items 2.1'.

The design constraint driving these tests: Jeff edits ONE number per band (its floor),
never a range. Ranges are derived for display. That makes gaps and overlaps structurally
impossible rather than merely validated-against — he cannot type a table that leaves a
stock uncategorised, because there is no way to express one.
"""

from __future__ import annotations

import pytest

from ajz.bands import (
    DEFAULT_PE_BANDS,
    DEFAULT_SCORE_BANDS,
    DEFAULT_VALUE_BANDS,
    Band,
    BandTable,
)


# --- Classification ------------------------------------------------------------------

def test_classify_picks_the_first_band_at_or_below_the_value():
    table = BandTable("Test", (Band("High", 100.0), Band("Low", 50.0)))
    assert table.label_for(150) == "High"
    assert table.label_for(100) == "High"   # floor is inclusive
    assert table.label_for(99.9) == "Low"


def test_the_lowest_band_is_open_ended_downwards():
    """Jeff's tables have no bottom. 'Weak to Dead' must catch anything, including a
    negative score -- a loss-making company must land somewhere, not nowhere."""
    table = BandTable("Test", (Band("High", 100.0), Band("Low", 50.0)))
    assert table.label_for(0) == "Low"
    assert table.label_for(-500) == "Low"


def test_a_missing_value_has_no_label_rather_than_a_wrong_one():
    """None is 'we could not compute this', which is not the same as 'it scored badly'.
    v5.1's IFERROR(...,0) collapsed exactly this distinction."""
    assert DEFAULT_SCORE_BANDS.label_for(None) is None


def test_an_empty_table_labels_nothing_instead_of_raising():
    assert BandTable("Empty", ()).label_for(42) is None


# --- Jeff's actual numbers, verbatim -------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (281.4, "Legendary"),      # NVDA, live
    (150.0, "Legendary"),
    (149.9, "Exceptional"),
    (136.1, "Exceptional"),    # CRM, live
    (116.8, "Elite"),          # GOOGL, live
    (80.8, "Excellent"),       # AMZN, live
    (60.0, "Good"),
    (40.0, "Fair to Poor"),
    (39.0, "Weak to Dead"),
])
def test_ajz_score_bands_match_jeffs_table(score, expected):
    assert DEFAULT_SCORE_BANDS.label_for(score) == expected


@pytest.mark.parametrize("value,expected", [
    (11.82, "Generational"),   # NVDA, live
    (10.1, "Generational"),
    (9.21, "Elite"),           # CRM, live
    (7.1, "Elite"),
    (6.97, "Exceptional"),     # GOOGL, live
    (5.0, "Exceptional"),
    (4.22, "Excellent"),       # HOOD, live
    (3.95, "Attractive"),      # AMZN, live
    (2.28, "Fair"),            # PLTR, live
    (1.9, "Expensive"),
    (0.62, "Expensive"),       # NET, live
])
def test_ajz_value_bands_match_jeffs_table(value, expected):
    assert DEFAULT_VALUE_BANDS.label_for(value) == expected


@pytest.mark.parametrize("pe,expected", [
    (14.8, "Cheap"),           # CRM, live
    (15.0, "Cheap"),
    (17.4, "Fair Value"),      # META, live
    (23.8, "Premium"),         # NVDA, live
    (34.5, "Expensive"),       # LLY, live
    (51.8, "Very Expensive"),  # HOOD, live
    (62.0, "Speculative"),     # AMD, live
    (112.5, "Ultra Speculative"),  # PLTR, live
    (232.5, "Bubble"),         # NET, live
])
def test_forward_pe_bands_match_jeffs_table(pe, expected):
    """Jeff wrote '>=15 | Cheap' but every other row of his table reads downward, and
    'Bubble' sits at the top. The intent is unambiguous: 15 or below is cheap."""
    assert DEFAULT_PE_BANDS.label_for(pe) == expected


# --- Display ranges are derived, never typed ------------------------------------------

def test_ranges_are_derived_from_the_floors_below_them():
    table = BandTable("Test", (Band("High", 100.0), Band("Mid", 50.0), Band("Low", 10.0)))
    assert table.display_ranges() == ["100 and above", "99.9 – 50", "Below 50"]


def test_editing_one_floor_reshapes_its_neighbour_automatically():
    """The whole point of storing floors: Jeff moves one number and the table stays
    contiguous. He cannot create a gap because a gap is not expressible."""
    table = BandTable("Test", (Band("High", 100.0), Band("Mid", 50.0), Band("Low", 10.0)))
    moved = BandTable("Test", (Band("High", 100.0), Band("Mid", 80.0), Band("Low", 10.0)))
    assert moved.display_ranges()[1] == "99.9 – 80"
    assert table.label_for(60) == "Mid"
    assert moved.label_for(60) == "Low"   # no gap opened, 60 simply fell through


# --- Reading Jeff's edits back ---------------------------------------------------------

def test_blank_spare_rows_are_skipped_not_treated_as_the_end_of_the_table():
    """The Settings sheet is protected, so Excel will not let Jeff insert a row; he adds
    a band by typing into a blank spare row instead. He will not reliably pick the first
    one, so a blank must not end the table."""
    rows = [("Generational", 10.1), ("Elite", 7.1),
            (None, None), ("Typed into the second spare", 1.0)]
    table, warnings = BandTable.from_rows("AJZ Value Score", rows)
    assert [b.label for b in table.bands] == [
        "Generational", "Elite", "Typed into the second spare"]
    assert warnings == []


def test_a_band_typed_into_a_spare_row_sorts_to_where_it_belongs():
    """He types at the bottom because that is where the blank rows are. The table is
    ordered by floor, so he never has to get the position right."""
    rows = [("Generational", 10.1), ("Elite", 7.1), (None, None),
            ("Once In A Lifetime", 20.0)]
    table, _ = BandTable.from_rows("AJZ Value Score", rows)
    assert [b.label for b in table.bands][0] == "Once In A Lifetime"


def test_rows_are_sorted_high_to_low_regardless_of_entry_order():
    """He may insert a row in the middle rather than retyping the table."""
    rows = [("Low", 10.0), ("High", 100.0), ("Mid", 50.0)]
    table, _ = BandTable.from_rows("Test", rows)
    assert [b.label for b in table.bands] == ["High", "Mid", "Low"]


def test_a_non_numeric_floor_drops_that_row_with_a_warning_not_a_crash():
    """A typo must cost him one band, not the morning refresh."""
    rows = [("High", 100.0), ("Broken", "abc"), ("Low", 10.0)]
    table, warnings = BandTable.from_rows("Test", rows)
    assert [b.label for b in table.bands] == ["High", "Low"]
    assert len(warnings) == 1
    assert "Broken" in warnings[0]


def test_a_percent_sign_or_stray_text_is_tolerated():
    """He types into Excel, not a form. '150+' and '15%' should not break anything."""
    rows = [("High", "150+"), ("Low", "15%")]
    table, warnings = BandTable.from_rows("Test", rows)
    assert [b.floor for b in table.bands] == [150.0, 15.0]
    assert warnings == []


def test_duplicate_floors_keep_one_band_and_warn():
    """Two bands starting at the same number means one is unreachable -- exactly the
    silent-empty-bucket failure the Aggressive Position band had."""
    rows = [("First", 50.0), ("Second", 50.0), ("Low", 10.0)]
    table, warnings = BandTable.from_rows("Test", rows)
    assert len(table.bands) == 2
    assert any("unreachable" in w.lower() or "same" in w.lower() for w in warnings)


def test_an_entirely_empty_table_falls_back_to_the_default():
    """If he clears the sheet, he gets Jeff's shipped numbers back -- not a blank
    column where every stock is uncategorised."""
    table, warnings = BandTable.from_rows(
        "AJZ Score", [], fallback=DEFAULT_SCORE_BANDS)
    assert table.bands == DEFAULT_SCORE_BANDS.bands
    assert warnings == []


def test_a_band_with_a_floor_but_no_label_is_dropped():
    rows = [("High", 100.0), (None, 50.0), ("Low", 10.0)]
    table, warnings = BandTable.from_rows("Test", rows)
    assert [b.label for b in table.bands] == ["High", "Low"]
    assert len(warnings) == 1


# --- Which end of a table is the good end ---------------------------------------------


def test_most_tables_read_best_first():
    """AJZ Score and AJZ Value both improve as the number rises, so the top row is best."""
    assert DEFAULT_SCORE_BANDS.shade_index("Legendary") == 0
    assert DEFAULT_VALUE_BANDS.shade_index("Generational") == 0


def test_forward_pe_reads_best_last():
    """REGRESSION: a low P/E is the good one, but the table is ordered high-to-low like
    the others -- so shading by row position painted "Bubble" in the strongest colour and
    left "Cheap" with no fill at all. The most expensive stock on the sheet looked like
    the best thing on it."""
    assert DEFAULT_PE_BANDS.shade_index("Cheap") == 0
    assert DEFAULT_PE_BANDS.shade_index("Bubble") == len(DEFAULT_PE_BANDS.bands) - 1


def test_shade_index_is_none_for_a_label_that_is_not_in_the_table():
    assert DEFAULT_PE_BANDS.shade_index("Nonsense") is None
    assert DEFAULT_PE_BANDS.shade_index(None) is None


def test_direction_survives_an_edit_because_it_belongs_to_the_table_not_the_rows():
    """Jeff renames and re-floors his P/E categories; none of that makes a high P/E good."""
    rows = [("Silly money", 100.0), ("Sensible", 10.0)]
    table, _ = BandTable.from_rows("Forward P/E", rows, fallback=DEFAULT_PE_BANDS)
    assert table.higher_is_better is False
    assert table.shade_index("Sensible") == 0
