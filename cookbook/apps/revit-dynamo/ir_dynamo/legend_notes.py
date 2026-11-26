"""Lines about a legend that help the user read the colours. No Revit import."""

from __future__ import annotations

from typing import Any, List

import numpy as np

ONE_COLOUR_SHARE = 0.8  # one_colour_note: this share of the values in one bin


def one_colour_note(legend: Any, values: Any, fixed: Any) -> List[str]:
    """A line when the platform's fixed range puts most values in one colour.

    ``legend`` is a ``colors.Legend``; ``fixed`` the registry's fixed range or
    None. UTCI is always -40 .. 46 degC on the platform, in 7 flat colours: a
    summer run of 21 .. 28 degC is one colour (tester run, 2026-11-24). The
    line says how to see the variation. Nothing without a fixed range: the
    platform then colours over the trimmed range already.
    """
    if fixed is None or values is None or len(legend.bins) < 2:
        return []
    v = np.asarray(values, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return []
    counts = np.bincount(legend.bin_of(v), minlength=len(legend.bins))
    share = float(counts.max()) / len(v)
    if share < ONE_COLOUR_SHARE:
        return []
    return [
        "Warning: %.0f %% of the values (%.4g .. %.4g) are in one colour of the platform "
        "scale (%.4g .. %.4g). To see the variation: show-last legend trimmed (free)."
        % (100.0 * share, float(v.min()), float(v.max()), float(fixed[0]), float(fixed[1]))
    ]
