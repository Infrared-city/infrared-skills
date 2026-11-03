"""Show a result in Revit as a coloured surface (a DirectShape in the model).

* ground: one square per grid cell, a little above the ground;
* facades: one triangle per result triangle, a little out of the wall.

Each cell takes the colour the SDK renderer gives it (``ir_dynamo.cell_colors``).
Each distinct colour is one material, named by analysis and colour, for example
"Infrared svf 08AEC4". The Watch text gives the legend in bins, with counts.
The shape stays in the model (it is "baked"); the next run of the same target
(ground or facades) replaces it. Look at
it in a Shaded or Realistic 3D view. The legend is in the Watch node text.

Dynamo wraps a node run in a transaction. This file asks Dynamo's
``TransactionManager`` for it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from ir_dynamo import cell_colors, colors, settings, summary

from . import result_mesh, revit_location

SHAPE_NAME = "Infrared result"
APP_ID = "Infrared Dynamo"
MATERIAL_PREFIX = "Infrared "


def material_name(analysis_type: str, rgb: Sequence[int]) -> str:
    """The material of one colour, for example ``"Infrared svf 08AEC4"``."""
    short = next(
        (a.key for a in settings.ANALYSES.values() if a.sdk_type == analysis_type),
        analysis_type or "result",
    )
    return "%s%s %02X%02X%02X" % (MATERIAL_PREFIX, short, rgb[0], rgb[1], rgb[2])


def _materials(doc: Any, analysis_type: str, palette: List[Tuple[int, int, int]]) -> List[Any]:
    """One material per palette colour (reused by name). Returns their ids."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import Color, FilteredElementCollector, Material  # type: ignore

    known = {
        m.Name: m
        for m in list(FilteredElementCollector(doc).OfClass(clr.GetClrType(Material)))
    }
    ids = []
    for rgb in palette:
        name = material_name(analysis_type, rgb)
        material = known.get(name)
        if material is None:
            material = doc.GetElement(Material.Create(doc, name))
            known[name] = material
        material.Color = Color(*rgb)
        ids.append(material.Id)
    return ids


LEGACY_DATA_ID = "result"  # the tag of shapes drawn before there were two targets


