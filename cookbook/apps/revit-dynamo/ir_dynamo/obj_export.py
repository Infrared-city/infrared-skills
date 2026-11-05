"""Write the selection as an OBJ file for the Infrared platform upload (free, no API call).

Input is plain data, like ``meshes``: ``{element_id: flat [x, y, z, ...]}``,
9 numbers per triangle, Revit-frame metres (x east, y true north, z up).

The file follows the platform upload rules (skill page ``platform-byo-upload.md``):

* metres, so the platform's unit guess finds "m";
* one object per element, named ``building_<id>`` or ``ground_<id>``, so the
  platform does not classify by shape;
* no ``usemtl`` lines: a Revit material name such as "Concrete" is a ground
  word for the platform classifier;
* the parts below the ground (basements, foundations) are left out, because
  the platform puts the lowest point of the model on the ground;
* Y up, -Z north (the usual OBJ axes, as Rhino and Blender write them). If the
  platform shows the model on its side, set the up axis in "Review model";
* by default without the detail categories (``is_detail``): furniture,
  fixtures, equipment, railings, mullions. They add many triangles and almost
  no effect on the outdoor climate. ``export-obj all`` keeps them.

The origin of the file is the middle of the buildings, at the ground. The
caller gives the longitude and latitude of that point to the user, who moves
the model there on the platform map: an OBJ has no georeference.
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import summary
from . import terrain as terrain_mod

Soup = Dict[str, Sequence[float]]

# Terrain triangles this far around the buildings go into the file.
TERRAIN_MARGIN_M = 50.0
# Vertices nearer than this are one vertex (1 mm).
WELD_M = 1e-3
# The platform refuses a larger OBJ file.
PLATFORM_LIMIT_BYTES = 40 * 1024 * 1024

EXPORT_NAMES = ("export-obj", "export obj", "export", "obj")
KEEP_ALL_WORDS = ("all", "full")

# Categories left out of an export by default: Revit BuiltInCategory names
# (language independent) and the English display names (a fallback).
DETAIL_BUILTINS = frozenset(
    "OST_" + n
    for n in (
        "LightingFixtures LightingDevices Furniture FurnitureSystems Casework "
        "SpecialityEquipment PlumbingFixtures MechanicalEquipment ElectricalEquipment "
        "ElectricalFixtures CommunicationDevices DataDevices FireAlarmDevices "
        "SecurityDevices NurseCallDevices TelephoneDevices Sprinklers DuctTerminal "
        "FoodServiceEquipment MedicalEquipment Signage AudioVisualDevices FireProtection "
        "StairsRailing StairsRailingBaluster RailingTopRail RailingHandRail RailingSupport "
        "RailingTermination CurtainWallMullions Cornices Entourage Planting Parking"
    ).split()
)
DETAIL_NAMES = frozenset(
    n.lower()
    for n in (
        "Lighting Fixtures", "Lighting Devices", "Furniture", "Furniture Systems",
        "Casework", "Specialty Equipment", "Plumbing Fixtures", "Mechanical Equipment",
        "Electrical Equipment", "Electrical Fixtures", "Communication Devices",
        "Data Devices", "Fire Alarm Devices", "Security Devices", "Nurse Call Devices",
        "Telephone Devices", "Sprinklers", "Air Terminals", "Food Service Equipment",
        "Medical Equipment", "Signage", "Audio Visual Devices", "Fire Protection",
        "Railings", "Top Rails", "Handrails", "Supports", "Terminations",
        "Curtain Wall Mullions", "Wall Sweeps", "Entourage", "Planting", "Parking",
    )
)


def parse_export(label: object) -> Optional[bool]:
    """None: not an export label. Else True when every category is kept.

    ``"export-obj"`` -> False (detail categories left out),
    ``"export-obj all"`` -> True.
    """
    words = re.split(r"[\s_]+", str(label).strip().lower())
    keep_all = bool(words) and words[-1] in KEEP_ALL_WORDS
    base = " ".join(words[:-1] if keep_all else words)
    if base in EXPORT_NAMES or base.replace(" ", "-") in EXPORT_NAMES:
        return keep_all
    return None


def is_detail(builtin: str, name: str) -> bool:
    """True for a category the export leaves out by default."""
    return str(builtin) in DETAIL_BUILTINS or str(name).strip().lower() in DETAIL_NAMES


@dataclass(frozen=True)
class ObjScene:
    """What goes into the file, Revit-frame metres.

    Attributes
    ----------
    buildings, terrain : dict
        ``{id: (n, 3, 3) triangles}``. Building parts below the ground are removed;
        terrain triangles face up and lie near the buildings.
    origin : tuple of float
        ``(x, y, z)``: the middle of the buildings box, at the ground level.
    warnings : list of str
        Lines for the Watch node.
    """

    buildings: Dict[str, np.ndarray]
    terrain: Dict[str, np.ndarray]
    origin: Tuple[float, float, float]
    warnings: List[str]


def _bbox(tris: Sequence[np.ndarray]) -> Tuple[float, float, float, float]:
    every = np.concatenate([t.reshape(-1, 3) for t in tris])
    return (
        float(every[:, 0].min()),
        float(every[:, 1].min()),
        float(every[:, 0].max()),
        float(every[:, 1].max()),
    )


def clip_to_ground(tri: np.ndarray, sampler: Optional[terrain_mod.Sampler], flat_z: float) -> Tuple[np.ndarray, int]:
    """Cut the triangles that cross the ground; keep the part above it.

    The platform puts the lowest point of the model on its ground, so a
    basement wall that reaches above the ground must not keep its lower part.
    The gap to the ground is linear along each edge (exact for a flat ground,
    close for a terrain). Returns ``(triangles, number of cut triangles)``.
    """
    if len(tri) == 0:
        return tri, 0
    flat = tri.reshape(-1, 3)
    gap = (flat[:, 2] - terrain_mod.ground_z(sampler, flat, flat_z)).reshape(-1, 3)
    tol = terrain_mod.GROUND_TOL_M
    cross = np.any(gap < -tol, axis=1) & np.any(gap > tol, axis=1)
    if not cross.any():
        return tri, 0
    pieces: List[np.ndarray] = [tri[~cross]]
    for t, g in zip(tri[cross], gap[cross]):
        poly = []
        for i in range(3):
            j = (i + 1) % 3
            if g[i] >= 0.0:
                poly.append(t[i])
            if (g[i] >= 0.0) != (g[j] >= 0.0):
                poly.append(t[i] + (t[j] - t[i]) * (g[i] / (g[i] - g[j])))
        for k in range(1, len(poly) - 1):
            pieces.append(np.array([[poly[0], poly[k], poly[k + 1]]]))
    return np.concatenate(pieces), int(cross.sum())


def prepare_scene(buildings_m: Soup, terrain_m: Optional[Soup] = None) -> ObjScene:
    """Buildings without their buried parts, the terrain near them, and the origin.

    The ground level is the lowest terrain point near the buildings, or Revit
    elevation 0 without terrain (the same rule as a run, ``run._scene``).
    """
    tris = {str(k): terrain_mod.triangles(v) for k, v in buildings_m.items()}
    tris = {k: v for k, v in tris.items() if len(v)}
    if not tris:
        raise ValueError("No buildings to export. Select walls, floors, roofs or masses.")
    bbox = _bbox(list(tris.values()))
    warnings: List[str] = []
    terrain: Dict[str, np.ndarray] = {}
    sampler = None
    ground = 0.0
    if terrain_m:
        terrain, notes = terrain_mod.prepare(terrain_m, bbox, TERRAIN_MARGIN_M)
        warnings += notes
        if terrain:
            every = np.concatenate(list(terrain.values()))
            sampler = terrain_mod.Sampler(every)
            ground = float(every[:, :, 2].min())
    buildings: Dict[str, np.ndarray] = {}
    below = 0
    cut = 0
    buried_ids: List[str] = []
    for name, tri in tris.items():
        gone = terrain_mod.buried(tri, sampler, ground)
        below += int(gone.sum())
        if gone.all():
            buried_ids.append(name)
            continue
        kept, n_cut = clip_to_ground(tri[~gone], sampler, ground)
        cut += n_cut
        buildings[name] = kept
    if buried_ids:
        warnings.append(
            summary.id_list_line("element(s) are entirely below the ground and are not exported", buried_ids)
        )
    if not buildings:
        raise ValueError("Every selected element is below the ground. Nothing to export.")
    if below:
        warnings.append(
            "%d triangle(s) below the ground (basements, foundations) are not exported."
            % below
        )
    if cut:
        warnings.append("%d triangle(s) that cross the ground are cut at the ground." % cut)
    if sampler is None:
        warnings.append(
            "No terrain: the ground is Revit elevation 0. Put the ground in the terrain "
            "input, or the platform puts the lowest exported point on its ground."
        )
    x0, y0, x1, y1 = _bbox(list(buildings.values()))
    origin = (0.5 * (x0 + x1), 0.5 * (y0 + y1), ground)
    return ObjScene(buildings, terrain, origin, warnings)


def _weld(tri: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Shared vertices (1 mm) and faces; faces with two equal corners are dropped."""
    points = tri.reshape(-1, 3)
    keys = np.round(points / WELD_M).astype(np.int64)
    unique, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    del unique
    faces = np.asarray(inverse).reshape(-1, 3)
    good = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return points[first], faces[good]


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_") or "x"


