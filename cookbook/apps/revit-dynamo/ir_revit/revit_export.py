"""``analysis = "export-obj"``: write the selection as an OBJ file for the platform upload.

Free: no API key and no API call. The rules are in ``ir_dynamo.obj_export``;
this file reads Revit, writes the file and gives the Watch lines.
"""

from __future__ import annotations

import math
import os
from typing import Any, List, Optional

from ir_dynamo import frame, obj_export

from . import revit_geometry, revit_location

EXPORT_NAMES = ("export-obj", "export obj", "export", "obj")
EXPORT_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "Infrared")


def is_export(analysis: Any) -> bool:
    return str(analysis).strip().lower() in EXPORT_NAMES


def export_obj(
    doc: Any,
    elements: Any,
    terrain: Any,
    lat: Optional[float],
    lon: Optional[float],
    progress: Any = None,
) -> List[str]:
    """Read the selection and the terrain, write the OBJ, return the Watch lines."""
    site = revit_location.read_location(doc, lat, lon)
    if progress:
        progress("export: reading geometry from Revit")
    buildings, terrain_m, notes = revit_geometry.collect_scene(
        doc, elements, site.true_north_rad, terrain
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
        "Unit: metres. Axes: x east, y up, -z north (true north).",
        "Origin: lon %.6f, lat %.6f, Revit elevation %.2f m (ground)." % (o_lon, o_lat, oz),
    ]
    text, counts = obj_export.obj_text(scene, header)
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
        "Place it on the platform map at lon %.6f, lat %.6f (the middle of the buildings). "
        "The file has no georeference: drag the model there before Save." % (o_lon, o_lat),
        "Location source: %s, true north %.1f deg. Units: metres, Y up."
        % (site.source, math.degrees(site.true_north_rad)),
    ] + scene.warnings + notes
