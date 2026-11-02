"""Show a result in Revit as a coloured surface (a DirectShape in the model).

* ground: one square per grid cell, a little above the ground;
* facades: one triangle per result triangle, a little out of the wall.

Each colour bin is one material, "Infrared 01" .. "Infrared 10" (low -> high).
The shape stays in the model (it is "baked"); the next run of the same target
(ground or facades) replaces it. Look at
it in a Shaded or Realistic 3D view. The legend is in the Watch node text.

Dynamo wraps a node run in a transaction. This file asks Dynamo's
``TransactionManager`` for it.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from . import result_mesh, revit_location

SHAPE_NAME = "Infrared result"
APP_ID = "Infrared Dynamo"
MATERIAL_PREFIX = "Infrared "


def _materials(doc: Any) -> List[Any]:
    """The bin materials (created once, colours refreshed). Returns their ids."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import Color, FilteredElementCollector, Material  # type: ignore

    known = {
        m.Name: m
        for m in list(FilteredElementCollector(doc).OfClass(clr.GetClrType(Material)))
    }
    ids = []
    for k, rgb in enumerate(result_mesh.bin_colors()):
        name = "%s%02d" % (MATERIAL_PREFIX, k + 1)
        material = known.get(name)
        if material is None:
            material = doc.GetElement(Material.Create(doc, name))
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
    """One DirectShape with all triangles; each face takes the material of its bin."""
    from Autodesk.Revit.DB import (  # type: ignore
        BuiltInCategory,
        DirectShape,
        ElementId,
        TessellatedFace,
        TessellatedShapeBuilder,
        TessellatedShapeBuilderFallback,
        TessellatedShapeBuilderTarget,
        XYZ,
    )
    from System.Collections.Generic import List as NetList  # type: ignore

    builder = TessellatedShapeBuilder()
    builder.OpenConnectedFaceSet(False)
    for tri, k in zip(feet, bins):
        corners = NetList[XYZ]()
        for p in tri:
            corners.Add(XYZ(float(p[0]), float(p[1]), float(p[2])))
        builder.AddFace(TessellatedFace(corners, material_ids[int(k)]))
    builder.CloseConnectedFaceSet()
    builder.Target = TessellatedShapeBuilderTarget.Mesh
    builder.Fallback = TessellatedShapeBuilderFallback.Salvage
    builder.Build()
    built = builder.GetBuildResult()
    shape = DirectShape.CreateElement(doc, ElementId(BuiltInCategory.OST_GenericModel))
    shape.ApplicationId = APP_ID  # how the next run finds and replaces it
    shape.ApplicationDataId = target  # "ground" or "facades"
    shape.SetShape(built.GetGeometricalObjects())
    try:
        shape.Name = "%s (%s)" % (SHAPE_NAME, target)  # shown in Properties; not every Revit allows it
    except Exception:
        pass
    return shape


def show(
    result: Dict[str, Any], title: str, unit: str, true_north_rad: float, target: str
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
    """
    from RevitServices.Persistence import DocumentManager  # type: ignore
    from RevitServices.Transactions import TransactionManager  # type: ignore

    if len(result["values"]) == 0:
        return "The result has no values to show."
    tri_m, bins = result_mesh.coloured_triangles(result)
    feet = revit_location.site_m_to_internal_ft(tri_m.reshape(-1), true_north_rad)
    feet = feet.reshape(-1, 3, 3)
    doc = DocumentManager.Instance.CurrentDBDocument
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        removed = _delete_old_shapes(doc, target)
        shape = _build_shape(doc, feet, bins, _materials(doc), target)
    except Exception as error:
        TransactionManager.Instance.ForceCloseTransaction()
        return "Display failed: %s (%d triangles)" % (error, len(feet))
    TransactionManager.Instance.TransactionTaskDone()
    low, high = result["legend_min"], result["legend_max"]
    lines = [
        "Showed %s on %s (%s) as %d triangles, element %s (replaced %d old %s shape(s)). "
        "Use a Shaded or Realistic 3D view."
        % (title, target, unit, len(feet), shape.Id, removed, target),
        "Legend for %s (material: value range):" % target,
    ]
    if low is not None and high is not None:
        lines += result_mesh.legend_lines(float(low), float(high), unit)
    return "\n".join(lines)
