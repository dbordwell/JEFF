"""Jeff's tunable settings (Requested Changes for Items 2.1).

A deliberate line runs through this module:

  * **The FORMULA is not adjustable.** AJZ Score's weights — 2x revenue growth, 0.5x ROIC
    — are AJZ Rule 3.0 itself. Jeff wrote "Keep Unchanged" next to them, and changing them
    changes what a score *means*, breaking comparability with every past snapshot.

  * **Everything that turns a number into a word IS adjustable.** His three category
    tables and his two movement percentages are investment judgements, they are his
    domain, and he is visibly still tuning them: between v2.0 and v2.1 of his change
    request he split the Value table's top band into three because one band was
    swallowing every stock. He did that unprompted, in a day, without asking.

That is the whole design rule here. Every number Jeff wrote in his change request is
editable by Jeff on the Settings sheet — including the *names* of the categories and how
many there are. The less of this that needs us, the less of it comes back to us.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

from .bands import (
    DEFAULT_PE_BANDS,
    DEFAULT_SCORE_BANDS,
    DEFAULT_VALUE_BANDS,
    BandTable,
)

# Keys under which parsed band tables travel inside the settings mapping, so that reading
# the sheet stays a single dict and no call signature has to grow a second argument.
TABLE_PREFIX = "table:"
TABLE_END = "table:end"   # closes a table, so blank spare rows inside one stay spares

# Blank rows left at the foot of each table so Jeff can add a band. Excel will not let
# him insert a row into a protected sheet, and unprotecting the sheet to allow it would
# trade a real safeguard for a rare need. Three is enough for the kind of edit he has
# actually made (v2.0 -> v2.1 added two), and the count is restored on every refresh.
SPARE_BAND_ROWS = 3

# (attribute, sheet title, default) — drives both writing and reading the sheet.
BAND_TABLES: tuple[tuple[str, str, BandTable], ...] = (
    ("score_bands", "AJZ Score — categories", DEFAULT_SCORE_BANDS),
    ("pe_bands", "Forward P/E — categories", DEFAULT_PE_BANDS),
    ("value_bands", "AJZ Value Score — categories (Primary Screen)", DEFAULT_VALUE_BANDS),
)


@dataclass(frozen=True)
class Thresholds:
    """The settings that turn scores into words and into alerts.

    Defaults reproduce Jeff's v2.1 tables exactly, so an untouched Settings sheet behaves
    precisely as his change request specifies.
    """

    # --- The three category tables (his "Settings: Tables")
    score_bands: BandTable = field(default=DEFAULT_SCORE_BANDS)
    pe_bands: BandTable = field(default=DEFAULT_PE_BANDS)
    value_bands: BandTable = field(default=DEFAULT_VALUE_BANDS)

    # --- Movers (his: "an alert for anything where the AJZ Score has moved more than
    #     25% or the forward P/E has moved more than 10%")
    mover_score_pct: float = 25.0
    mover_pe_pct: float = 10.0

    # --- Alerts. Conviction is gone from these by his instruction ("Get rid of
    #     Conviction Calculation and references to same throughout"), which leaves them
    #     as pure AJZ Value tests. He did not ask for the Alerts sheet itself to change,
    #     so it keeps working on the half of each rule that survives.
    buy_value: float = 7.0
    warning_value: float = 5.0
    exit_value: float = 3.0

    # What to call companies with no forward P/E. A word, not a number, and his to
    # choose for the same reason the band names are: he is the one who has to read it.
    # He has variously called these "pre profit" and "unprofitable", which mean rather
    # different things, so the sheet should not be the place that decides.
    pre_profit_label: str = "Pre-Profit"

    def __post_init__(self) -> None:
        if self.exit_value > self.warning_value:
            raise ValueError(
                f"exit_value ({self.exit_value}) must not exceed warning_value "
                f"({self.warning_value}) — an exit is more serious than a warning."
            )

    def describe(self) -> list[tuple[str, str, object, str]]:
        """(key, human label, value, explanation) — the scalar rows of the Settings sheet."""
        return [
            ("mover_score_pct", "Movers alert: AJZ Score moved more than",
             self.mover_score_pct,
             "Percent change since the last refresh. Your change request said 25%."),
            ("mover_pe_pct", "Movers alert: Forward P/E moved more than", self.mover_pe_pct,
             "Percent change since the last refresh. Your change request said 10%."),
            ("buy_value", "BUY alert: AJZ Value above", self.buy_value,
             "Raise this to make BUY alerts rarer."),
            ("warning_value", "WARNING alert: AJZ Value below", self.warning_value,
             "Raise or lower this to make warnings rarer or more common."),
            ("exit_value", "EXIT alert: AJZ Value below", self.exit_value,
             "Must not be above the WARNING number — an exit is the more serious call."),
            ("pre_profit_label", "Name for companies with no forward P/E",
             self.pre_profit_label,
             "These are ranked on AJZ Score alone and never enter the averages."),
        ]


DEFAULT_THRESHOLDS = Thresholds()

# Text settings are parsed as words; everything else scalar is parsed as a number.
# Kept explicit rather than inferred from the annotation so that adding a field cannot
# silently change how an existing one is read.
_TEXT_FIELDS = {"pre_profit_label"}

_SCALAR_FIELDS = {
    f.name for f in fields(Thresholds) if not f.name.endswith("_bands")
}


def from_mapping(values: dict[str, object]) -> tuple[Thresholds, list[str]]:
    """Build Thresholds from whatever was typed into the Settings sheet.

    Returns the thresholds plus any warnings. Never raises on bad input: a typo in one
    cell falls back to that field's default rather than stopping the refresh. Jeff
    refreshes on demand with nobody to call, so a dashboard that quietly used a default
    and said so beats no dashboard at all.
    """
    warnings: list[str] = []
    kwargs: dict[str, object] = {}

    for key, raw in (values or {}).items():
        if key.startswith(TABLE_PREFIX) or key not in _SCALAR_FIELDS:
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if key in _TEXT_FIELDS:
            kwargs[key] = str(raw).strip()
            continue
        try:
            kwargs[key] = float(str(raw).strip().rstrip("%"))
        except (TypeError, ValueError):
            warnings.append(f"Settings: '{key}' was not a number; using the default")

    for attr, title, default in BAND_TABLES:
        rows = values.get(f"{TABLE_PREFIX}{attr}") if values else None
        if not rows:
            continue  # sheet predates the tables, or he cleared them -> shipped defaults
        table, table_warnings = BandTable.from_rows(title, list(rows), fallback=default)
        warnings.extend(table_warnings)
        kwargs[attr] = table

    try:
        return Thresholds(**kwargs), warnings
    except ValueError as exc:
        warnings.append(f"Settings: {exc} Using defaults instead.")
        # Keep his tables even when a scalar is contradictory: the two are independent
        # judgements, and throwing away seven good bands over one bad number is worse
        # than the bad number.
        keep = {k: v for k, v in kwargs.items()
                if k.endswith("_bands") or k in _TEXT_FIELDS}
        return replace(DEFAULT_THRESHOLDS, **keep), warnings
