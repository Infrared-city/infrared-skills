"""Text lines that describe a result and its legend, for the Watch node and the log.

No Revit import (tested with pytest).
"""

from __future__ import annotations

from typing import Any, Dict, List

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
