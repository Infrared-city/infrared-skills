"""A result as coloured triangles in site metres. Pure, no Rhino import.

The colours are the platform colours, the same as in Revit: ``ir_dynamo.colors``
makes the legend, ``ir_dynamo.cell_colors`` gives each value its colour, and
``ir_revit.result_mesh`` (pure numpy despite its package) makes the triangles.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Tuple

import numpy as np

from ir_dynamo import cell_colors, colors
from ir_revit import result_mesh


# The legend range when the command names none: the SDK's own default, the result's
# min_legend .. max_legend ("exact"). The Revit default "platform" is the registry's fixed
# UTCI scale (-40 .. 46 degC in 7 bins): a July afternoon in Vienna (23 .. 28 degC) was
# one colour (live run 2026-11-20).
SDK_RANGE_MODE = "exact"


def with_look(cmd: Any, text: str) -> Any:
    """``cmd`` with the SDK's default legend range when ``text`` names no range mode."""
    words = str(text).lower().split()
    if cmd.legend == colors.DEFAULT_RANGE_MODE and colors.DEFAULT_RANGE_MODE not in words:
        return replace(cmd, legend=SDK_RANGE_MODE)
    return cmd


def without_look(cmd: Any) -> Any:
    """``cmd`` without its legend and gradient: two runs equal here have the same result."""
    return replace(cmd, legend=colors.DEFAULT_RANGE_MODE, gradient=False)


def coloured(
    result: Dict[str, Any], analysis_type: str, range_mode: str = "", gradient: bool = False
) -> Tuple[np.ndarray, np.ndarray, Any, List[str]]:
    """``(triangles (n, 3, 3) site metres, rgb (n, 3) int, legend, warning lines)``."""
    legend, notes = colors.make_legend(
        analysis_type,
        result["legend_min"],
        result["legend_max"],
        values=result["values"],
        range_mode=range_mode,
        gradient=gradient,
    )
    palette, index, more = cell_colors.cell_colors(
        analysis_type,
        result["values"],
        result["legend_min"],
        result["legend_max"],
        range_mode,
        legend,
        result.get("grid_shape"),
        result.get("cells"),
        gradient=gradient,
    )
    tri, bins = result_mesh.coloured_triangles(result, index)
    rgb = np.asarray(palette, dtype=np.int64).reshape(-1, 3)[np.asarray(bins, dtype=np.int64)]
    return tri, rgb, legend, list(notes) + list(more)
