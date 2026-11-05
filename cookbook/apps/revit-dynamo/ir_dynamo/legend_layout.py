"""The layout of a legend view: colour swatches and text lines. No Revit import.

``ir_revit.revit_legend`` draws it in a Revit drafting view (filled regions and
text notes). Sizes are paper millimetres; the view is drawn at scale 1:1.

Rows, top to bottom: the title, then one swatch + range per bin, the highest
value at the top (as the platform legend), then the notes. A class scale (PWC)
shows the class name instead of the range, the first class at the top.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from . import colors

SWATCH_W_MM = 12.0
SWATCH_H_MM = 6.0
ROW_MM = 7.0
TEXT_X_MM = 16.0
TITLE_GAP_MM = 10.0
NOTE_ROW_MM = 5.0


@dataclass(frozen=True)
class Swatch:
    """A filled rectangle: lower-left corner and size in mm, and its colour."""

    x: float
    y: float
    w: float
    h: float
    rgb: Tuple[int, int, int]


@dataclass(frozen=True)
class Text:
    """A text line: its top-left point in mm."""

    x: float
    y: float
    text: str


def range_texts(bins: Sequence[colors.Bin], unit: str) -> List[str]:
    """``"2 to 4 m/s"`` for each bin, low -> high.

    The bins come from sampled colours, so a bin ends a little before the next one
    starts (1.996 and 2.035). The edge between two bins is their middle, rounded to
    one digit more than the smallest bin width: 0 to 2, 2 to 4 (wind speed), 0.1 to
    0.2 (sky view factor). "to", not "-": "0 - 2" read as a negative number.
    """
    if not bins:
        return []
    edges = [bins[0].low] + [0.5 * (a.high + b.low) for a, b in zip(bins, bins[1:])] + [bins[-1].high]
    widths = [hi - lo for lo, hi in zip(edges, edges[1:]) if hi > lo]
    digits = max(0, 1 - int(math.floor(math.log10(min(widths))))) if widths else 3

    def text(x: float) -> str:
        out = "%.*f" % (digits, x)
        out = out.rstrip("0").rstrip(".") if "." in out else out
        return "0" if out in ("-0", "") else out

    return [("%s to %s %s" % (text(lo), text(hi), unit)).rstrip() for lo, hi in zip(edges, edges[1:])]


def legend_layout(
    legend: colors.Legend,
    title: str,
    unit: str,
    target: str,
    notes: Sequence[str] = (),
) -> Tuple[List[Swatch], List[Text]]:
    """The swatches and texts of one legend.

    Parameters
    ----------
    legend : colors.Legend
        The bins (low -> high) with their colours and value ranges.
    title, unit, target : str
        For the title line, for example ``"Wind speed (m/s), ground"``.
    notes : sequence of str
        Lines under the swatches (the range used, the platform range).
    """
    swatches: List[Swatch] = []
    classes = bool(legend.labels)
    head = "%s, %s" % (title, target) if classes else "%s (%s), %s" % (title, unit, target)
    texts: List[Text] = [Text(0.0, 0.0, head)]
    top = -TITLE_GAP_MM
    if classes:
        rows = list(zip(legend.bins, legend.labels))
    else:  # the highest value on top
        rows = list(reversed(list(zip(legend.bins, range_texts(legend.bins, unit)))))
    for row, (b, text) in enumerate(rows):
        y = top - row * ROW_MM
        swatches.append(Swatch(0.0, y - SWATCH_H_MM, SWATCH_W_MM, SWATCH_H_MM, b.rgb))
        texts.append(Text(TEXT_X_MM, y - 1.0, text))
    y = top - len(legend.bins) * ROW_MM - 2.0
    for k, note in enumerate(notes):
        texts.append(Text(0.0, y - k * NOTE_ROW_MM, note))
    return swatches, texts
