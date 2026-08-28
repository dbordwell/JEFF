"""Jeff's categorisation tables (Requested Changes for Items 2.1).

Three tables turn numbers into words: AJZ Score -> "Legendary", Forward P/E -> "Bubble",
AJZ Value Score -> "Generational". Jeff wrote all three himself and will keep retuning
them, so they live on the Settings sheet where he can edit them without calling anyone.

**Why a band stores a floor and not a range.** Jeff's source file writes bands as ranges
("149-120", "15.1 - 20"). If he typed ranges, he would own keeping them contiguous, and a
single mistyped endpoint opens a gap that silently drops a stock into no category at all
-- the same class of silent-wrong failure as v5.1's IFERROR(...,0). Storing one floor per
band makes a gap *inexpressible*: every value lands in exactly one band by construction.
The ranges he recognises are then derived for display (`display_ranges`). Complexity moves
to us; the sheet stays a column of single numbers.

His 2.0 -> 2.1 revision split one band into three, so the row count is his to change too.
The Settings sheet is protected, which means Excel will not let him *insert* a row, so it
carries blank spare rows at the foot of each table instead. `from_rows` therefore skips
blank rows rather than stopping at one, and sorts by floor -- he types a new band into any
free row and it lands in the right place by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Band:
    """One row of a table: everything at or above `floor`, until the next band up."""

    label: str
    floor: float


def _fmt(number: float) -> str:
    """Render a floor the way Jeff wrote it: 150, not 150.0; 10.1 stays 10.1."""
    return f"{number:g}"


# Numbers Jeff types in Excel arrive with the decoration he typed them with: "150+",
# "15%", "> 40". Strip anything that is not part of the number rather than rejecting it.
_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")


def _to_float(raw: object) -> float | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if raw is None:
        return None
    match = _NUMERIC.search(str(raw))
    return float(match.group()) if match else None


@dataclass(frozen=True)
class BandTable:
    """An ordered set of bands, highest floor first. First match wins."""

    # `name` is excluded from equality on purpose: it is a label for warning messages
    # ("AJZ Score: 'Elite' starts at 'abc'"), and the same table is called one thing in
    # code and another on the sheet Jeff reads. A table IS its bands; two tables with the
    # same bands behave identically and must compare equal.
    name: str = field(compare=False)
    bands: tuple[Band, ...] = ()

    # Does a bigger number mean a better stock? True for AJZ Score and AJZ Value Score,
    # False for Forward P/E, where cheap is the good end.
    #
    # This exists only so the sheet can shade the best band most strongly. Every table is
    # stored highest-floor-first regardless, so without it "Bubble" -- the most expensive
    # thing on the sheet -- sat at row 0 and got painted as though it were the best.
    #
    # It is a property of the table, not of the rows: Jeff renames his categories and
    # moves their floors, and none of that makes a high P/E good.
    higher_is_better: bool = True

    def label_for(self, value: float | None) -> str | None:
        """The band a value falls in, or None if there is no value to categorise.

        None in, None out -- deliberately. A missing AJZ Score means the data did not
        arrive, which must not be reported as the bottom band; "Weak to Dead" is a claim
        about a company, and we have no basis to make it.
        """
        if value is None:
            return None
        for band in self.bands:
            if value >= band.floor:
                return band.label
        # Nothing matched: the value sits below every floor. The lowest band absorbs it.
        # This is what makes a gap inexpressible -- whatever Jeff types as the bottom
        # floor, the bottom band is open-ended downwards, so no value is ever homeless.
        # A company with negative margins scores below zero and must still be categorised.
        return self.bands[-1].label if self.bands else None

    def display_ranges(self) -> list[str]:
        """The range text for each band, derived from the floor of the band above it.

        Read-only on the sheet: it is a view of the floors, not a second source of truth
        that could disagree with them.
        """
        out: list[str] = []
        for index, band in enumerate(self.bands):
            if index == 0:
                out.append(f"{_fmt(band.floor)} and above")
            elif index == len(self.bands) - 1:
                out.append(f"Below {_fmt(self.bands[index - 1].floor)}")
            else:
                ceiling = self.bands[index - 1].floor - 0.1
                out.append(f"{_fmt(ceiling)} – {_fmt(band.floor)}")
        return out

    def shade_index(self, label: str | None) -> int | None:
        """Rank of a band for colouring, 0 being the best. None if it is not in the table.

        Distinct from its position in `bands`, which is always ordered by floor.
        """
        for index, band in enumerate(self.bands):
            if band.label == label:
                return index if self.higher_is_better else len(self.bands) - 1 - index
        return None

    def rows(self) -> list[tuple[str, float]]:
        """(label, floor) pairs for writing to the Settings sheet."""
        return [(b.label, b.floor) for b in self.bands]

    @classmethod
    def from_rows(
        cls,
        name: str,
        rows: list[tuple[object, object]],
        fallback: BandTable | None = None,
    ) -> tuple[BandTable, list[str]]:
        """Build a table from what Jeff typed. Never raises.

        Every rejection costs him one band and produces one warning; the refresh still
        finishes. A dashboard that quietly used a default beats no dashboard at all --
        he refreshes on demand and has no one to call when it stops.
        """
        warnings: list[str] = []
        bands: list[Band] = []
        seen: dict[float, str] = {}

        for label, raw_floor in rows:
            blank_label = label is None or not str(label).strip()
            blank_floor = raw_floor is None or (
                isinstance(raw_floor, str) and not raw_floor.strip())

            if blank_label and blank_floor:
                # A spare row he has not used yet. Skip rather than stop: the sheet is
                # protected so these blanks are how he adds a band, and he will not
                # reliably fill the first one -- stopping here would silently swallow a
                # band he typed two rows further down.
                continue

            if blank_label:
                warnings.append(
                    f"{name}: a band starting at {raw_floor} has no name; it was skipped."
                )
                continue

            floor = _to_float(raw_floor)
            if floor is None:
                warnings.append(
                    f"{name}: '{label}' starts at '{raw_floor}', which is not a number; "
                    "that band was skipped."
                )
                continue

            if floor in seen:
                warnings.append(
                    f"{name}: '{label}' and '{seen[floor]}' both start at {_fmt(floor)}, "
                    f"so '{label}' is unreachable; it was skipped."
                )
                continue

            seen[floor] = str(label).strip()
            bands.append(Band(str(label).strip(), floor))

        # Direction comes from the table this one replaces, never from what Jeff typed.
        # There is no cell on the sheet for it because there is no judgement in it.
        higher_is_better = fallback.higher_is_better if fallback is not None else True

        if not bands:
            if fallback is not None:
                return fallback, warnings
            return cls(name, (), higher_is_better), warnings

        # Sort rather than demand order: he may insert a row mid-table instead of
        # retyping it, and the order he leaves behind should not change the meaning.
        bands.sort(key=lambda b: -b.floor)
        return cls(name, tuple(bands), higher_is_better), warnings


# --- Jeff's tables, verbatim from 'Requested Changes for Items 2.1' -------------------
#
# Left exactly as he wrote them, including the AJZ Score bands, which on today's live
# data put 13 of 24 stocks in "Legendary" and leave the bottom three bands empty. That is
# his call to make: he split the Value table's top band three ways between v2.0 and v2.1
# without prompting, so he is already tuning this the moment he sees real numbers -- and
# the Settings sheet is where he does it.

DEFAULT_SCORE_BANDS = BandTable("AJZ Score", (
    Band("Legendary", 150.0),
    Band("Exceptional", 120.0),
    Band("Elite", 100.0),
    Band("Excellent", 80.0),
    Band("Good", 60.0),
    Band("Fair to Poor", 40.0),
    Band("Weak to Dead", 0.0),
))

# Jeff wrote ">=15 | Cheap" at the foot of a table that otherwise reads downward with
# "Bubble" at the top. Taken literally that would label every stock Cheap. Implemented to
# his evident intent: 15 or below is cheap. Flagged to him rather than silently assumed.
DEFAULT_PE_BANDS = BandTable("Forward P/E", higher_is_better=False, bands=(
    Band("Bubble", 120.0),
    Band("Ultra Speculative", 80.1),
    Band("Speculative", 60.1),
    Band("Very Expensive", 40.1),
    Band("Expensive", 30.1),
    Band("Premium", 20.1),
    Band("Fair Value", 15.1),
    Band("Cheap", 0.0),
))

DEFAULT_VALUE_BANDS = BandTable("AJZ Value Score", (
    Band("Generational", 10.1),
    Band("Elite", 7.1),
    Band("Exceptional", 5.0),
    Band("Excellent", 4.0),
    Band("Attractive", 3.0),
    Band("Fair", 2.0),
    Band("Expensive", 0.0),
))
