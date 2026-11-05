"""``analysis = "export-obj"``: write the selection as an OBJ file for the platform upload.

Free: no API key and no API call. The rules are in ``ir_dynamo.obj_export``;
this file reads Revit, writes the file and gives the Watch lines.
"""

from __future__ import annotations

import math
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from ir_dynamo import frame, obj_export, summary

from . import revit_geometry, revit_location

EXPORT_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "Infrared")


def is_export(analysis: Any) -> bool:
    return obj_export.parse_export(analysis) is not None


def export_obj(
    doc: Any,
    elements: Any,
    terrain: Any,
    lat: Optional[float],
    lon: Optional[float],
    progress: Any = None,
    label: str = "export-obj",
) -> List[str]:
    """Read the selection and the terrain, write the OBJ, return the Watch lines.

    ``label`` is the ``analysis`` text. ``"export-obj"`` keeps the building
    categories only (``obj_export.is_building``), ``"export-obj all"`` keeps all.
    """
    keep_all = bool(obj_export.parse_export(label))
    site = revit_location.read_location(doc, lat, lon)
    if progress:
        progress("export: reading geometry from Revit")
    categories: Dict[str, str] = {}
    buildings, terrain_m, notes = revit_geometry.collect_scene(
        doc,
        elements,
        site.true_north_rad,
        terrain,
        skip=None if keep_all else obj_export.not_building,
        categories=categories,
    )
    if not buildings:
        return [
            "No building geometry found. Select walls, floors, roofs or masses "
            "(and the ground in the terrain input)."
        ] + notes
    scene = obj_export.prepare_scene(buildings, terrain_m)
    ox, oy, oz = scene.origin
    o_lon, o_lat = frame.point_lonlat(site.lon, site.lat, ox, oy)
    document = doc.PathName or doc.Title
    header = [
        "Infrared OBJ export from Revit: %s" % os.path.basename(str(document)),
        "Unit: metres. Axes: x east, y north (true north), z up.",
        "Origin: lon %.6f, lat %.6f, Revit elevation %.2f m (ground)." % (o_lon, o_lat, oz),
    ]
    text, counts = obj_export.obj_text(scene, header, categories)
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    path = obj_export.export_path(EXPORT_FOLDER, document)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    size = os.path.getsize(path)
    return [
        "OBJ written: %s" % path,
        "%d object(s): %d building(s), %d ground; %d vertices, %d triangles."
        % (
            counts["objects"],
            len(scene.buildings),
            len(scene.terrain),
            counts["vertices"],
            counts["faces"],
        ),
        obj_export.size_line(size),
        summary.share_line(
            "Triangles by category",
            _category_triangles(scene.buildings, categories),
        ),
        "Place it on the platform map at lon %.6f, lat %.6f (the middle of the buildings). "
        "The file has no georeference: drag the model there before Save." % (o_lon, o_lat),
        "Location source: %s, true north %.1f deg. Units: metres, Z up."
        % (site.source, math.degrees(site.true_north_rad)),
        "On the platform, in Review model: if the model is upside down, clear "
        "'Flip vertical'. Up axis must be z.",
    ] + scene.warnings + notes


def _category_triangles(buildings: Dict[str, Any], categories: Dict[str, str]) -> Dict[str, int]:
    counts: Counter = Counter()
    for key, tri in buildings.items():
        counts[categories.get(key, "no category")] += len(tri)
    return dict(counts)
