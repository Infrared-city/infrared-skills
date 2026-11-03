"""The layout of a legend view: colour swatches and text lines. No Revit import.

``ir_revit.revit_legend`` draws it in a Revit drafting view (filled regions and
text notes). Sizes are paper millimetres; the view is drawn at scale 1:1.

Rows, top to bottom: the title, then one swatch + range per bin, the highest
value at the top (as the platform legend), then the notes.
"""

from __future__ import annotations

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


def _num(value: float) -> str:
    return "%.3g" % value


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
    texts: List[Text] = [Text(0.0, 0.0, "%s (%s), %s" % (title, unit, target))]
    top = -TITLE_GAP_MM
    for row, b in enumerate(reversed(legend.bins)):
        y = top - row * ROW_MM
        swatches.append(Swatch(0.0, y - SWATCH_H_MM, SWATCH_W_MM, SWATCH_H_MM, b.rgb))
        texts.append(Text(TEXT_X_MM, y - 1.0, "%s - %s %s" % (_num(b.low), _num(b.high), unit)))
    y = top - len(legend.bins) * ROW_MM - 2.0
    for k, note in enumerate(notes):
        texts.append(Text(0.0, y - k * NOTE_ROW_MM, note))
    return swatches, texts
