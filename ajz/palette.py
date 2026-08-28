"""Turning a fill Jeff clicked in Excel into a colour we can use.

Jeff coloured the category names on the Settings sheet himself, to make the three tables
visual. It was the right instinct in the right place, and the refresh threw it away --
the workbook is rebuilt from nothing every time, so anything we do not explicitly read
back is destroyed. This module is the read-back for colour.

Two things make it more than `cell.fill.fgColor.rgb`:

**Excel's picker mostly does not hand out RGB.** The top row of the colour picker -- the
row anyone clicks first -- stores a *slot* into the workbook's theme plus a *tint*, not a
colour. Below it sit five tinted variants of each slot, which are the same slot with a
different tint. Reading only `.rgb` would resolve the ten "Standard Colors" at the bottom
and silently ignore everything above them, which is most of what he will actually click.

**We never guess.** Anything that cannot be resolved to a real colour returns None, which
means "use our ramp". A band that keeps its old shading is a non-event; a band painted a
colour Jeff did not choose is us putting words in his mouth about his own categories.
"""

from __future__ import annotations

import colorsys
from xml.etree import ElementTree

from . import theme

_DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

# The order the theme's colour scheme is written in the XML.
_SCHEME_ORDER = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
                 "accent4", "accent5", "accent6", "hlink", "folHlink")

# The order Excel *indexes* it in. The first two pairs are swapped relative to the XML:
# theme index 0 is the light background, not the dark text. This is a genuine quirk of
# the format rather than a mistake, and getting it wrong inverts every neutral Jeff picks
# -- black text where he chose a white background.
_THEME_INDEX = ("lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3",
                "accent4", "accent5", "accent6", "hlink", "folHlink")

# Excel's legacy indexed palette. Only the entries Excel still produces are worth
# carrying; 64 and 65 mean "system foreground/background", which have no fixed value.
_INDEXED = {
    0: "000000", 1: "FFFFFF", 2: "FF0000", 3: "00FF00", 4: "0000FF", 5: "FFFF00",
    6: "FF00FF", 7: "00FFFF", 8: "000000", 9: "FFFFFF", 10: "FF0000", 11: "00FF00",
    12: "0000FF", 13: "FFFF00", 14: "FF00FF", 15: "00FFFF", 16: "800000",
    17: "008000", 18: "000080", 19: "808000", 20: "800080", 21: "008080",
    22: "C0C0C0", 23: "808080", 40: "00CCFF", 41: "CCFFFF", 42: "CCFFCC",
    43: "FFFF99", 44: "99CCFF", 45: "FF99CC", 46: "CC99FF", 47: "FFCC99",
    48: "3366FF", 49: "33CCCC", 50: "99CC00", 51: "FFCC00", 52: "FF9900",
    53: "FF6600", 54: "666699", 55: "969696", 56: "003366", 57: "339966",
    58: "003300", 59: "333300", 60: "993300", 61: "993366", 62: "333399",
    63: "333333",
}


def _argb(hex6: str) -> str:
    return "FF" + hex6.upper()


def apply_tint(hex6: str, tint: float) -> str:
    """Lighten or darken a colour the way Excel does, in HLS space.

    Tint runs -1 (black) to +1 (white) and is how the five variants under each theme
    colour in the picker are stored. Working in HLS rather than scaling RGB channels is
    what keeps the hue stable: "Accent 1, Lighter 40%" has to stay recognisably the same
    blue, and a naive channel scale drifts it toward grey.
    """
    if not tint:
        return hex6.upper()

    red, green, blue = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, lum, sat = colorsys.rgb_to_hls(red, green, blue)

    lum = lum * (1 + tint) if tint < 0 else lum * (1 - tint) + tint

    red, green, blue = colorsys.hls_to_rgb(hue, min(max(lum, 0.0), 1.0), sat)
    return "".join(f"{round(channel * 255):02X}" for channel in (red, green, blue))


def _theme_colours(wb) -> list[str]:
    """The workbook theme's twelve colour slots, in Excel's index order.

    Returns [] if the theme cannot be read, which makes every theme colour unresolvable
    and therefore falls back to the ramp -- the safe direction.
    """
    raw = getattr(wb, "loaded_theme", None)
    if not raw:
        return []

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return []

    scheme = root.find(f".//{_DRAWING_NS}clrScheme")
    if scheme is None:
        return []

    by_name: dict[str, str] = {}
    for name in _SCHEME_ORDER:
        node = scheme.find(f"{_DRAWING_NS}{name}")
        if node is None:
            continue
        srgb = node.find(f"{_DRAWING_NS}srgbClr")
        if srgb is not None and srgb.get("val"):
            by_name[name] = srgb.get("val").upper()
            continue
        # A system colour (window / windowText). `lastClr` is what Excel last rendered
        # it as, which is the only concrete value available to us.
        sys_clr = node.find(f"{_DRAWING_NS}sysClr")
        if sys_clr is not None and sys_clr.get("lastClr"):
            by_name[name] = sys_clr.get("lastClr").upper()

    if len(by_name) < len(_SCHEME_ORDER):
        return []
    return [by_name[name] for name in _THEME_INDEX]


def resolve_fill(cell, wb) -> str | None:
    """The ARGB colour of a cell's fill, or None if it has none we can trust.

    None covers every "we do not know" case as well as the plain "no fill" case, because
    both mean the same thing downstream: fall back to our ramp.
    """
    fill = getattr(cell, "fill", None)
    if fill is None or fill.patternType not in ("solid",):
        # Only solid fills. A pattern or gradient has no single colour, and Jeff has no
        # reason to reach for one; treating a gradient's first stop as "the colour" would
        # be us inventing an answer.
        return None

    colour = fill.fgColor
    if colour is None:
        return None

    kind = getattr(colour, "type", None)

    if kind == "rgb":
        value = colour.rgb
        if not isinstance(value, str):
            return None
        value = value.upper()
        if len(value) == 6:
            return "FF" + value
        if len(value) != 8:
            return None
        # Force the alpha byte opaque rather than trusting it. openpyxl pads a six-digit
        # colour with a 00 alpha, and Excel ignores alpha on fills anyway -- so a 00 here
        # means "written short", not "transparent". Reading it as transparency would
        # discard perfectly good colours; the absence of a fill is already carried by
        # patternType above.
        return "FF" + value[2:]

    if kind == "indexed":
        base = _INDEXED.get(colour.indexed)
        return _argb(base) if base else None

    if kind == "theme":
        slots = _theme_colours(wb)
        index = colour.theme
        if not slots or not isinstance(index, int) or not 0 <= index < len(slots):
            return None
        return _argb(apply_tint(slots[index], colour.tint or 0.0))

    return None


def ink_for(argb: str | None) -> str:
    """Readable text colour for a given fill.

    Jeff picks the fill; nobody should have to also pick the text colour, and if he
    chooses navy the label must not vanish into it. Relative luminance per WCAG, with the
    threshold set where the contrast ratio against each ink is equal.
    """
    if not argb or len(argb) < 8:
        return theme.INK_PRIMARY

    channels = []
    for offset in (2, 4, 6):
        try:
            value = int(argb[offset:offset + 2], 16) / 255
        except ValueError:
            return theme.INK_PRIMARY
        channels.append(value / 12.92 if value <= 0.04045
                        else ((value + 0.055) / 1.055) ** 2.4)

    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return theme.INK_PRIMARY if luminance > 0.36 else theme.INK_INVERSE