def _delete_old_shapes(doc: Any, target: str) -> int:
    """Delete the earlier shapes of ``target`` (and the untagged legacy ones)."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import DirectShape, FilteredElementCollector  # type: ignore

    # Copy to a list first: deleting while the collector runs breaks the iterator.
    shapes = list(FilteredElementCollector(doc).OfClass(clr.GetClrType(DirectShape)))
    old = [
        s.Id
        for s in shapes
        if s.ApplicationId == APP_ID
        and s.ApplicationDataId in (target, LEGACY_DATA_ID)
    ]
    for element_id in old:
        doc.Delete(element_id)
    return len(old)


def _build_shape(
    doc: Any, feet: np.ndarray, bins: np.ndarray, material_ids: List[Any], target: str
) -> Any:
    """One DirectShape with all triangles; each face takes the material of its bin.

    A Revit ``Mesh`` has ONE material, and a ``TessellatedShapeBuilder`` with
    the Mesh target gives one mesh, also from several face sets. So each colour
    has its own builder, and the meshes of all colours form one DirectShape.
    """
    from Autodesk.Revit.DB import (  # type: ignore
        BuiltInCategory,
        DirectShape,
        ElementId,
        GeometryObject,
        TessellatedFace,
        TessellatedShapeBuilder,
        TessellatedShapeBuilderFallback,
        TessellatedShapeBuilderTarget,
        XYZ,
    )
    from System.Collections.Generic import List as NetList  # type: ignore

    objects = NetList[GeometryObject]()
    for k in np.unique(bins):
        # One builder per colour: one builder gives ONE mesh (one material) even
        # with several face sets (a live run: 62 colours, 1 mesh, 1 material).
        builder = TessellatedShapeBuilder()
        builder.OpenConnectedFaceSet(False)
        material = material_ids[int(k)]
        for tri in feet[bins == k]:
            corners = NetList[XYZ]()
            for p in tri:
                corners.Add(XYZ(float(p[0]), float(p[1]), float(p[2])))
            builder.AddFace(TessellatedFace(corners, material))
        builder.CloseConnectedFaceSet()
        builder.Target = TessellatedShapeBuilderTarget.Mesh
        builder.Fallback = TessellatedShapeBuilderFallback.Salvage
        builder.Build()
        for item in builder.GetBuildResult().GetGeometricalObjects():
            objects.Add(item)
    shape = DirectShape.CreateElement(doc, ElementId(BuiltInCategory.OST_GenericModel))
    shape.ApplicationId = APP_ID  # how the next run finds and replaces it
    shape.ApplicationDataId = target  # "ground" or "facades"
    shape.SetShape(objects)
    objects = list(objects)
    try:
        shape.Name = "%s (%s)" % (SHAPE_NAME, target)  # shown in Properties; not every Revit allows it
    except Exception:
        pass
    materials = {
        str(o.MaterialElementId) for o in objects if hasattr(o, "MaterialElementId")
    }
    check = "Revit built %d mesh(es) with %d material(s) for %d colour(s)." % (
        len(objects),
        len(materials),
        len(np.unique(bins)),
    )
    return shape, check


def show(
    result: Dict[str, Any],
    title: str,
    unit: str,
    true_north_rad: float,
    target: str,
    analysis_type: str = "",
    range_mode: str = "",
) -> str:
    """Draw the result as a coloured surface. Return the text for the Watch node.

    Parameters
    ----------
    result : dict
        ``results.ground_points`` or ``results.facade_triangles`` of ir_dynamo.
    title, unit : str
        Legend title and unit.
    true_north_rad : float
        The angle that ``revit_geometry`` used. The shape is turned back with it.
    target : str
        ``"ground"`` or ``"facades"``. The shape is tagged with it; a new shape
        replaces only the old shape of the same target.
    analysis_type : str
        The SDK analysis name; it picks the platform colours. Empty or unknown:
        the built-in gradient, with a warning line.
    range_mode : str
        The legend range: ``"trimmed"``, ``"exact"`` or ``"platform"``
        (see ``ir_dynamo.colors``). Empty: the default.
    """
    from RevitServices.Persistence import DocumentManager  # type: ignore
    from RevitServices.Transactions import TransactionManager  # type: ignore

    if len(result["values"]) == 0:
        return "The result has no values to show."
    legend, warnings = colors.make_legend(
        analysis_type,
        result["legend_min"],
        result["legend_max"],
        values=result["values"],
        range_mode=range_mode,
    )
    palette, index, notes = cell_colors.cell_colors(
        analysis_type,
        result["values"],
        result["legend_min"],
        result["legend_max"],
        range_mode,
        legend,
        result.get("grid_shape"),
        result.get("cells"),
    )
    tri_m, bins = result_mesh.coloured_triangles(result, index)
    feet = revit_location.site_m_to_internal_ft(tri_m.reshape(-1), true_north_rad)
    feet = feet.reshape(-1, 3, 3)
    doc = DocumentManager.Instance.CurrentDBDocument
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        removed = _delete_old_shapes(doc, target)
        shape, check = _build_shape(
            doc, feet, bins, _materials(doc, analysis_type, palette), target
        )
    except Exception as error:
        TransactionManager.Instance.ForceCloseTransaction()
        return "Display failed: %s (%d triangles)" % (error, len(feet))
    TransactionManager.Instance.TransactionTaskDone()
    lines = [
        "Showed %s on %s (%s) as %d triangles, element %s (replaced %d old %s shape(s)). "
        "Use a Shaded or Realistic 3D view."
        % (title, target, unit, len(feet), shape.Id, removed, target),
        check,
        "Cell colours: drawn by the SDK renderer, %d distinct colour(s)." % len(palette),
    ]
    lines += summary.value_lines(result, target, unit)
    lines += ["Legend for %s (bin: colour, value range: count):" % target]
    lines += summary.legend_count_lines(legend, result["values"], unit, range_mode)
    lines += warnings + notes
    return "\n".join(lines)
