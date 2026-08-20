"""Jeff's tunable decision thresholds (spec §6.5).

A deliberate line runs through this module:

  * **The FORMULA is not adjustable.** AJZ Score's weights — 2x revenue growth, 0.5x ROIC
    — are AJZ Rule 3.0 itself. Jeff wrote "Keep Unchanged" next to them, and changing them
    changes what a score *means*, breaking comparability with every past snapshot.

  * **The DECISION thresholds ARE adjustable.** Where "high AJZ" starts, what triggers a
    warning, which conviction level counts as Core — those are investment judgements, they
    are his domain, and he will want to move them as he learns.

Without this, every tweak is a phone call to Dave, and a walk-away handoff that needs Dave
is not a walk-away handoff. That is worth one extra editable sheet.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Thresholds:
    """The cut-offs that turn scores into decisions.

    Defaults reproduce Jeff's original framework exactly, so an untouched Settings sheet
    behaves precisely as his Copilot chat described.
    """

    # --- Opportunity Matrix
    strong_value: float = 7.0        # AJZ Value at or above this is "high AJZ"
    core_conviction: int = 21        # conviction for Core Holding
    aggressive_conviction: int = 16  # conviction for Aggressive Position

    # --- Alerts
    buy_value: float = 7.0
    buy_conviction: int = 20
    warning_value: float = 5.0
    exit_value: float = 3.0
    exit_conviction: int = 15
    mover_places: int = 5            # rank change that counts as an upgrade/downgrade

    def __post_init__(self) -> None:
        if self.core_conviction < self.aggressive_conviction:
            raise ValueError(
                f"core_conviction ({self.core_conviction}) must be at least "
                f"aggressive_conviction ({self.aggressive_conviction}) — otherwise no "
                "stock can ever be an Aggressive Position."
            )
        if self.exit_value > self.warning_value:
            raise ValueError(
                f"exit_value ({self.exit_value}) must not exceed warning_value "
                f"({self.warning_value}) — an exit is more serious than a warning."
            )

    @property
    def aggressive_is_reachable(self) -> bool:
        """Whether the Aggressive band is a real range or a closed door.

        When core_conviction == aggressive_conviction the band has zero width and no
        stock can ever land there. Worth detecting rather than leaving Jeff to wonder why
        a bucket is permanently empty — which is exactly what happened with the live data.
        """
        return self.core_conviction > self.aggressive_conviction

    def describe(self) -> list[tuple[str, str, object, str]]:
        """(key, human label, value, explanation) — drives the Settings sheet."""
        return [
            ("strong_value", "High AJZ Value starts at", self.strong_value,
             "Above this counts as a high score. Lower it if too few stocks qualify."),
            ("core_conviction", "Core Holding needs conviction of", self.core_conviction,
             "Your 'Very High' band starts at 21."),
            ("aggressive_conviction", "Aggressive Position needs conviction of",
             self.aggressive_conviction,
             "Must be below the Core number, or nothing can ever be Aggressive."),
            ("buy_value", "BUY alert: AJZ Value above", self.buy_value,
             "Both this and the conviction test must pass."),
            ("buy_conviction", "BUY alert: conviction above", self.buy_conviction, ""),
            ("warning_value", "WARNING alert: AJZ Value below", self.warning_value,
             "Raise or lower this to make warnings rarer or more common."),
            ("exit_value", "EXIT alert: AJZ Value below", self.exit_value,
             "Both this and the conviction test must pass."),
            ("exit_conviction", "EXIT alert: conviction below", self.exit_conviction, ""),
            ("mover_places", "Rank move that counts as a big change", self.mover_places,
             "Places gained or lost in a week."),
        ]


DEFAULT_THRESHOLDS = Thresholds()

_INT_FIELDS = {"core_conviction", "aggressive_conviction", "buy_conviction",
               "exit_conviction", "mover_places"}


def from_mapping(values: dict[str, object]) -> tuple[Thresholds, list[str]]:
    """Build Thresholds from whatever was typed into the Settings sheet.

    Returns the thresholds plus any warnings. Never raises on bad input: a typo in one
    cell falls back to that field's default rather than stopping the morning refresh.
    A dashboard that silently uses a default is far better than no dashboard.
    """
    warnings: list[str] = []
    kwargs: dict[str, object] = {}
    valid = {f.name for f in fields(Thresholds)}

    for key, raw in (values or {}).items():
        if key not in valid:
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            number = float(str(raw).strip())
        except (TypeError, ValueError):
            warnings.append(f"Settings: '{key}' was not a number; using the default")
            continue
        kwargs[key] = int(number) if key in _INT_FIELDS else number

    try:
        thresholds = Thresholds(**kwargs)
    except ValueError as exc:
        warnings.append(f"Settings: {exc} Using defaults instead.")
        return DEFAULT_THRESHOLDS, warnings

    if not thresholds.aggressive_is_reachable:
        warnings.append(
            "Settings: Aggressive Position can never be reached with these numbers — "
            "the Core and Aggressive conviction levels are equal."
        )
    return thresholds, warnings
