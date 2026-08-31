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


class PEAbsence(str, Enum):
    """Why a row has no P/E. Recorded because the two causes are not the same problem.

    NOT_PROFITABLE is a fact about the company: analysts project a loss, so no forward
    P/E exists to compute. That is investable information -- Jeff explicitly wants these
    tracked ("there will be pre-profit companies that should be tracked and potentially
    invested in").

    NO_ESTIMATE is a fact about our data: nobody is covering it, or the symbol returned
    nothing. That is a gap he may be able to close himself, and it is the likeliest
    signature of a ticker that does not exist -- which matters, because a symbol that
    silently matches the wrong company is this project's worst failure mode.

    Collapsing the two into "no P/E" would hide the second inside the first.
    """

    NOT_PROFITABLE = "not_profitable"
    NO_ESTIMATE = "no_estimate"


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
    pe_absence: PEAbsence | None = None

    as_of: date | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if self.pe_ratio is not None and self.pe_basis is None:
            raise ValueError(
                f"{self.ticker}: pe_ratio given without pe_basis. "
                "Forward and trailing P/E must never be mixed silently (spec §5.5)."
            )
        if self.pe_ratio is not None and self.pe_absence is not None:
            raise ValueError(
                f"{self.ticker}: has a P/E of {self.pe_ratio} and also a reason for "
                "not having one. One of the two is wrong, and guessing which would "
                "put a stock in the wrong bucket."
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
    def is_pre_profit(self) -> bool:
        """Scored on quality, but with no P/E to value it against.

        Deliberately NOT the same as "unrankable". A row with no AJZ Score at all is
        also unrankable, but it is missing data rather than missing earnings, and
        ranking it on quality would mean ranking it on a number we do not have.

        The pair (is_rankable, is_pre_profit) is mutually exclusive by construction, so
        no stock can be counted twice or fall between the two.
        """
        return self.ajz_score is not None and self.ajz_value_score is None

    @property
    def is_rankable(self) -> bool:
        """Whether this row may enter rankings and averages.

        The single most important predicate in the system. v5.1's bug was that
        unrankable rows still contributed 0 to every AVERAGE, permanently pinning
        every headline number near zero.
        """
        return self.ajz_value_score is not None
