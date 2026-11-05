"""A result as coloured triangles: pure numpy, no Revit import (tested with pytest).

* ground: each grid cell becomes a square (two triangles), lifted a little,
  with its corners on the terrain when the result has ``corner_z``; on a flat
  ground the cells of one colour are joined into polygons (``coloured_regions``);
* facades: each result triangle, moved a little out of the wall.

The colour of each value is an index into a palette (``ir_dynamo.cell_colors``:
the colour the SDK renderer gives that cell).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


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


Loop = np.ndarray  # (k, 3) corners of one polygon ring, metres


def ground_regions(
    points: Sequence[Sequence[float]], cell_m: float, colour: Sequence[int]
) -> Optional[List[Tuple[int, List[Loop]]]]:
    """The cells of each colour joined into polygons: ``[(colour, [ring]), ...]``.

    Only for a flat ground (all cell centres at one z, no terrain): None else. Revit
    draws an edge around every face, so one face per cell shows the grid as lines;
    one face per region shows only the borders between colours. A region with a hole
    is cut through the hole into pieces without holes (``_without_holes``): the Revit
    face of one ring is the one that works from Dynamo. Each ring runs anticlockwise
    seen from above (face normal up). Lifted by ``GROUND_LIFT_M``.
    """
    from shapely.geometry import MultiPolygon, Polygon, box
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union

    centre = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    colour = np.asarray(colour, dtype=np.int64).reshape(-1)
    if len(centre) == 0 or float(np.ptp(centre[:, 2])) > 1e-6:
        return None
    cell = float(cell_m)
    origin = centre[:, :2].min(axis=0) - 0.5 * cell
    # Whole cell numbers: neighbour squares then share their corners exactly.
    ij = np.rint((centre[:, :2] - origin) / cell - 0.5).astype(np.int64)
    z = float(centre[0, 2]) + GROUND_LIFT_M

    def ring(coords: Any) -> Loop:
        xy = np.asarray(coords, dtype=np.float64)[:-1]  # shapely repeats the first corner
        out = np.empty((len(xy), 3))
        out[:, :2] = origin + xy * cell
        out[:, 2] = z
        return out

    regions: List[Tuple[int, List[Loop]]] = []
    for k in np.unique(colour):
        cells = ij[colour == k]
        merged = unary_union([box(i, j, i + 1, j + 1) for i, j in cells.tolist()])
        parts = merged.geoms if isinstance(merged, MultiPolygon) else [merged]
        for part in parts:
            if not isinstance(part, Polygon) or part.is_empty:
                continue
            for piece in _without_holes(part.simplify(0)):  # simplify: drop corners on straight edges
                piece = orient(piece, 1.0)
                regions.append((int(k), [ring(piece.exterior.coords)]))
    return regions


def _without_holes(polygon: Any) -> List[Any]:
    """``polygon`` cut into pieces without holes: a north-south cut through the middle
    of a hole splits its ring, and each piece is cut again until no hole is left."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import split

    if not polygon.interiors:
        return [polygon]
    hx0, _, hx1, _ = Polygon(polygon.interiors[0]).bounds
    _, y0, _, y1 = polygon.bounds
    x = 0.5 * (hx0 + hx1)
    pieces = split(polygon, LineString([(x, y0 - 1.0), (x, y1 + 1.0)]))
    out: List[Any] = []
    for piece in pieces.geoms:
        if isinstance(piece, Polygon) and not piece.is_empty:
            out += _without_holes(piece)
    return out


def coloured_regions(
    result: Dict[str, Any], index: Sequence[int]
) -> Optional[List[Tuple[int, List[Loop]]]]:
    """``ground_regions`` of a ground result without terrain; None for facades or terrain."""
    if result["kind"] != "points" or result.get("corner_z") is not None:
        return None
    return ground_regions(result["points"], result["cell_m"], index)


def coloured_triangles(result: Dict[str, Any], index: Sequence[int]) -> Tuple[np.ndarray, np.ndarray]:
    """Triangles ``(m, 3, 3)`` in Revit-frame metres and the colour index of each one.

    ``index[i]`` is the palette colour of ``result["values"][i]``.
    """
    colour = np.asarray(index, dtype=np.int64).reshape(-1)
    if result["kind"] == "points":
        tri = ground_triangles(result["points"], result["cell_m"], result.get("corner_z"))
        return tri, np.repeat(colour, 2)
    return facade_triangles(result["triangles"]), colour
