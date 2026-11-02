"""Terrain maths: pure numpy, no Revit and no SDK import (tested with pytest).

Input is plain data, like ``meshes``: ``{element_id: flat [x, y, z, ...]}``
with 9 numbers per triangle, Revit-frame metres.

* ``prepare``: keep the upward-facing triangles that touch the work area;
* ``Sampler``: the terrain height at any (x, y), by barycentric lookup;
* ``buried``: which building triangles lie below the ground (foundations);
* ``corner_heights``: the terrain height at the four corners of each result cell.

NOTE (stop-gap): this host-side height sampler exists only because infrared-sdk
1.0.0 does not export the kernel's terrain lookup (``ir_geo::terrain_sample``
in infrared-core). When a later SDK exports it, replace ``Sampler`` by that
call and delete the loop below.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

Soup = Dict[str, Sequence[float]]

# A triangle whose normal is flatter than this (nz / length) is a wall of the
# terrain slab, not ground. 0.02 is about 89 degrees from horizontal.
MIN_UP = 0.02
# A building vertex within this distance of the ground is "on" the ground.
GROUND_TOL_M = 0.01
EPS = 1e-9


def triangles(flat: Sequence[float]) -> np.ndarray:
    """Flat xyz list -> ``(n, 3, 3)`` float64. Empty input gives ``(0, 3, 3)``."""
    array = np.asarray(flat, dtype=np.float64).reshape(-1)
    if array.size % 9 != 0:
        raise ValueError("A triangle list needs 9 numbers for each triangle.")
    return array.reshape(-1, 3, 3)


def face_up(tri: np.ndarray) -> np.ndarray:
    """Turn every triangle so its normal points up; drop vertical and empty ones."""
    if len(tri) == 0:
        return tri
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    length[length == 0.0] = np.inf
    up = normal[:, 2] / length
    out = tri.copy()
    flip = up < 0.0
    out[flip] = tri[flip][:, [0, 2, 1], :]
    return out[np.abs(up) >= MIN_UP]


def prepare(
    terrain: Soup, bbox_m: Sequence[float], margin_m: float
) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Upward ground triangles of each terrain element that touch the work area.

    ``bbox_m`` is ``(min_x, min_y, max_x, max_y)``, Revit frame. A triangle is
    kept whole when its box meets the work box grown by ``margin_m``. Returns
    ``({id: (n, 3, 3)}, warnings)``; an element with nothing left is dropped.
    """
    x0, y0, x1, y1 = bbox_m
    x0, y0, x1, y1 = x0 - margin_m, y0 - margin_m, x1 + margin_m, y1 + margin_m
    kept: Dict[str, np.ndarray] = {}
    warnings: List[str] = []
    for name, flat in terrain.items():
        tri = face_up(triangles(flat))
        if len(tri):
            lo, hi = tri.min(axis=1), tri.max(axis=1)
            near = (hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)
            tri = tri[near]
        if len(tri) == 0:
            warnings.append(
                "Terrain %s has no ground triangle in the work area. It is skipped." % name
            )
            continue
        kept[str(name)] = tri
    return kept, warnings


class Sampler:
    """Terrain height at (x, y): barycentric lookup in the triangles. NaN outside."""

    def __init__(self, tri: np.ndarray) -> None:
        self.tri = np.asarray(tri, dtype=np.float64).reshape(-1, 3, 3)

    def z_at(self, xy: np.ndarray) -> np.ndarray:
        """Heights for ``(m, 2)`` points. Where triangles overlap, the highest wins."""
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        out = np.full(len(xy), np.nan)
        if len(xy) == 0 or len(self.tri) == 0:
            return out
        order = np.argsort(xy[:, 0], kind="stable")
        xs = xy[order, 0]
        for t in self.tri:
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
            det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-12:
                continue
            lo = np.searchsorted(xs, min(ax, bx, cx) - EPS, side="left")
            hi = np.searchsorted(xs, max(ax, bx, cx) + EPS, side="right")
            if hi <= lo:
                continue
            idx = order[lo:hi]
            px, py = xy[idx, 0], xy[idx, 1]
            l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / det
            l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / det
            l3 = 1.0 - l1 - l2
            inside = (l1 >= -EPS) & (l2 >= -EPS) & (l3 >= -EPS)
            if inside.any():
                z = l1[inside] * az + l2[inside] * bz + l3[inside] * cz
                hit = idx[inside]
                out[hit] = np.fmax(out[hit], z)
        return out


def ground_z(sampler: Optional[Sampler], xyz: np.ndarray, flat_z: float) -> np.ndarray:
    """Ground height under each ``(m, 3)`` point: the terrain, else ``flat_z``."""
    if sampler is None:
        return np.full(len(xyz), float(flat_z))
    z = sampler.z_at(xyz[:, :2])
    return np.where(np.isfinite(z), z, float(flat_z))


def buried(tri: np.ndarray, sampler: Optional[Sampler], flat_z: float) -> np.ndarray:
    """Bool per triangle: lies below the ground, so it is a foundation part.

    A triangle is buried when no vertex is above the ground (within
    ``GROUND_TOL_M``) and at least one is clearly below it. A floor slab that
    rests exactly on the ground is not buried: the building stays closed.
    """
    if len(tri) == 0:
        return np.zeros(0, dtype=bool)
    flat = tri.reshape(-1, 3)
    gap = (flat[:, 2] - ground_z(sampler, flat, flat_z)).reshape(-1, 3)
    return np.all(gap <= GROUND_TOL_M, axis=1) & np.any(gap < -GROUND_TOL_M, axis=1)


def corner_heights(points: np.ndarray, cell_m: float, sampler: Sampler) -> np.ndarray:
    """Terrain height at the corners of each cell: ``(n, 4)``, Revit metres.

    ``points`` are the ``(n, 3)`` cell centres (z = the ground fallback). The
    corner order is SW, SE, NE, NW. A corner outside the terrain takes the mean
    of the cell's other corners; a cell fully outside keeps its centre z.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    half = 0.5 * float(cell_m)
    dx = np.array([-half, half, half, -half])
    dy = np.array([-half, -half, half, half])
    cx = (pts[:, 0:1] + dx).reshape(-1)
    cy = (pts[:, 1:2] + dy).reshape(-1)
    # Neighbouring cells share corners: look each one up once (1 mm key).
    keys = np.round(np.stack([cx, cy], axis=1) / 1e-3).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    z = sampler.z_at(unique * 1e-3)[np.asarray(inverse).reshape(-1)].reshape(-1, 4)
    finite = np.isfinite(z)
    count = finite.sum(axis=1)
    total = np.where(finite, z, 0.0).sum(axis=1)
    mean = np.where(count > 0, total / np.maximum(count, 1), pts[:, 2])
    return np.where(finite, z, mean[:, None])
