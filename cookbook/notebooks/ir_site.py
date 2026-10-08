"""Small site helpers for the cookbook notebooks and scripts.

They turn your own GeoJSON (footprints with heights, tree points, ground
surfaces) into the inputs of the Infrared SDK, and make simple test geometry
(boxes, terrain). Everything is plain Python + numpy + shapely.

The frame rules (see https://infrared.city/docs/sdk/#coordinates):
- The run polygon is lon/lat. The south-west corner of its bounding box is
  the origin (0, 0, 0) of your model.
- Meshes are in metres: x east, y north, z up.
- Trees and ground materials stay in lon/lat. The SDK moves them.
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Polygon, shape
from shapely.geometry.polygon import orient

# The SDK projects lon/lat on a sphere with this radius (equirectangular
# around the origin). We use the same numbers so that our meshes sit exactly
# where the SDK puts the trees and the ground materials.
EARTH_RADIUS_M = 6_371_000.0
DEG = math.pi / 180.0

VIENNA_EPW_URL = (
    "https://climate.onebuilding.org/WMO_Region_6_Europe/AUT_Austria/"
    "NO_Lower_Austria/AUT_NO_Wien-Schwechat.AP.110360_TMYx.zip"
)


# --- Frame -----------------------------------------------------------------


def bbox_polygon(west: float, south: float, east: float, north: float) -> dict:
    """A GeoJSON polygon (lon/lat) for a bounding box."""
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def rect_polygon(lon: float, lat: float, width_m: float, height_m: float) -> dict:
    """A rectangle (lon/lat) with its south-west corner at (lon, lat)."""
    dlat = height_m / (EARTH_RADIUS_M * DEG)
    dlon = width_m / (EARTH_RADIUS_M * DEG * math.cos(lat * DEG))
    return bbox_polygon(lon, lat, lon + dlon, lat + dlat)


def polygon_around(features: list[dict], pad_m: float = 20.0) -> dict:
    """The bounding box of some GeoJSON features, padded by `pad_m` metres."""
    w, s, e, n = shapely.total_bounds([shape(f["geometry"]) for f in features])
    dlat = pad_m / (EARTH_RADIUS_M * DEG)
    dlon = dlat / math.cos(0.5 * (s + n) * DEG)
    return bbox_polygon(w - dlon, s - dlat, e + dlon, n + dlat)


def origin_of(polygon: dict) -> tuple[float, float]:
    """The model origin: the south-west corner of the polygon bbox."""
    ring = np.asarray(polygon["coordinates"][0])
    return float(ring[:, 0].min()), float(ring[:, 1].min())


def to_xy(lon: Any, lat: Any, origin: tuple[float, float]) -> tuple[Any, Any]:
    """Lon/lat to metres in the frame of `origin` (works on arrays too)."""
    lon0, lat0 = origin
    x = (np.asarray(lon) - lon0) * DEG * EARTH_RADIUS_M * math.cos(lat0 * DEG)
    y = (np.asarray(lat) - lat0) * DEG * EARTH_RADIUS_M
    return x, y


def size_m(polygon: dict) -> tuple[float, float]:
    """Width and height of the polygon bbox, in metres."""
    ring = np.asarray(polygon["coordinates"][0])
    x, y = to_xy(ring[:, 0], ring[:, 1], origin_of(polygon))
    return float(x.max()), float(y.max())


# --- Meshes ----------------------------------------------------------------


def extrude(footprint: Polygon, height: float, base: float = 0.0) -> dict:
    """A closed solid from a footprint (metres): bottom, top and walls.

    The caps use a constrained Delaunay triangulation, so concave footprints
    and courtyards work. The mesh shares its vertices, so it is watertight.
    """
    footprint = orient(footprint, 1.0)  # exterior CCW, holes CW
    rings = [footprint.exterior, *footprint.interiors]
    ring_xy = [np.asarray(r.coords)[:-1, :2] for r in rings]
    xy = np.vstack(ring_xy)
    n = len(xy)
    lookup = {(round(px, 6), round(py, 6)): i for i, (px, py) in enumerate(xy)}

    coords = np.vstack([np.c_[xy, np.full(n, base)], np.c_[xy, np.full(n, base + height)]])
    tris: list[tuple[int, int, int]] = []
    for tri in shapely.constrained_delaunay_triangles(footprint).geoms:
        a, b, c = (lookup[(round(px, 6), round(py, 6))] for px, py in tri.exterior.coords[:3])
        (ax, ay), (bx, by), (cx, cy) = xy[a], xy[b], xy[c]
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
            b, c = c, b  # make the triangle CCW seen from above
        tris += [(a, c, b), (a + n, b + n, c + n)]  # bottom faces down, top faces up
    start = 0
    for r in ring_xy:  # walls: one quad for each edge, normals outwards
        m = len(r)
        for i in range(m):
            p, q = start + i, start + (i + 1) % m
            tris += [(p, q, q + n), (p, q + n, p + n)]
        start += m
    return {"coordinates": coords.ravel().tolist(), "indices": np.ravel(tris).tolist()}


def box(x0: float, y0: float, x1: float, y1: float, z0: float, z1: float) -> dict:
    """An axis-aligned closed box in metres."""
    return extrude(shapely.box(x0, y0, x1, y1), z1 - z0, base=z0)


def terrain_mesh(xs: np.ndarray, ys: np.ndarray, z: np.ndarray) -> dict:
    """A height field (`z[j, i]` at `xs[i]`, `ys[j]`) as one triangle mesh."""
    nx, ny = len(xs), len(ys)
    X, Y = np.meshgrid(xs, ys)
    a = (np.arange(ny - 1)[:, None] * nx + np.arange(nx - 1)[None, :]).ravel()
    tris = np.c_[a, a + 1, a + nx + 1, a, a + nx + 1, a + nx]  # two CCW triangles per cell
    coords = np.c_[X.ravel(), Y.ravel(), np.asarray(z, dtype=float).ravel()]
    return {"coordinates": coords.ravel().tolist(), "indices": tris.ravel().tolist()}


def footprint_xy(feature: dict, origin: tuple[float, float]) -> Polygon:
    """A GeoJSON polygon feature (lon/lat) as a shapely polygon in metres."""
    geom = shape(feature["geometry"])
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    ext = np.asarray(geom.exterior.coords)
    holes = [np.asarray(h.coords) for h in geom.interiors]
    to_m = lambda c: np.c_[to_xy(c[:, 0], c[:, 1], origin)]  # noqa: E731
    return shapely.make_valid(Polygon(to_m(ext), [to_m(h) for h in holes])).buffer(0)


def buildings_from_geojson(
    fc: dict, origin: tuple[float, float], height_key: str = "height_m"
) -> dict[str, dict]:
    """Footprints with a height property -> `{id: mesh}` in metres."""
    meshes = {}
    for i, feature in enumerate(fc["features"]):
        poly = footprint_xy(feature, origin)
        height = float(feature["properties"].get(height_key) or 10.0)
        if poly.is_empty or poly.area < 4.0:
            continue  # skip slivers: they add no shade and cost sensors
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        meshes[f"b{i:03d}"] = extrude(poly, height)
    return meshes


def trees_from_geojson(fc: dict) -> dict[str, dict]:
    """Tree points -> `{id: feature}` for `vegetation=`.

    The crown shape comes from `genus`. Here the first word of the species
    name is the genus (for example "Tilia tomentosa" -> "Tilia").
    """
    trees = {}
    for i, f in enumerate(fc["features"]):
        p = dict(f["properties"])
        if "genus" not in p and p.get("species"):
            p["genus"] = p["species"].split()[0]
        trees[f"t{i:03d}"] = {"type": "Feature", "geometry": f["geometry"], "properties": p}
    return trees


def ground_from_geojson(fc: dict, key: str = "material") -> dict[str, dict]:
    """Surfaces with a material property -> `{layer: FeatureCollection}`."""
    layers: dict[str, list] = {}
    for f in fc["features"]:
        layers.setdefault(f["properties"][key], []).append(f)
    return {k: {"type": "FeatureCollection", "features": v} for k, v in layers.items()}


def facade_sensors(
    footprint: Polygon,
    height: float,
    spacing: float = 1.0,
    offset: float = 0.3,
    min_len: float = 3.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sensor points on the outer walls of an extruded footprint.

    Returns `(points, normals, wall)`: one row for each point, the outward
    normal, and the index of the wall (edge) it sits on. Points sit
    `offset` metres in front of the wall, on a `spacing` grid. Walls shorter
    than `min_len` get no sensors.
    """
    ring = np.asarray(orient(footprint, 1.0).exterior.coords)
    pts, nrm, wall = [], [], []
    zs = np.arange(spacing / 2, height, spacing)
    for i, (p, q) in enumerate(zip(ring[:-1, :2], ring[1:, :2])):
        edge = q - p
        length = float(np.hypot(*edge))
        if length < min_len:
            continue
        d = edge / length
        n = np.array([d[1], -d[0]])  # right of the edge = outside (CCW ring)
        s = np.arange(spacing / 2, length, spacing)
        xy = p + np.outer(s, d) + offset * n
        grid = np.array([[x, y, z] for z in zs for x, y in xy])
        pts.append(grid)
        nrm.append(np.tile([n[0], n[1], 0.0], (len(grid), 1)))
        wall.append(np.full(len(grid), i))
    return np.vstack(pts), np.vstack(nrm), np.concatenate(wall)


def ground_sensors(area: Polygon, spacing: float = 2.0, z: float = 1.0) -> np.ndarray:
    """A grid of sensor points inside a polygon, `z` metres above the ground."""
    x0, y0, x1, y1 = area.bounds
    xx, yy = np.meshgrid(np.arange(x0, x1, spacing) + spacing / 2, np.arange(y0, y1, spacing) + spacing / 2)
    xy = np.c_[xx.ravel(), yy.ravel()]
    inside = shapely.contains_xy(area, xy[:, 0], xy[:, 1])
    return np.c_[xy[inside], np.full(inside.sum(), z)]


def read_geojson(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


# --- Weather ---------------------------------------------------------------


def fetch_epw(url: str = VIENNA_EPW_URL, cache_dir: str | Path = "cache") -> Path:
    """Download a TMYx EPW (zip) once and return the path of the `.epw` file."""
    import io
    import zipfile

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (Path(url).stem + ".epw")
    if not target.exists():
        data = urllib.request.urlopen(url, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next(n for n in z.namelist() if n.endswith(".epw"))
            target.write_bytes(z.read(name))
    return target
