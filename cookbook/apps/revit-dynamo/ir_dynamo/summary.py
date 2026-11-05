"""Text lines that describe a result and its legend, for the Watch node and the log.

No Revit import (tested with pytest).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Sequence

import numpy as np

from . import colors

PERCENTILES = (2, 10, 25, 50, 75, 90, 98)


def _num(value: float) -> str:
    return "%.4g" % value


def value_lines(result: Dict[str, Any], target: str, unit: str) -> List[str]:
    """The statistics of the result values: count, min, max, mean, percentiles.

    ``legend_min`` / ``legend_max`` are the range that came with the SDK result.
    """
    v = np.asarray(result["values"], dtype=np.float64)
    finite = v[np.isfinite(v)]
    lines = ["Result values on %s (%s): %d value(s), %d without a number."
             % (target, unit, len(v), len(v) - len(finite))]
    if len(finite) == 0:
        return lines
    pct = np.percentile(finite, PERCENTILES)
    lines.append(
        "  min %s, max %s, mean %s, median %s"
        % (_num(finite.min()), _num(finite.max()), _num(finite.mean()), _num(np.median(finite)))
    )
    lines.append(
        "  percentiles "
        + ", ".join("p%d %s" % (p, _num(x)) for p, x in zip(PERCENTILES, pct))
    )
    lo, hi = result.get("legend_min"), result.get("legend_max")
    if lo is not None and hi is not None:
        lines.append("  result legend_min .. legend_max (SDK): %s .. %s" % (_num(lo), _num(hi)))
    return lines


def legend_count_lines(
    legend: colors.Legend, values: Any, unit: str, range_mode: str
) -> List[str]:
    """The legend range in use, and per bin: colour, value range, count and share.

    For a smooth platform gradient the bin colour is the colour at the bin's
    middle; the cells themselves carry the exact SDK colour.

    Values outside the legend range are drawn in the first or last colour;
    a line gives how many.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if legend.labels:  # a class scale (PWC): the count of each class
        counts = np.bincount(legend.bin_of(v), minlength=len(legend.bins)) if len(v) else []
        total = max(len(v), 1)
        return ["Classes:"] + [
            "  %s  rgb%s: %d (%.1f %%)" % (label, b.rgb, count, 100.0 * count / total)
            for label, b, count in zip(legend.labels, legend.bins, counts)
        ]
    low, high = float(legend.ramp_values[0]), float(legend.ramp_values[-1])
    lines = [
        "Legend range used (%s): %s .. %s %s"
        % (colors.parse_range_mode(range_mode), _num(low), _num(high), unit)
    ]
    below, above = int(np.sum(v < low)), int(np.sum(v > high))
    if below or above:
        lines.append(
            "  %d value(s) below and %d above the range are drawn in the end colours."
            % (below, above)
        )
    counts = np.bincount(legend.bin_of(v), minlength=len(legend.bins)) if len(v) else []
    total = max(len(v), 1)
    for k, (b, count) in enumerate(zip(legend.bins, counts)):
        lines.append(
            "  bin %02d  rgb%s  %s .. %s %s: %d (%.1f %%)"
            % (k + 1, b.rgb, _num(b.low), _num(b.high), unit, count, 100.0 * count / total)
        )
    return lines


def selection_line(label: str, descriptions: Sequence[str], top: int = 8) -> str:
    """One line with the count of each category in a selection, the largest first.

    ``descriptions`` holds one ``"Category, Class"`` text per element
    (``ir_revit.revit_geometry.describe``). Only the category is counted.
    """
    counts = Counter(d.split(",")[0].strip() or "no category" for d in descriptions)
    parts = ["%d %s" % (n, name) for name, n in counts.most_common(top)]
    rest = len(counts) - len(parts)
    if rest > 0:
        parts.append("%d more categor%s" % (rest, "y" if rest == 1 else "ies"))
    return "%s: %d element(s)%s" % (label, len(descriptions), (": " + ", ".join(parts)) if parts else "")


def id_list_line(count_text: str, ids: Sequence[str], show: int = 5) -> str:
    """One line for many elements: ``"<n> <count_text> (ids a, b, ... and 3 more)."``.

    ``count_text`` follows the number, for example ``"element(s) are below the
    ground and are skipped"``. Empty ``ids`` gives an empty string.
    """
    if not ids:
        return ""
    shown = ", ".join(str(i) for i in list(ids)[:show])
    rest = len(ids) - min(len(ids), show)
    more = " and %d more" % rest if rest > 0 else ""
    return "%d %s (ids %s%s)." % (len(ids), count_text, shown, more)


def share_line(label: str, counts: Dict[str, int], top: int = 8) -> str:
    """``"<label>: Walls 600000 (30 %), ..."``, the largest first."""
    total = sum(counts.values())
    if total == 0:
        return "%s: none." % label
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    parts = ["%s %d (%.0f %%)" % (name, n, 100.0 * n / total) for name, n in ranked[:top]]
    if len(ranked) > top:
        parts.append("%d more" % (len(ranked) - top))
    return "%s: %s." % (label, ", ".join(parts))
