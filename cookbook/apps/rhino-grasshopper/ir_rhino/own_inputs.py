"""Trees and ground materials from the Grasshopper inputs, in site metres.

* A tree is a point (6 m high, 4 m crown), a circle (crown = its diameter) or a
  solid / mesh (height and crown from its bounding box: the crown is the mean
  of its width and depth).
* A ground patch is a closed curve, a surface / polysurface (the outline of
  each face that is not vertical) or a mesh (its outlines). Holes are filled.
  Its material comes from the ``material`` input: one text for every patch,
  or one per patch.

The output is what ``ir_dynamo.own_layers`` takes. Rhino import inside the
functions: the module loads without Rhino.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ir_dynamo import own_layers

from .site import Site, model_to_site_m

MIN_AREA_M2 = 0.01  # a ring smaller than this in plan (a vertical face) is left out


def _xy_m(points: Sequence[Any], site: Site) -> List[Tuple[float, float]]:
    flat = [c for p in points for c in (p.X, p.Y, p.Z)]
    xyz = model_to_site_m(flat, site).reshape(-1, 3)
    return [(float(x), float(y)) for x, y, _ in xyz]


def _area(ring: Sequence[Tuple[float, float]]) -> float:
    xy = np.asarray(ring, dtype=np.float64)
    x, y = xy[:, 0], xy[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _curve_points(curve: Any, tolerance: float) -> Optional[List[Any]]:
    """The points of a closed curve, as a polyline; None when it is open."""
    if curve is None or not curve.IsClosed:
        return None
    ok, polyline = curve.TryGetPolyline()
    if ok:
        return list(polyline)
    poly = curve.ToPolyline(tolerance, math.radians(5.0), 0.0, 0.0)
    if poly is None:
        return None
    return [poly.Point(i) for i in range(poly.PointCount)]


def _rings(geometry: Any, tolerance: float) -> List[List[Any]]:
    """The outlines (model points) of one ground item."""
    import Rhino.Geometry as rg  # type: ignore

    if isinstance(geometry, rg.Curve):
        points = _curve_points(geometry, tolerance)
        return [points] if points else []
    if isinstance(geometry, rg.Extrusion):
        geometry = geometry.ToBrep()
    if isinstance(geometry, rg.Surface):
        geometry = geometry.ToBrep()
    if isinstance(geometry, rg.Brep):
        out = []
        for face in geometry.Faces:
            points = _curve_points(face.OuterLoop.To3dCurve(), tolerance)
            if points:
                out.append(points)
        return out
    if isinstance(geometry, rg.Mesh):
        return [list(p) for p in (geometry.GetNakedEdges() or [])]
    return []


def ground(
    geometries: Sequence[Any], materials: Sequence[Any], site: Site, tolerance: float
) -> Tuple[Dict[str, List[List[Tuple[float, float]]]], int]:
    """``({material: [ring, ...]}, items left out)``. ValueError for a bad material input."""
    if not geometries:
        return {}, 0
    names = [str(m).strip() for m in materials if m is not None and str(m).strip()]
    if not names:
        raise ValueError(
            "connect the material input: one of %s, one for every ground item or one for "
            "each." % ", ".join(own_layers.MATERIALS)
        )
    if len(names) not in (1, len(geometries)):
        raise ValueError(
            "the material input has %d text(s) for %d ground item(s): give one for all, or one "
            "for each." % (len(names), len(geometries))
        )
    names = [own_layers.material_name(n) for n in names]
    out: Dict[str, List[List[Tuple[float, float]]]] = {}
    skipped = 0
    for k, geometry in enumerate(geometries):
        rings = [_xy_m(r, site) for r in _rings(geometry, tolerance)] if geometry is not None else []
        rings = [r for r in rings if len(r) >= 3 and _area(r) >= MIN_AREA_M2]
        if not rings:
            skipped += 1
            continue
        out.setdefault(names[0 if len(names) == 1 else k], []).extend(rings)
    return out, skipped


def _tree(geometry: Any, site: Site) -> Optional[own_layers.Tree]:
    import Rhino.Geometry as rg  # type: ignore

    if isinstance(geometry, rg.Point):
        geometry = geometry.Location
    if isinstance(geometry, rg.Point3d):
        (x, y), = _xy_m([geometry], site)
        return x, y, None, None
    if isinstance(geometry, rg.Curve):
        ok, circle = geometry.TryGetCircle()
        if ok:
            (x, y), = _xy_m([circle.Center], site)
            return x, y, None, 2.0 * circle.Radius * site.unit_m
        return None
    if isinstance(geometry, (rg.Brep, rg.Extrusion, rg.Mesh, rg.SubD, rg.Surface)):
        box = geometry.GetBoundingBox(True)
        if not box.IsValid:
            return None
        (x, y), = _xy_m([box.Center], site)
        d = box.Diagonal
        height = d.Z * site.unit_m
        crown = 0.5 * (d.X + d.Y) * site.unit_m
        return x, y, height if height > 0 else None, crown if crown > 0 else None
    return None


def trees(geometries: Sequence[Any], site: Site) -> Tuple[List[own_layers.Tree], int]:
    """``([(x, y, height or None, crown or None), ...], items left out)``."""
    out: List[own_layers.Tree] = []
    skipped = 0
    for geometry in geometries:
        tree = _tree(geometry, site) if geometry is not None else None
        if tree is None:
            skipped += 1
        else:
            out.append(tree)
    return out, skipped
