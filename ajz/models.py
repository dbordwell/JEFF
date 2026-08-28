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


class Alert(str, Enum):
    BUY = "BUY"
    UPGRADE = "UPGRADE"
    WARNING = "WARNING"
    EXIT = "EXIT"
    DOWNGRADE = "DOWNGRADE"


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
    ajz_score: float | None
    ajz_value_score: float | None

    # Jeff's three category tables, applied. Each is the word beside the number on the
    # Top Rankings sheet, and each comes from a table he can edit in Settings.
    score_label: str | None = None
    pe_label: str | None = None
    value_label: str | None = None

    alerts: tuple[Alert, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def forward_pe(self) -> float | None:
        """The P/E behind this row.

        Jeff specified this as "AJZ Score / AJZ Value Score", which is algebraically the
        same P/E the adapter supplied, since AJZ Value Score is Score / P/E. We return
        the supplied figure rather than re-deriving it: the division is exact either way,
        but re-deriving would lose the number entirely whenever the Value Score is
        missing -- which is precisely the loss-making case where the P/E is most worth
        seeing. Check the Notes column for rows using a trailing P/E.
        """
        return self.data.pe_ratio

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
