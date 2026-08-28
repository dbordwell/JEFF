"""Visual design tokens for the workbook.

Colour assignment follows the dataviz method: pick the encoding by the *job* the
colour does, then use the matching palette family. Three distinct jobs appear here
and they deliberately do not share colours.

1. AJZ rating bands (Elite > Excellent > Strong > Good > Fair > Weak)
   -> ORDINAL MAGNITUDE, so a SEQUENTIAL single-hue ramp, light to dark.

   Copilot's original spec used a rainbow for these bands (green/blue/yellow/
   orange/red). That is the classic anti-pattern for ordered data: a rainbow implies
   category, not rank, so nothing about the colour tells you Elite beats Good. A
   one-hue ramp encodes the ordering in the colour itself.

2. Alerts (BUY / UPGRADE / WARNING / EXIT / DOWNGRADE)
   -> STATUS, which has its own reserved palette. Status colours are never reused as
   category colours, and never carry meaning alone: every cell also holds its label.

3. Opportunity Matrix buckets -> CATEGORICAL IDENTITY, assigned in fixed slot order.
   "Avoid" takes a recessive neutral rather than status-red: it is a category, not an
   error state, and status red is reserved.

Hex values are the dataviz reference palette. openpyxl wants ARGB, so everything is
stored pre-prefixed with "FF".
"""

from __future__ import annotations


def _argb(hex6: str) -> str:
    return "FF" + hex6.upper().lstrip("#")


# --- Ink and surface -----------------------------------------------------------------
INK_PRIMARY = _argb("0b0b0b")
INK_SECONDARY = _argb("52514e")
INK_MUTED = _argb("8a8985")
INK_INVERSE = _argb("ffffff")

SURFACE = _argb("fcfcfb")
NEUTRAL_FILL = _argb("f0efec")
HEADER_FILL = _argb("0d366b")  # sequential blue step 700, for table headers
RULE = _argb("d8d7d2")

# --- 1. Sequential ramp: category bands ----------------------------------------------
# Blue 450 -> 100, then a neutral tail. Dark to light == best to worst, so rank is
# legible without reading the word. Text colour flips on the darkest step only.
#
# Keyed by POSITION, not by label. Jeff owns the band names now and demonstrably changes
# them ("Fair" -> "Fair to Poor" between v2.0 and v2.1), and he owns how many there are
# (v2.1 added two). A palette keyed on the words would silently lose its colour the first
# time he retyped one, and would mis-colour the rest: his "Elite" is the second band of
# seven, where the old label-keyed map had "Elite" as the best of six. Position is the
# only thing about a band that we still define.
_RAMP: tuple[tuple[str | None, str], ...] = (
    (_argb("2a78d6"), INK_INVERSE),    # step 450
    (_argb("6da7ec"), INK_PRIMARY),    # step 300
    (_argb("9ec5f4"), INK_PRIMARY),    # step 200
    (_argb("cde2fb"), INK_PRIMARY),    # step 100
    (NEUTRAL_FILL, INK_SECONDARY),
    (None, INK_MUTED),                 # no fill: the worst band recedes, never shouts
)


def band_style(index: int, total: int) -> tuple[str | None, str]:
    """(fill, ink) for the band at `index` of `total`, best first.

    Any number of bands is stretched across the six ramp steps, so a five-band table and
    a nine-band table both read best-to-worst at a glance. The label is always in the
    cell as well: colour adds speed here and never carries meaning alone, which matters
    because roughly one man in twelve cannot separate the warm end of a ramp reliably.
    """
    if total <= 1:
        return _RAMP[0]
    step = round(index * (len(_RAMP) - 1) / (total - 1))
    return _RAMP[min(step, len(_RAMP) - 1)]



# --- 2. Status palette (reserved; never used for categories) --------------------------
STATUS_GOOD = _argb("0ca30c")
STATUS_WARNING = _argb("fab219")
STATUS_SERIOUS = _argb("ec835a")
STATUS_CRITICAL = _argb("d03b3b")

# Direction of travel on the Movers sheet. Deliberately the muted status inks rather than
# a saturated red/green pair: a stock moving is news, not an emergency, and the sheet
# would otherwise read as a wall of alarm on any volatile week. The sign is always in the
# text of the cell too, so the colour is never the only thing carrying the direction.
INK_POSITIVE = _argb("0a7d0a")
INK_NEGATIVE = _argb("b03030")

ALERT_FILL: dict[str, str] = {
    "BUY": STATUS_GOOD,
    "UPGRADE": STATUS_GOOD,
    "WARNING": STATUS_WARNING,
    "DOWNGRADE": STATUS_SERIOUS,
    "EXIT": STATUS_CRITICAL,
}

ALERT_INK: dict[str, str] = {
    "BUY": INK_INVERSE,
    "UPGRADE": INK_INVERSE,
    "WARNING": INK_PRIMARY,  # warning is sub-3:1 on light; dark ink + label is the fix
    "DOWNGRADE": INK_PRIMARY,
    "EXIT": INK_INVERSE,
}

# --- Banner (spec §10) ----------------------------------------------------------------
BANNER_FILL: dict[str, str] = {
    "ok": _argb("0ca30c"),
    "partial": _argb("0ca30c"),
    "stale": _argb("fab219"),
    "quota": _argb("fab219"),
    "auth_error": _argb("d03b3b"),
}

BANNER_INK: dict[str, str] = {
    "ok": INK_INVERSE,
    "partial": INK_INVERSE,
    "stale": INK_PRIMARY,
    "quota": INK_PRIMARY,
    "auth_error": INK_INVERSE,
}

FONT = "Calibri"  # universally present on Windows + macOS Excel; sans-serif in both.
