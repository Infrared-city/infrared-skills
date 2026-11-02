"""A result as coloured triangles: pure numpy, no Revit import (tested with pytest).

* ground: each grid cell becomes a square (two triangles), lifted a little,
  with its corners on the terrain when the result has ``corner_z``;
* facades: each result triangle, moved a little out of the wall.

The values are put into ``BINS`` colour bins between the legend min and max.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

BINS = 10
# Low -> high (viridis stops). The bin colours are blends of these.
GRADIENT = [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]
GROUND_LIFT_M = 0.05  # above the ground, so the colours do not mix with a floor
FACADE_OFFSET_M = 0.05  # out of the wall, for the same reason


def bin_colors(count: int = BINS) -> List[Tuple[int, int, int]]:
    """``count`` colours from low to high, blended from ``GRADIENT``."""
    stops = np.asarray(GRADIENT, dtype=np.float64)
    where = np.linspace(0.0, len(stops) - 1.0, count)
    low = np.floor(where).astype(int).clip(0, len(stops) - 2)
    part = (where - low)[:, None]
    rgb = stops[low] * (1.0 - part) + stops[low + 1] * part
    return [tuple(int(round(c)) for c in row) for row in rgb]


def bin_index(values: np.ndarray, low: float, high: float, count: int = BINS) -> np.ndarray:
    """The bin (0 .. count-1) of each value. Values outside [low, high] go to the end bins."""
    if not high > low:
        return np.zeros(values.shape, dtype=int)
    scaled = (values - low) / (high - low) * count
    return np.clip(np.floor(scaled), 0, count - 1).astype(int)


def legend_lines(low: float, high: float, unit: str, count: int = BINS) -> List[str]:
    """One line per bin: its number, colour and value range."""
    edges = np.linspace(low, high, count + 1)
    colors = bin_colors(count)
    return [
        "  Infrared %02d  rgb%s  %.3g .. %.3g %s"
        % (k + 1, colors[k], edges[k], edges[k + 1], unit)
        for k in range(count)
    ]


def ground_triangles(
    points: Sequence[Sequence[float]],
    cell_m: float,
    corner_z: Optional[Sequence[Sequence[float]]] = None,
) -> np.ndarray:
    """Two triangles per cell centre: shape ``(2 * n, 3, 3)``, metres, Revit frame.

    ``corner_z`` (optional, ``(n, 4)``: SW, SE, NE, NW) is the terrain height at
    each cell corner, so the square follows the slope. Without it the square is
    flat at the z of its centre point. Both are lifted by ``GROUND_LIFT_M``.
    """
    centre = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    half = 0.5 * float(cell_m)
    if corner_z is None:
        z = np.repeat(centre[:, 2:3], 4, axis=1)
    else:
        z = np.asarray(corner_z, dtype=np.float64).reshape(-1, 4)
    z = z + GROUND_LIFT_M
    x0, x1 = centre[:, 0] - half, centre[:, 0] + half
    y0, y1 = centre[:, 1] - half, centre[:, 1] + half
    a = np.stack([x0, y0, z[:, 0]], axis=1)
    b = np.stack([x1, y0, z[:, 1]], axis=1)
    c = np.stack([x1, y1, z[:, 2]], axis=1)
    d = np.stack([x0, y1, z[:, 3]], axis=1)
    first = np.stack([a, b, c], axis=1)
    second = np.stack([a, c, d], axis=1)
    out = np.empty((2 * len(centre), 3, 3), dtype=np.float64)
    out[0::2], out[1::2] = first, second
    return out


def facade_triangles(triangles: Sequence[float]) -> np.ndarray:
    """The result triangles, each moved ``FACADE_OFFSET_M`` away from the building.

    "Away" is along the triangle normal, turned to point away from the centre of
    all triangles (good for one building or a compact group).
    """
    tri = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    if len(tri) == 0:
        return tri
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    length[length == 0.0] = 1.0
    normal /= length[:, None]
    middle = tri.mean(axis=1)
    outward = middle - middle.mean(axis=0)
    flip = np.einsum("ij,ij->i", normal, outward) < 0.0
    normal[flip] *= -1.0
    return tri + FACADE_OFFSET_M * normal[:, None, :]


def coloured_triangles(result: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """Triangles ``(m, 3, 3)`` in Revit-frame metres and the bin of each one."""
    values = np.asarray(result["values"], dtype=np.float64)
    low, high = result["legend_min"], result["legend_max"]
    if low is None or high is None:
        low, high = float(np.nanmin(values)), float(np.nanmax(values))
    bins = bin_index(values, float(low), float(high))
    if result["kind"] == "points":
        tri = ground_triangles(result["points"], result["cell_m"], result.get("corner_z"))
        return tri, np.repeat(bins, 2)
    return facade_triangles(result["triangles"]), bins
