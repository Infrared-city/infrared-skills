"""A result as coloured triangles: pure numpy, no Revit import (tested with pytest).

* ground: each grid cell becomes a square (two triangles), lifted a little,
  with its corners on the terrain when the result has ``corner_z``;
* facades: each result triangle, moved a little out of the wall.

The colour bin of each value comes from ``ir_dynamo.colors.Legend`` (the platform
colours of the SDK colour registry).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from ir_dynamo.colors import Legend

GROUND_LIFT_M = 0.05  # above the ground, so the colours do not mix with a floor
FACADE_OFFSET_M = 0.05  # out of the wall, for the same reason


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


def coloured_triangles(result: Dict[str, Any], legend: Legend) -> Tuple[np.ndarray, np.ndarray]:
    """Triangles ``(m, 3, 3)`` in Revit-frame metres and the legend bin of each one.

    A value without a bin (NaN) gets the first bin; results do not carry NaN
    (``ir_dynamo.results`` leaves such cells out).
    """
    bins = np.maximum(legend.bin_of(result["values"]), 0)
    if result["kind"] == "points":
        tri = ground_triangles(result["points"], result["cell_m"], result.get("corner_z"))
        return tri, np.repeat(bins, 2)
    return facade_triangles(result["triangles"]), bins
