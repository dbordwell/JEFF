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

# --- 1. Sequential ramp: AJZ rating bands --------------------------------------------
# Blue 450 -> 100, then a neutral tail. Dark to light == best to worst, so rank is
# legible without reading the word. Text colour flips on the darkest step only.
AJZ_BAND_FILL: dict[str, str] = {
    "Elite": _argb("2a78d6"),  # step 450
    "Excellent": _argb("6da7ec"),  # step 300
    "Strong": _argb("9ec5f4"),  # step 200
    "Good": _argb("cde2fb"),  # step 100
    "Fair": NEUTRAL_FILL,
    "Weak": None,  # no fill: the worst band should recede, not shout
}

AJZ_BAND_INK: dict[str, str] = {
    "Elite": INK_INVERSE,
    "Excellent": INK_PRIMARY,
    "Strong": INK_PRIMARY,
    "Good": INK_PRIMARY,
    "Fair": INK_SECONDARY,
    "Weak": INK_MUTED,
}

# Conviction bands reuse the same ramp. Same job (ordinal magnitude), same encoding —
# and reusing it means Jeff learns one visual language, not two.
CONVICTION_BAND_FILL: dict[str, str] = {
    "Very High": _argb("2a78d6"),
    "High": _argb("9ec5f4"),
    "Medium": _argb("cde2fb"),
    "Low": NEUTRAL_FILL,
}

CONVICTION_BAND_INK: dict[str, str] = {
    "Very High": INK_INVERSE,
    "High": INK_PRIMARY,
    "Medium": INK_PRIMARY,
    "Low": INK_SECONDARY,
}

# --- 2. Status palette (reserved; never used for categories) --------------------------
STATUS_GOOD = _argb("0ca30c")
STATUS_WARNING = _argb("fab219")
STATUS_SERIOUS = _argb("ec835a")
STATUS_CRITICAL = _argb("d03b3b")

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

# --- 3. Categorical: Opportunity Matrix buckets ---------------------------------------
# Fixed slot order from the reference palette: 1 blue, 2 orange, 3 aqua, 4 yellow.
# Every cell carries its text label, which is the required relief for the yellow/orange
# pairing and for the sub-3:1 light-surface slots.
CATEGORY_FILL: dict[str, str] = {
    "Core Holding": _argb("2a78d6"),  # slot 1
    "Aggressive Position": _argb("eb6834"),  # slot 2
    "Defensive Compounder": _argb("1baf7a"),  # slot 3
    "Needs Conviction": _argb("eda100"),  # slot 4 — an action item, not a verdict
    "Avoid": NEUTRAL_FILL,  # recessive; status-red is reserved
    "Not Rated": None,
}

CATEGORY_INK: dict[str, str] = {
    "Core Holding": INK_INVERSE,
    "Aggressive Position": INK_INVERSE,
    "Defensive Compounder": INK_INVERSE,
    "Needs Conviction": INK_PRIMARY,
    "Avoid": INK_SECONDARY,
    "Not Rated": INK_MUTED,
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
