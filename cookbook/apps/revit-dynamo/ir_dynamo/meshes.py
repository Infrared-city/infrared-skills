"""Triangle lists from Revit -> SDK building meshes.

Input is plain data: ``{building_id: flat [x, y, z, x, y, z, ...]}``. Every 9
numbers are one triangle, in Revit-frame metres (z up). The SDK
(``infrared_sdk.geometry.clean_mesh``) welds the vertices, drops bad
triangles and turns the winding outward. This module only calls it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from infrared_sdk.geometry import clean_mesh

from . import frame as frame_mod

Soup = Dict[str, Sequence[float]]


def _array(flat: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(flat, dtype=np.float64).reshape(-1)
    if array.size == 0 or array.size % 9 != 0:
        raise ValueError(
            "Building %r: the triangle list needs 9 numbers for each triangle, got %d."
            % (name, array.size)
        )
    if not np.all(np.isfinite(array)):
        raise ValueError("Building %r has a coordinate that is not a number." % (name,))
    return array


def soup_bbox(soups: Soup) -> Tuple[float, float, float, float]:
    """``(min_x, min_y, max_x, max_y)`` of all triangles, in the input frame."""
    if not soups:
        raise ValueError("No buildings. Select at least one building.")
    boxes = []
    for name, flat in soups.items():
        xyz = _array(flat, name).reshape(-1, 3)
        boxes.append(
            (xyz[:, 0].min(), xyz[:, 1].min(), xyz[:, 0].max(), xyz[:, 1].max())
        )
    return (
        float(min(b[0] for b in boxes)),
        float(min(b[1] for b in boxes)),
        float(max(b[2] for b in boxes)),
        float(max(b[3] for b in boxes)),
    )


def soup_min_z(soups: Soup) -> float:
    """Lowest z of all triangles."""
    return float(min(_array(f, n).reshape(-1, 3)[:, 2].min() for n, f in soups.items()))


def build_buildings(
    frame: frame_mod.SiteFrame, soups: Soup, z_offset: Optional[float] = None
) -> Tuple[Dict[str, dict], float, List[str]]:
    """Revit-frame triangle lists -> SDK ``buildings`` dict.

    Parameters
    ----------
    frame : SiteFrame
        From ``frame.make_frame``.
    soups : dict
        ``{building_id: flat xyz list}``, Revit-frame metres.
    z_offset : float, optional
        Subtracted from every z, so that the lowest point is at 0 (the ground
        of the SDK). Default: the lowest z of all buildings. Add it back to
        every z that comes out.

    Returns
    -------
    buildings : dict
        ``{id: {"coordinates": [...], "indices": [...]}}`` in the SDK frame.
    z_offset : float
        The offset that was used.
    warnings : list of str
        One line for each building that was dropped.
    """
    if z_offset is None:
        z_offset = soup_min_z(soups)
    buildings: Dict[str, dict] = {}
    warnings: List[str] = []
    for name, flat in soups.items():
        moved = frame_mod.points_to_sdk(frame, _array(flat, name))
        moved[2::3] -= z_offset
        cleaned = clean_mesh(moved, np.arange(moved.size // 3, dtype=np.uint32))
        if cleaned.indices.size == 0:
            warnings.append("Building %s has no usable triangle and is skipped." % name)
            continue
        buildings[str(name)] = {
            "coordinates": np.asarray(cleaned.coordinates, dtype=np.float64).tolist(),
            "indices": cleaned.indices.astype(np.int64).tolist(),
        }
    if not buildings:
        raise ValueError("No building has a usable triangle.")
    return buildings, float(z_offset), warnings


def _field(mesh: Any, name: str) -> Any:
    """A field of a mesh that is a dict or an SDK ``DotBimMesh``."""
    return mesh[name] if isinstance(mesh, dict) else getattr(mesh, name)


def _xy_box(mesh: Any) -> Tuple[float, float, float, float]:
    xyz = np.asarray(_field(mesh, "coordinates"), dtype=np.float64).reshape(-1, 3)
    return xyz[:, 0].min(), xyz[:, 1].min(), xyz[:, 0].max(), xyz[:, 1].max()


def merge_context(
    selected: Dict[str, dict], fetched: Mapping[str, Any]
) -> Tuple[Dict[str, dict], int]:
    """Add fetched public buildings, except those that overlap a selected one.

    ``fetched`` values may be dicts or SDK ``DotBimMesh`` objects (what
    ``buildings.get_area`` returns). The overlap test is a box test in x and y.
    Both inputs are in the SDK frame. Returns ``(all_buildings, number_added)``.
    """
    boxes = [_xy_box(m) for m in selected.values()]
    merged = dict(selected)
    added = 0
    for name, mesh in fetched.items():
        x0, y0, x1, y1 = _xy_box(mesh)
        if any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1] for b in boxes):
            continue
        merged["ctx-%s" % name] = {
            "coordinates": list(_field(mesh, "coordinates")),
            "indices": list(_field(mesh, "indices")),
        }
        added += 1
    return merged, added
