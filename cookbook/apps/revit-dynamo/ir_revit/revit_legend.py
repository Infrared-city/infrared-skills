"""Draw a legend in a Revit drafting view: one view per target, renewed each run.

The Revit API cannot create a Legend view (only duplicate one), so the legend
is a drafting view named ``"Infrared legend - ground"`` (or ``- facades``),
at scale 1:1: one solid filled region per colour and a text note per line
(``ir_dynamo.legend_layout``). Find it in the Project Browser under Drafting
Views; it can go on a sheet. A new run of the same target clears and redraws
the same view, so a viewport on a sheet stays.

Call it inside the Dynamo transaction (``revit_display.show`` does).

Revit API calls used here: ``ViewFamilyType`` / ``ViewDrafting.Create``,
``FillPatternElement``, ``FilledRegionType`` (``Duplicate``,
``ForegroundPatternId``, ``ForegroundPatternColor``), ``FilledRegion.Create``,
``CurveLoop``, ``Line.CreateBound``, ``TextNote.Create``,
``Document.GetDefaultElementTypeId``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ir_dynamo import colors, legend_layout

VIEW_PREFIX = "Infrared legend - "
REGION_PREFIX = "Infrared legend "
MM_TO_FT = 1.0 / 304.8


def _by_class(doc: Any, cls: Any, view_id: Any = None) -> List[Any]:
    import clr  # type: ignore
    from Autodesk.Revit.DB import FilteredElementCollector  # type: ignore

    collector = FilteredElementCollector(doc) if view_id is None else FilteredElementCollector(doc, view_id)
    return list(collector.OfClass(clr.GetClrType(cls)))


def _view(doc: Any, target: str) -> Any:
    """The legend view of ``target``: found by name and cleared, or created."""
    from Autodesk.Revit.DB import (  # type: ignore
        FilledRegion,
        TextNote,
        ViewDrafting,
        ViewFamily,
        ViewFamilyType,
    )

    name = VIEW_PREFIX + target
    for view in _by_class(doc, ViewDrafting):
        if view.Name == name:
            for cls in (FilledRegion, TextNote):
                for element in _by_class(doc, cls, view.Id):
                    doc.Delete(element.Id)
            return view
    family = next(t for t in _by_class(doc, ViewFamilyType) if t.ViewFamily == ViewFamily.Drafting)
    view = ViewDrafting.Create(doc, family.Id)
    view.Name = name
    try:
        view.Scale = 1  # sizes are paper millimetres
    except Exception:
        pass
    return view


def _solid_fill(doc: Any) -> Any:
    from Autodesk.Revit.DB import FillPatternElement, FillPatternTarget  # type: ignore

    for pattern in _by_class(doc, FillPatternElement):
        fill = pattern.GetFillPattern()
        if fill.IsSolidFill and fill.Target == FillPatternTarget.Drafting:
            return pattern
    raise RuntimeError("the document has no solid fill pattern")


def _region_types(doc: Any, rgbs: Sequence[Any]) -> Dict[Any, Any]:
    """One solid FilledRegionType per colour, named by its hex (reused by name)."""
    from Autodesk.Revit.DB import Color, FilledRegionType  # type: ignore

    types = _by_class(doc, FilledRegionType)
    known = {t.Name: t for t in types}
    solid = _solid_fill(doc)
    out = {}
    for rgb in set(tuple(c) for c in rgbs):
        name = "%s%02X%02X%02X" % (REGION_PREFIX, rgb[0], rgb[1], rgb[2])
        region_type = known.get(name)
        if region_type is None:
            region_type = doc.GetElement(types[0].Duplicate(name).Id)
            known[name] = region_type
        region_type.ForegroundPatternId = solid.Id
        region_type.ForegroundPatternColor = Color(*rgb)
        out[rgb] = region_type.Id
    return out


def draw_legend(
    doc: Any,
    legend: colors.Legend,
    title: str,
    unit: str,
    target: str,
    notes: Sequence[str] = (),
) -> str:
    """Draw (or redraw) the legend view of ``target``. Returns a line for the Watch node."""
    from Autodesk.Revit.DB import (  # type: ignore
        CurveLoop,
        ElementTypeGroup,
        FilledRegion,
        Line,
        TextNote,
        XYZ,
    )
    from System.Collections.Generic import List as NetList  # type: ignore

    swatches, texts = legend_layout.legend_layout(legend, title, unit, target, notes)
    view = _view(doc, target)
    region_types = _region_types(doc, [s.rgb for s in swatches])
    for s in swatches:
        x0, y0 = s.x * MM_TO_FT, s.y * MM_TO_FT
        x1, y1 = (s.x + s.w) * MM_TO_FT, (s.y + s.h) * MM_TO_FT
        corners = [XYZ(x0, y0, 0), XYZ(x1, y0, 0), XYZ(x1, y1, 0), XYZ(x0, y1, 0)]
        loop = CurveLoop()
        for a, b in zip(corners, corners[1:] + corners[:1]):
            loop.Append(Line.CreateBound(a, b))
        loops = NetList[CurveLoop]()
        loops.Add(loop)
        FilledRegion.Create(doc, region_types[tuple(s.rgb)], view.Id, loops)
    text_type = doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType)
    for t in texts:
        TextNote.Create(doc, view.Id, XYZ(t.x * MM_TO_FT, t.y * MM_TO_FT, 0), t.text, text_type)
    return "Legend view: \"%s\" (Project Browser > Drafting Views)." % view.Name
