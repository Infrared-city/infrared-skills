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
from . import summary
from . import terrain as terrain_mod

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


def near(soups: Soup, bbox_m: Sequence[float], reach_m: float) -> Soup:
    """The soups whose box meets ``bbox_m`` grown by ``reach_m`` (buildings that can shade)."""
    x0, y0, x1, y1 = bbox_m[0] - reach_m, bbox_m[1] - reach_m, bbox_m[2] + reach_m, bbox_m[3] + reach_m
    out: Soup = {}
    for name, flat in soups.items():
        xyz = np.asarray(flat, dtype=np.float64).reshape(-1, 3)
        if len(xyz) and xyz[:, 0].min() < x1 and xyz[:, 0].max() > x0 and xyz[:, 1].min() < y1 and xyz[:, 1].max() > y0:
            out[name] = flat
    return out


def build_buildings(
    frame: frame_mod.SiteFrame,
    soups: Soup,
    z_offset: float = 0.0,
    sampler: Optional[terrain_mod.Sampler] = None,
) -> Tuple[Dict[str, dict], float, List[str]]:
    """Revit-frame triangle lists -> SDK ``buildings`` dict.

    Parameters
    ----------
    frame : SiteFrame
        From ``frame.make_frame``.
    soups : dict
        ``{building_id: flat xyz list}``, Revit-frame metres.
    z_offset : float
        The Revit z that is the ground of the SDK (z = 0 there). Subtracted from
        every z. Default 0: the internal Revit elevation 0. With terrain, the
        caller passes the lowest terrain point. Add it back to every z that
        comes out.
    sampler : Sampler, optional
        The terrain. Without it the ground is flat at ``z_offset``. Triangles
        below the ground (foundations) are dropped, see ``terrain.buried``.

    Returns
    -------
    buildings : dict
        ``{id: {"coordinates": [...], "indices": [...]}}`` in the SDK frame.
    z_offset : float
        The offset that was used.
    warnings : list of str
        One line for each building that was dropped, and one with the number of
        buried triangles that were left out.
    """
    buildings: Dict[str, dict] = {}
    warnings: List[str] = []
    below = 0
    buried_ids: List[str] = []
    unusable_ids: List[str] = []
    # One terrain lookup for all the buildings: a lookup walks every terrain
    # triangle, so one per building did not end on a model of 4765 elements
    # with terrain (live run 2026-11-12).
    arrays = {name: _array(flat, name).reshape(-1, 3, 3) for name, flat in soups.items()}
    ends = np.cumsum([len(tri) for tri in arrays.values()])
    every = np.concatenate(list(arrays.values())) if arrays else np.zeros((0, 3, 3))
    gone_all = terrain_mod.buried(every, sampler, z_offset)
    for (name, tri), end in zip(arrays.items(), ends):
        gone = gone_all[end - len(tri):end]
        below += int(gone.sum())
        if gone.all():
            buried_ids.append(str(name))
            continue
        moved = frame_mod.points_to_sdk(frame, tri[~gone].reshape(-1))
        moved[2::3] -= z_offset
        cleaned = clean_mesh(moved, np.arange(moved.size // 3, dtype=np.uint32))
        if cleaned.indices.size == 0:
            unusable_ids.append(str(name))
            continue
        buildings[str(name)] = {
            "coordinates": np.asarray(cleaned.coordinates, dtype=np.float64).tolist(),
            "indices": cleaned.indices.astype(np.int64).tolist(),
        }
    for line in (
        summary.id_list_line("building(s) are entirely below the ground and are skipped", buried_ids),
        summary.id_list_line("building(s) have no usable triangle and are skipped", unusable_ids),
    ):
        if line:
            warnings.append(line)
    if not buildings:
        raise ValueError("No building has a usable triangle above the ground.")
    if below:
        warnings.append(
            "%d triangle(s) below the ground (foundations) were left out." % below
        )
    return buildings, float(z_offset), warnings


def build_terrain(
    frame: frame_mod.SiteFrame, terrain: Dict[str, np.ndarray], z_offset: float
) -> Dict[str, dict]:
    """Prepared terrain triangles (Revit frame) -> SDK ``ground_geometry`` dict.

    Shape: ``{id: {"coordinates": [...], "indices": [...]}}``, the SDK frame,
    z lowered by ``z_offset`` like the buildings.
    """
    out: Dict[str, dict] = {}
    for name, tri in terrain.items():
        moved = frame_mod.points_to_sdk(frame, tri.reshape(-1))
        moved[2::3] -= z_offset
        cleaned = clean_mesh(moved, np.arange(moved.size // 3, dtype=np.uint32))
        if cleaned.indices.size:
            out[str(name)] = {
                "coordinates": np.asarray(cleaned.coordinates, dtype=np.float64).tolist(),
                "indices": cleaned.indices.astype(np.int64).tolist(),
            }
    return out


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
