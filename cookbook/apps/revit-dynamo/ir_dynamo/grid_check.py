"""Check where the ground matrix sits: does the SDK rule put the no-data cells under the buildings?

The SDK docs place a ground grid by its ``bounds``: row 0 is the south edge, and
cell ``(r, c)`` has its centre ``(c + 0.5, r + 0.5)`` cells from the SW corner.
``results.ground_points`` follows that rule. This check scores it, and the
shifts of one cell around it, on each real result: the server leaves the cells
inside a building without a value (NaN), so the right placement puts the most
building points into NaN cells. A line in the Watch text gives the scores.

Building points: the centre of each flat (roof or floor) triangle above the
ground, its corners moved 40 % towards that centre, and the points of a
``LATTICE_M`` lattice inside the larger triangles. A lattice point is at least
half a step from the outline, so one cell of shift moves the points near the
outline out of the no-data cells. No Revit import.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from . import frame as frame_mod

SHIFTS = (-1, 0, 1)
FLAT = 0.9  # |normal z| of a roof or floor triangle
ABOVE_M = 0.5  # flat triangles at the ground (a slab on grade) are not used
LATTICE_M = 0.5
MAX_LATTICE_TRIANGLES = 20000  # the largest ones; enough for a check


def _lattice(tri: np.ndarray) -> np.ndarray:
    """Points of a ``LATTICE_M`` lattice (offset half a step) inside one triangle (xy)."""
    a, b, c = tri[0, :2], tri[1, :2], tri[2, :2]
    low, high = tri[:, :2].min(axis=0), tri[:, :2].max(axis=0)
    xs = np.arange(low[0] + LATTICE_M / 2, high[0], LATTICE_M)
    ys = np.arange(low[1] + LATTICE_M / 2, high[1], LATTICE_M)
    if xs.size == 0 or ys.size == 0:
        return np.zeros((0, 2))
    p = np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)
    v0, v1, v2 = c - a, b - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    den = d00 * d11 - d01 * d01
    if den == 0:
        return np.zeros((0, 2))
    d20, d21 = v2 @ v0, v2 @ v1
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    return p[(u >= 0) & (v >= 0) & (u + v <= 1)]


def building_points(buildings: Dict[str, dict]) -> np.ndarray:
    """``(n, 2)`` points, SDK-frame metres, inside the building footprints."""
    out = []
    for mesh in buildings.values():
        xyz = np.asarray(mesh["coordinates"], dtype=np.float64).reshape(-1, 3)
        tri = xyz[np.asarray(mesh["indices"], dtype=np.int64).reshape(-1, 3)]
        normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(normal, axis=1)
        centre = tri.mean(axis=1)
        keep = (length > 0) & (np.abs(normal[:, 2]) >= FLAT * length) & (centre[:, 2] > ABOVE_M)
        if not keep.any():
            continue
        tri, centre = tri[keep], centre[keep]
        inner = tri + 0.4 * (centre[:, None, :] - tri)
        out.append(np.concatenate([centre[:, :2], inner[:, :, :2].reshape(-1, 2)]))
        area = 0.5 * length[keep]
        for k in np.argsort(-area)[:MAX_LATTICE_TRIANGLES]:
            if area[k] < LATTICE_M * LATTICE_M:
                break
            out.append(_lattice(tri[k]))
    return np.concatenate(out) if out else np.zeros((0, 2))


def scores(
    no_data: np.ndarray,
    corner: Tuple[float, float],
    cell: Tuple[float, float],
    points: np.ndarray,
) -> Tuple[Dict[Tuple[int, int], float], int]:
    """Share of building cells that are no data, per ``(shift_x, shift_y)`` in cells.

    A shift ``s`` puts the centre of cell ``i`` at ``(i + 0.5 + s)`` cells from
    the corner. Returns the scores and the number of building cells (shift 0).
    """
    rows, cols = no_data.shape
    out: Dict[Tuple[int, int], float] = {}
    counted = 0
    for sx in SHIFTS:
        for sy in SHIFTS:
            col = np.floor((points[:, 0] - corner[0]) / cell[0] - sx).astype(np.int64)
            row = np.floor((points[:, 1] - corner[1]) / cell[1] - sy).astype(np.int64)
            inside = (row >= 0) & (row < rows) & (col >= 0) & (col < cols)
            unique = np.unique(row[inside] * cols + col[inside])
            if unique.size == 0:
                continue
            out[(sx, sy)] = float(no_data.reshape(-1)[unique].mean())
            if (sx, sy) == (0, 0):
                counted = int(unique.size)
    return out, counted


def alignment_lines(
    frame: frame_mod.SiteFrame, result: Any, buildings: Dict[str, dict]
) -> List[str]:
    """The text lines of the check for one ground result (empty if it cannot run)."""
    grid = np.asarray(result.physical_grid(), dtype=np.float64)
    points = building_points(buildings)
    if grid.size == 0 or len(points) == 0 or result.bounds is None:
        return []
    cell = frame_mod.grid_cell_m(result.bounds, grid.shape)
    corner = frame_mod.grid_corner_sdk(frame, result.bounds)
    found, counted = scores(~np.isfinite(grid), corner, cell, points)
    if not found:
        return []
    best = max(found, key=lambda k: (found[k], -abs(k[0]) - abs(k[1])))

    def pct(key: Tuple[int, int]) -> str:
        return "%.0f %%" % (100.0 * found[key]) if key in found else "n/a"

    lines = [
        "Grid alignment check (%d cells under buildings; share without a value): "
        "SDK rule: %s; best: x %+d, y %+d cell(s): %s."
        % (counted, pct((0, 0)), best[0], best[1], pct(best))
    ]
    if found[best] > found.get((0, 0), 0.0):
        lines.append(
            "Warning: the ground grid may be one cell off here. Please report this line."
        )
    return lines