def obj_text(scene: ObjScene, header: Sequence[str] = ()) -> Tuple[str, Dict[str, int]]:
    """The OBJ file text and counts (``objects``, ``vertices``, ``faces``).

    Axes in the file: x east, y up, z south (Y up, -Z north), metres, from
    ``scene.origin``.
    """
    ox, oy, oz = scene.origin
    lines = ["# %s" % h for h in header]
    counts = {"objects": 0, "vertices": 0, "faces": 0}
    base = 1  # OBJ indices start at 1 and count over the whole file
    groups = [("building", scene.buildings), ("ground", scene.terrain)]
    for prefix, items in groups:
        for name, tri in items.items():
            points, faces = _weld(np.asarray(tri, dtype=np.float64))
            if len(faces) == 0:
                continue
            lines.append("o %s_%s" % (prefix, _safe_name(name)))
            east = points[:, 0] - ox
            north = points[:, 1] - oy
            up = points[:, 2] - oz
            lines += ["v %.3f %.3f %.3f" % (e, u, -n) for e, n, u in zip(east, north, up)]
            lines += ["f %d %d %d" % (a + base, b + base, c + base) for a, b, c in faces]
            base += len(points)
            counts["objects"] += 1
            counts["vertices"] += len(points)
            counts["faces"] += len(faces)
    return "\n".join(lines) + "\n", counts


def export_path(folder: str, document: str, now: Optional[datetime.datetime] = None) -> str:
    """``<folder>/<document name>-<YYYYmmdd-HHMM>.obj``; the name is made file-safe."""
    stem = os.path.splitext(os.path.basename(str(document or "")))[0]
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M")
    return os.path.join(folder, "%s-%s.obj" % (_safe_name(stem) if stem else "revit", stamp))


def size_line(size_bytes: int) -> str:
    """The file size, and a warning above the platform limit."""
    mb = size_bytes / (1024.0 * 1024.0)
    if size_bytes > PLATFORM_LIMIT_BYTES:
        return (
            "File size %.1f MB: above the platform limit of 40 MB. Select fewer "
            "elements (the outer shell only: no railings, furniture or curtain wall "
            "mullions)." % mb
        )
    return "File size %.1f MB (platform limit 40 MB)." % mb
