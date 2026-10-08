"""Turn the user's building footprints (GeoJSON) into the meshes the SDK needs.

The SDK wants buildings as closed meshes `{id: {coordinates, indices}}` in
metres. The origin is the south-west corner of the bounding box of the run
polygon. x is east, y is north, z is up. Most users have footprints with a
height (GIS, CAD export, OSM). This module extrudes them into closed solids.
"""

from __future__ import annotations

import math
from typing import Any

import shapely
from shapely.geometry import Polygon, shape
from shapely.geometry.polygon import orient

# The SDK projects lon/lat into its site frame on a sphere with this radius
# (x = R * dlon * cos(origin_lat), y = R * dlat). Use the same numbers, so the
# buildings sit exactly where the SDK puts the trees and the ground.
EARTH_RADIUS_M = 6_371_000.0


def polygon_origin(polygon: dict) -> tuple[float, float]:
    """South-west corner (lon, lat) of the polygon bounding box = the model origin."""
    ring = polygon["coordinates"][0]
    return min(p[0] for p in ring), min(p[1] for p in ring)


def to_local(origin: tuple[float, float], lon: float, lat: float) -> tuple[float, float]:
    """Project one lon/lat point into the site frame, in metres."""
    lon0, lat0 = origin
    x = EARTH_RADIUS_M * math.radians(lon - lon0) * math.cos(math.radians(lat0))
    y = EARTH_RADIUS_M * math.radians(lat - lat0)
    return x, y


def _extrude(poly: Polygon, height: float) -> tuple[list[float], list[int]]:
    """One closed solid: bottom face, top face and walls, all faces outward."""
    poly = orient(poly, 1.0)  # outer ring counter-clockwise, holes clockwise
    rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]

    coords: list[float] = []
    index: dict[tuple[float, float], int] = {}  # xy -> index of the bottom vertex
    for ring in rings:
        for x, y in ring:
            index[(x, y)] = len(coords) // 6
            coords += [x, y, 0.0, x, y, height]  # bottom vertex 2i, top vertex 2i+1

    tris: list[int] = []
    # Caps: constrained Delaunay keeps concave shapes and holes correct and adds
    # no new points, so every triangle corner is a ring vertex.
    for tri in shapely.constrained_delaunay_triangles(poly).geoms:
        pa, pb, pc = list(tri.exterior.coords)[:3]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) < 0:
            pb, pc = pc, pb  # make the triangle counter-clockwise seen from above
        a, b, c = index[pa], index[pb], index[pc]
        tris += [2 * a + 1, 2 * b + 1, 2 * c + 1]  # top face looks up
        tris += [2 * a, 2 * c, 2 * b]  # bottom face looks down
    # Walls: for a counter-clockwise ring the outside is on the right side.
    for ring in rings:
        for i, p in enumerate(ring):
            a, b = index[p], index[ring[(i + 1) % len(ring)]]
            tris += [2 * a, 2 * b, 2 * b + 1, 2 * a, 2 * b + 1, 2 * a + 1]
    return coords, tris


def extrude_footprints(
    features: dict, polygon: dict, default_height: float = 10.0
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of footprints -> SDK buildings map.

    Each feature is a Polygon or MultiPolygon in lon/lat. `properties.height`
    is the building height in metres (default `default_height`).
    """
    origin = polygon_origin(polygon)
    buildings: dict[str, Any] = {}
    for n, feature in enumerate(features.get("features", [])):
        props = feature.get("properties") or {}
        height = float(props.get("height") or default_height)
        geom = shape(feature["geometry"])
        parts = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for k, part in enumerate(parts):
            local = Polygon(
                [to_local(origin, *p[:2]) for p in part.exterior.coords],
                [[to_local(origin, *p[:2]) for p in r.coords] for r in part.interiors],
            ).buffer(0)  # repairs small self-crossings in user data
            if local.is_empty or local.geom_type != "Polygon" or height <= 0:
                continue
            coords, indices = _extrude(local, height)
            key = str(feature.get("id") or props.get("id") or n)
            buildings[f"{key}-{k}" if k else key] = {"coordinates": coords, "indices": indices}
    return buildings
