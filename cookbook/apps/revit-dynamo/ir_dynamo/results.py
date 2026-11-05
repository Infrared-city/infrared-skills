"""SDK results -> plain data in the Revit frame.

Both functions return a dict with lists and numbers only:

ground: ``{"kind": "points", "points": [[x, y, z], ...], "values": [...],
           "cell_m": float, "legend_min", "legend_max",
           "grid_shape": [rows, cols], "cells": [[row, col], ...] (the place of
           each value in the SDK matrix; row 0 is the south edge),
           "corner_z": [[sw, se, ne, nw], ...] (only with terrain),
           "labels": [class names in code order] (only for a class result, PWC)}``
facades: ``{"kind": "triangles", "triangles": [x, y, z, ...] (9 per triangle),
            "values": [one per triangle], "legend_min", "legend_max"}``

Coordinates are Revit-frame metres. ``z_offset`` is added back to every z.
Cells without a value are left out.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
from infrared_sdk.legend import legend_range

from . import frame as frame_mod
from . import terrain as terrain_mod


def _legend(values: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    # The SDK measures the legend range (exact min and max of the finite values).
    found = legend_range(values, "exact") if values.size else None
    return (None, None) if found is None else (found[0], found[1])


def ground_points(
    frame: frame_mod.SiteFrame,
    result: Any,
    z_offset: float = 0.0,
    sampler: Optional[terrain_mod.Sampler] = None,
) -> Dict[str, Any]:
    """The ground grid of an ``AreaResult``: one point at the centre of each valid cell.

    The SDK result has no per-cell height. With a ``sampler`` (the terrain in the
    Revit frame) each cell gets the terrain height at its four corners
    (``corner_z``), so the display can follow the slope; ``z`` of the point is
    their mean. Without it every cell sits at ``z_offset``.
    """
    grid = np.asarray(result.physical_grid(), dtype=np.float64)
    rows, cols = grid.shape
    cell_x, cell_y = frame_mod.grid_cell_m(result.bounds, (rows, cols))
    row, col = np.nonzero(np.isfinite(grid))  # row 0 is the south
    xyz = np.empty((row.size, 3), dtype=np.float64)
    corner_x, corner_y = frame_mod.grid_corner_sdk(frame, result.bounds)
    # The SDK rule: cell (row, col) has its centre (col + 0.5, row + 0.5) cells
    # from the SW corner of ``bounds``; ``grid_check`` confirms it on each run.
    xyz[:, 0] = corner_x + (col + 0.5) * cell_x
    xyz[:, 1] = corner_y + (row + 0.5) * cell_y
    xyz[:, 2] = 0.0
    moved = frame_mod.points_to_revit(frame, xyz.reshape(-1)).reshape(-1, 3)
    moved[:, 2] += z_offset
    corner_z = None
    if sampler is not None and len(moved):
        corners = terrain_mod.corner_heights(moved, cell_x, sampler)
        moved[:, 2] = corners.mean(axis=1)
        corner_z = corners.tolist()
    values = grid[row, col]
    low, high = _legend(values)
    out = {
        "kind": "points",
        "points": moved.tolist(),
        "values": values.tolist(),
        "cell_m": float(cell_x),
        "legend_min": low,
        "legend_max": high,
        "grid_shape": [int(rows), int(cols)],
        "cells": np.stack([row, col], axis=1).tolist(),
    }
    if corner_z is not None:
        out["corner_z"] = corner_z
    labels = getattr(result, "legend", None)
    if labels:  # PWC: the class of each code
        out["labels"] = [str(x) for x in labels]
    return out


def facade_triangles(
    frame: frame_mod.SiteFrame, result: Any, z_offset: float = 0.0
) -> Dict[str, Any]:
    """The walls and roofs of a ``SurfaceAnalysisResult``: the triangles of each valid cell.

    Needs a run with ``emit_cell_tris=True`` (``payloads.build_payload`` sets it).
    """
    columns = result.columns
    tris = None if columns is None else columns.triangles
    if tris is None:
        raise RuntimeError(
            "The result has no cell triangles. Run again with emit_cell_tris."
        )
    values = np.asarray(
        columns.physical_values(0, int(columns.cell_offsets[-1])), dtype=np.float64
    )
    per_cell = np.diff(np.asarray(tris.cell_offsets, dtype=np.int64))
    keep = np.isfinite(values) & (np.asarray(tris.drawn) > 0) & (per_cell > 0)
    # One array of vertices for all groups, each group moved by its tile anchor.
    groups = [
        frame_mod.tile_to_site(pos, tris.anchors[g])
        for g, pos in enumerate(tris.positions)
    ]
    xyz = np.concatenate(groups) if groups else np.zeros((0, 3))
    tri_keep = np.repeat(keep, per_cell)
    tri_values = np.repeat(values, per_cell)[tri_keep]
    xyz = xyz.reshape(-1, 3, 3)[tri_keep].reshape(-1, 3)
    moved = frame_mod.points_to_revit(frame, xyz.reshape(-1)).reshape(-1, 3)
    moved[:, 2] += z_offset
    low, high = _legend(values[keep])
    return {
        "kind": "triangles",
        "triangles": moved.reshape(-1).tolist(),
        "values": tri_values.tolist(),
        "legend_min": low,
        "legend_max": high,
    }
