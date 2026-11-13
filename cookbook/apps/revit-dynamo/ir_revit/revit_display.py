"""Show a result in Revit as a coloured surface (a DirectShape in the model).

* ground: one square per grid cell, a little above the ground;
* facades: one triangle per result triangle, a little out of the wall.

Each cell takes the colour the SDK renderer gives it (``ir_dynamo.cell_colors``).
Each distinct colour is one material, named by analysis and colour, for example
"Infrared svf 08AEC4". The Watch text gives the legend in bins, with counts.
The shape stays in the model (it is "baked"): no later run deletes it, and the
command ``clear`` deletes them all (``revit_results``). A new result hides the
earlier results of its target in the active view (``revit_filters``). Look at
it in a Shaded or Realistic 3D view. The legend is in the Watch node text.

Dynamo wraps a node run in a transaction. This file asks Dynamo's
``TransactionManager`` for it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from ir_dynamo import cell_colors, colors, settings, summary, variants

from . import result_mesh, revit_filters, revit_legend, revit_location, revit_results
from .revit_results import APP_ID  # noqa: F401  (revit_geometry and revit_selection read it here)

SHAPE_NAME = "Infrared result"
MATERIAL_PREFIX = "Infrared "


def material_name(analysis_type: str, rgb: Sequence[int]) -> str:
    """The material of one colour, for example ``"Infrared svf 08AEC4"`` or
    ``"Infrared pwc lawson-lddc 0000FF"``."""
    base, variant = variants.split_key(analysis_type)
    short = next(
        (a.key for a in settings.ANALYSES.values() if a.sdk_type == base),
        base or "result",
    )
    if variant:
        short = "%s %s" % (short, variant)
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


def _sync_filters(doc: Any, target: str, comment: str) -> str:
    """A filter for each result; the earlier results of ``target`` are hidden in the view."""
    doc.Regenerate()  # the collector must see the new shape and not the deleted ones
    found = [(c, revit_results.target_of(data_id, c)) for _, c, data_id in revit_results.results(doc)]
    labels = sorted({c for c, _ in found if c} | ({comment} if comment else set()))
    hide = sorted({c for c, t in found if c and c != comment and t == target})
    return revit_filters.sync(doc, labels, show=comment, hide=hide)


def _build_shape(
    doc: Any,
    faces: List[Tuple[int, List[np.ndarray]]],
    material_ids: List[Any],
    target: str,
    regions: bool,
    label: str = "",
) -> Any:
    """One DirectShape with all faces; each face takes the material of its colour.

    ``label`` (the target, the command and the time of the run) goes into the
    Comments of the shape: Properties shows which run a shape is.

    ``faces``: ``(colour, [ring])`` in internal feet, one ring per face (no holes);
    a triangle is a ring of 3 corners. A Revit ``Mesh`` has ONE material, and a
    ``TessellatedShapeBuilder`` with the Mesh target gives one mesh, also from
    several face sets. So each colour has its own builder, and the geometry of all
    colours forms one DirectShape. ``regions``: the faces are joined colour regions
    (``result_mesh.coloured_regions``); they are built as faces of an open shell, so
    Revit draws edges only around each region, and as a mesh if that fails.
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
    for k in sorted({colour for colour, _ in faces}):
        # One builder per colour: one builder gives ONE mesh (one material) even
        # with several face sets (a live run: 62 colours, 1 mesh, 1 material).
        builder = TessellatedShapeBuilder()
        builder.OpenConnectedFaceSet(False)
        material = material_ids[int(k)]
        for colour, rings in faces:
            if colour != k:
                continue
            # One ring per face (regions come without holes). Pass the List[XYZ]
            # itself: an item read back from a list of IList[XYZ] made pythonnet
            # fail with "TessellatedFace returned NULL" (live run 2026-11-05).
            (ring,) = rings
            corners = NetList[XYZ]()
            for p in ring:
                corners.Add(XYZ(float(p[0]), float(p[1]), float(p[2])))
            builder.AddFace(TessellatedFace(corners, material))
        builder.CloseConnectedFaceSet()
        if regions:
            builder.Target = TessellatedShapeBuilderTarget.AnyGeometry
            builder.Fallback = TessellatedShapeBuilderFallback.Mesh
        else:
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
    try:
        if label:
            revit_results.comments(shape).Set(label)
    except Exception:
        pass
    materials = set()
    kinds: Dict[str, int] = {}
    for o in objects:
        name = type(o).__name__
        kinds[name] = kinds.get(name, 0) + 1
        if hasattr(o, "MaterialElementId"):  # a Mesh
            materials.add(str(o.MaterialElementId))
        elif hasattr(o, "Faces"):  # a Solid (open shell): a material per face
            materials.update(str(f.MaterialElementId) for f in o.Faces)
    check = "Revit built %s with %d material(s) for %d colour(s)." % (
        ", ".join("%d %s" % (n, name) for name, n in sorted(kinds.items())) or "nothing",
        len(materials),
        len({colour for colour, _ in faces}),
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
    gradient: bool = False,
    info: Sequence[str] = (),
    label: str = "",
) -> str:
    """Draw the result as a coloured surface. Return the text for the Watch node.

    The earlier results stay in the model. A shape of the same run and target is
    replaced (``show-last`` draws a saved result again).

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
        hides the earlier shapes of the same target in the active view.
    analysis_type : str
        The SDK analysis name; it picks the platform colours. Empty or unknown:
        the built-in gradient, with a warning line.
    range_mode : str
        The legend range: ``"trimmed"``, ``"exact"`` or ``"platform"``
        (see ``ir_dynamo.colors``). Empty: the default.
    gradient : bool
        True: a scale with flat platform bins (wind speed, UTCI) is drawn as a
        smooth gradient through the same colours.
    info : sequence of str
        Lines about the run for the legend view: the command, the location, the
        weather station, the time.
    label : str
        One short text for the run (command and time). With the target in front
        it is the Comments of the shape (``revit_results.shape_label``).
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
        gradient=gradient,
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
        gradient=gradient,
    )
    region_note = []
    try:
        regions_m = result_mesh.coloured_regions(result, index)
    except Exception as error:
        regions_m, region_note = None, ["Colour regions not joined (%s): one face per cell." % error]
    tri_m, bins = result_mesh.coloured_triangles(result, index)
    feet = revit_location.site_m_to_internal_ft(tri_m.reshape(-1), true_north_rad)
    cell_faces = [(int(k), [t]) for k, t in zip(bins, feet.reshape(-1, 3, 3))]
    doc = DocumentManager.Instance.CurrentDBDocument
    comment = revit_results.shape_label(target, label)
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        removed = revit_results.delete_same_run(doc, target, label)
        materials = _materials(doc, analysis_type, palette)
        # No per-colour subcategories for the edges: with 263 of them (live run
        # 2026-11-05) Dynamo did not start another run; Revit itself still responded.
        shape = None
        if regions_m is not None:
            faces = [
                (k, [revit_location.site_m_to_internal_ft(r.reshape(-1), true_north_rad).reshape(-1, 3) for r in rings])
                for k, rings in regions_m
            ]
            drawn = "%d region(s) of one colour" % len(faces)
            try:
                shape, check = _build_shape(doc, faces, materials, target, True, comment)
            except Exception as error:  # draw the cells, as before
                region_note.append("Colour regions failed in Revit (%s): one face per cell." % error)
        if shape is None:
            drawn = "%d triangles" % len(cell_faces)
            shape, check = _build_shape(doc, cell_faces, materials, target, False, comment)
    except Exception as error:
        TransactionManager.Instance.ForceCloseTransaction()
        return "Display failed: %s (%d triangles)" % (error, len(cell_faces))
    warnings = warnings + region_note
    low, high = float(legend.ramp_values[0]), float(legend.ramp_values[-1])
    if legend.labels:  # a class scale (PWC): no range
        warnings += variants.label_check(result.get("labels", []), legend.labels)
        legend_notes = list(info) + list(warnings)
    else:
        legend_notes = [
            "Colour range (%s): %.3g - %.3g %s; values outside take the end colours."
            % (colors.parse_range_mode(range_mode), low, high, unit)
        ] + list(info) + warnings
    try:  # a legend that fails must not take the result with it
        legend_line = revit_legend.draw_legend(
            doc, legend, title, unit, target, legend_notes, label, reuse=bool(removed)
        )
    except Exception as error:
        legend_line = "Legend view not drawn: %s" % error
    try:  # the same for the view filters
        filter_line = _sync_filters(doc, target, comment)
    except Exception as error:
        filter_line = "View filters not made: %s" % error
    TransactionManager.Instance.TransactionTaskDone()
    again = " (drawn again: it replaced %d shape(s) of the same run)" % removed if removed else ""
    lines = [
        "Showed %s on %s (%s) as %s, element %s%s. Use a Shaded or Realistic 3D view."
        % (title, target, unit, drawn, shape.Id, again),
        check,
        legend_line,
        filter_line,
        "Cell colours: drawn by the SDK renderer, %d distinct colour(s)%s."
        % (len(palette), ", smooth gradient" if gradient and not legend.labels else ""),
    ]
    lines += summary.value_lines(result, target, unit)
    lines += ["Legend for %s (bin: colour, value range: count):" % target]
    lines += summary.legend_count_lines(legend, result["values"], unit, range_mode)
    lines += warnings + notes
    return "\n".join(lines)
