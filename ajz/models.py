"""The internal data contract (spec §5.5) and the computed result rows.

Nothing in this module imports a data vendor. The whole point of `StockData` is that
the calculation core never learns where its numbers came from.

UNITS RULE (spec §5.6): every percentage in `StockData` is a WHOLE NUMBER.
Gross margin of 75% is `75.0`, never `0.75`. Adapters normalise at the boundary;
by the time a value reaches here it is already in whole-number percent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class PEBasis(str, Enum):
    """Which P/E we actually used for a row.

    This is mandatory rather than inferred because mixing forward and trailing P/E
    silently is a correctness hazard: the two are not comparable, and AJZ Value Score
    divides by whichever one it got.
    """

    FORWARD = "forward"
    TRAILING = "trailing"


class Category(str, Enum):
    """Opportunity Matrix bucket (spec §6.1)."""

    CORE_HOLDING = "Core Holding"
    AGGRESSIVE = "Aggressive Position"
    DEFENSIVE = "Defensive Compounder"
    AVOID = "Avoid"

    # Two distinct kinds of "we can't classify this", deliberately not merged.
    # v5.1 collapsed both into a silent 0 and produced "Avoid" for everything.
    NOT_RATED = "Not Rated"  # no usable P/E -> no AJZ Value Score -> cannot rank
    UNSCORED = "Needs Conviction"  # has AJZ Value, but Jeff hasn't scored conviction yet


class Alert(str, Enum):
    BUY = "BUY"
    UPGRADE = "UPGRADE"
    WARNING = "WARNING"
    EXIT = "EXIT"
    DOWNGRADE = "DOWNGRADE"


@dataclass(frozen=True)
class Conviction:
    """Jeff's five hand-entered 1-5 judgements (spec §7).

    This is the only data in the system that cannot be regenerated, which is why it
    is a separate type with its own validation rather than five loose floats.
    """

    predictability: int | None = None
    moat: int | None = None
    management: int | None = None
    balance_sheet: int | None = None
    tailwind: int | None = None

    COMPONENTS = ("predictability", "moat", "management", "balance_sheet", "tailwind")

    def __post_init__(self) -> None:
        for name in self.COMPONENTS:
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"conviction.{name} must be an int 1-5, got {value!r}")
            if not 1 <= value <= 5:
                raise ValueError(f"conviction.{name} must be 1-5, got {value}")

    @property
    def is_complete(self) -> bool:
        """All five scored. Partial scoring does not count -- see `score`."""
        return all(getattr(self, n) is not None for n in self.COMPONENTS)

    @property
    def score(self) -> int | None:
        """Sum of the five components, or None if any is missing.

        Deliberately None rather than a partial sum: summing three of five produces a
        number in the 3-15 range that looks like a legitimate 'Low' conviction score
        and would quietly misclassify the stock.
        """
        if not self.is_complete:
            return None
        return sum(getattr(self, n) for n in self.COMPONENTS)


@dataclass(frozen=True)
class StockData:
    """One ticker's market data -- the §5.5 contract. Vendor-agnostic."""

    ticker: str
    company: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    price: float | None = None

    # All percentages, whole numbers. See UNITS RULE above.
    revenue_growth: float | None = None
    gross_margin: float | None = None
    fcf_margin: float | None = None
    roic: float | None = None

    pe_ratio: float | None = None
    pe_basis: PEBasis | None = None

    as_of: date | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if self.pe_ratio is not None and self.pe_basis is None:
            raise ValueError(
                f"{self.ticker}: pe_ratio given without pe_basis. "
                "Forward and trailing P/E must never be mixed silently (spec §5.5)."
            )


@dataclass(frozen=True)
class ScoredStock:
    """The output of the calculation core: one fully-evaluated row."""

    data: StockData
    conviction: Conviction
    ajz_score: float | None
    ajz_value_score: float | None
    ajz_rating: str | None
    conviction_score: int | None
    conviction_rating: str | None
    category: Category
    alerts: tuple[Alert, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def ticker(self) -> str:
        return self.data.ticker

    @property
    def is_rankable(self) -> bool:
        """Whether this row may enter rankings and averages.

        The single most important predicate in the system. v5.1's bug was that
        unrankable rows still contributed 0 to every AVERAGE, permanently pinning
        every headline number near zero.
        """
        return self.ajz_value_score is not None
