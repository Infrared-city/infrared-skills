"""The user's own trees and ground materials, as the GeoJSON layers of the SDK.

Both come in the Revit frame (metres, origin = site location, x east, y true
north), like the buildings:

* trees: ``[(x, y, height_m, crown_m), ...]``; ``crown_m`` is the crown DIAMETER.
* ground: ``{material: [ring, ...]}``, a ring is ``[(x, y), ...]`` (closed or not).

The SDK takes trees as GeoJSON Points (``height``, ``crownDiameter``) and the
ground as one FeatureCollection per material, in lon/lat. Only the thermal
analyses (UTCI, TCS) read the ground materials.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import frame as frame_mod

MATERIALS = ("asphalt", "concrete", "soil", "vegetation", "water")
THERMAL = ("thermal-comfort-index", "thermal-comfort-statistics")
TREE_HEIGHT_M = 6.0  # the SDK default for a tree without a size
TREE_CROWN_M = 4.0

Tree = Tuple[float, float, Optional[float], Optional[float]]
Ring = Sequence[Tuple[float, float]]


def material_name(text: str) -> str:
    """One of ``MATERIALS`` for a text (any case); ValueError for anything else."""
    name = str(text or "").strip().lower()
    if name not in MATERIALS:
        raise ValueError(
            "unknown ground material %r. Use one of: %s." % (str(text), ", ".join(MATERIALS))
        )
    return name


def trees_geojson(frame: frame_mod.SiteFrame, trees_m: Sequence[Tree]) -> Dict[str, dict]:
    """``{tree-N: GeoJSON Point Feature}`` for the ``vegetation`` layer."""
    out: Dict[str, dict] = {}
    for k, (x, y, height, crown) in enumerate(trees_m):
        lon, lat = frame_mod.to_lonlat(frame, x, y)
        out["tree-%d" % k] = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "height": float(height) if height else TREE_HEIGHT_M,
                "crownDiameter": float(crown) if crown else TREE_CROWN_M,
            },
        }
    return out


def ground_geojson(frame: frame_mod.SiteFrame, ground_m: Dict[str, Sequence[Ring]]) -> Dict[str, dict]:
    """``{material: FeatureCollection of Polygons}`` for the ``ground_materials`` layer."""
    out: Dict[str, dict] = {}
    for material, rings in ground_m.items():
        features = []
        for ring in rings:
            points = [list(frame_mod.to_lonlat(frame, x, y)) for x, y in ring]
            if len(points) > 1 and points[0] == points[-1]:
                points.pop()
            if len(points) < 3:
                continue
            points.append(list(points[0]))
            features.append(
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [points]}, "properties": {}}
            )
        if features:
            out[material_name(material)] = {"type": "FeatureCollection", "features": features}
    return out


def notes(sdk_type: str, trees_m: Sequence[Tree], ground_m: Dict[str, Sequence[Ring]]) -> List[str]:
    """The lines that say what was sent."""
    lines: List[str] = []
    if trees_m:
        sized = sum(1 for t in trees_m if t[2] or t[3])
        lines.append(
            "Trees: %d (%d with a size from the geometry; the others %.0f m high, %.0f m crown)."
            % (len(trees_m), sized, TREE_HEIGHT_M, TREE_CROWN_M)
        )
    if ground_m:
        counts = ", ".join("%s %d" % (m, len(r)) for m, r in sorted(ground_m.items()))
        if sdk_type in THERMAL:
            lines.append("Ground materials: %s. Where two overlap, one of them is used." % counts)
        else:
            lines.append(
                "Warning: ground materials (%s) have no effect on this analysis; only utci and "
                "tcs read them." % counts
            )
    return lines


def merge_layers(public: Optional[Dict[str, dict]], own: Optional[Dict[str, dict]]) -> Optional[Dict[str, dict]]:
    """The public ground layers with the own features added to their material."""
    out: Dict[str, dict] = {}
    for layers in (public or {}, own or {}):
        for name, collection in layers.items():
            features = list((collection or {}).get("features") or [])
            if features:
                out.setdefault(name, {"type": "FeatureCollection", "features": []})["features"] += features
    return out or None


def _size(properties: dict, key: str, default: float) -> float:
    try:
        value = float(properties.get(key) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else default


def _outer_points(geometry: dict) -> List[List[float]]:
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    if kind == "Point":
        return [list(coords[:2])]
    if kind == "Polygon" and coords:
        return [list(p[:2]) for p in coords[0]]
    if kind == "MultiPolygon" and coords and coords[0]:
        return [list(p[:2]) for p in coords[0][0]]
    return []


def display_trees(frame: frame_mod.SiteFrame, vegetation: Optional[Dict[str, dict]]) -> List[List[float]]:
    """``[[x, y, height, crown], ...]`` in the Revit frame, for a host that draws the trees.

    A polygon tree stands at the mean of its outer ring, as the SDK seats it (near enough to draw).
    """
    rows, where = [], []
    for feature in (vegetation or {}).values():
        points = _outer_points(feature.get("geometry") or {})
        if not points:
            continue
        props = feature.get("properties") or {}
        where.append(np.mean(np.asarray(points, dtype=np.float64), axis=0))
        rows.append((_size(props, "height", TREE_HEIGHT_M), _size(props, "crownDiameter", TREE_CROWN_M)))
    if not rows:
        return []
    xy = frame_mod.from_lonlat(frame, np.asarray(where))
    return [[float(x), float(y), h, c] for (x, y), (h, c) in zip(xy, rows)]


def display_ground(frame: frame_mod.SiteFrame, layers: Optional[Dict[str, dict]]) -> Dict[str, List[list]]:
    """``{material: [polygon, ...]}``, a polygon is ``[outer ring, hole, ...]`` of ``[x, y]`` in the Revit frame."""
    out: Dict[str, List[list]] = {}
    for name, collection in (layers or {}).items():
        polygons = []
        for feature in (collection or {}).get("features") or []:
            geometry = feature.get("geometry") or {}
            kind, coords = geometry.get("type"), geometry.get("coordinates") or []
            parts = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
            for rings in parts:
                polygon = [frame_mod.from_lonlat(frame, np.asarray(r, dtype=np.float64)[:, :2]).tolist()
                           for r in rings if len(r) >= 3]
                if polygon:
                    polygons.append(polygon)
        if polygons:
            out[name] = polygons
    return out
