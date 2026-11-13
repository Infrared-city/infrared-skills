"""Draw a legend in a Revit drafting view: one view for each result.

The Revit API cannot create a Legend view (only duplicate one), so the legend
is a drafting view named ``"Infrared legend - ground - <command> (<time>)"``
(or ``- facades - ...``),
at scale 1:1: one solid filled region per colour and a text note per line
(``ir_dynamo.legend_layout``). Find it in the Project Browser under Drafting
Views; it can go on a sheet. Each run has its own view. A result that is drawn
again (``show-last``) clears and redraws its view, so a viewport on a sheet stays.

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


def element_name(element: Any) -> str:
    """The name of an element, also of an ElementType. Empty if no way works.

    Dynamo's CPython3 cannot read ``ElementType.Name`` ("property cannot be
    read": the type declares only a setter), and the getter of ``Element.Name``
    can give a None, which printed as "None" and hid every legend view. So try,
    in order: .NET reflection on ``Element.Name``, the property, the base
    getter, and the name parameters. A None, empty or "None" answer counts as
    a failure.
    """
    import clr  # type: ignore
    from Autodesk.Revit.DB import BuiltInParameter, Element  # type: ignore

    ways = (
        lambda: clr.GetClrType(Element).GetProperty("Name").GetValue(element, None),
        lambda: element.Name,
        lambda: Element.Name.__get__(element, Element),
        lambda: element.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString(),
        lambda: element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString(),
        lambda: element.get_Parameter(BuiltInParameter.VIEW_NAME).AsString(),
    )
    for way in ways:
        try:
            name = way()
        except Exception:
            continue
        if name is not None and str(name) not in ("", "None"):
            return str(name)
    return ""


def _by_class(doc: Any, cls: Any, view_id: Any = None) -> List[Any]:
    import clr  # type: ignore
    from Autodesk.Revit.DB import FilteredElementCollector  # type: ignore

    collector = FilteredElementCollector(doc) if view_id is None else FilteredElementCollector(doc, view_id)
    return list(collector.OfClass(clr.GetClrType(cls)))


def _drafting_views(doc: Any) -> List[Any]:
    """The drafting views, without view templates: a collector on a template's id
    fails ("viewId is not valid for element iteration"; live run 2026-11-06 on the
    Snowdon Towers sample, which has drafting view templates)."""
    from Autodesk.Revit.DB import ViewDrafting  # type: ignore

    return [v for v in _by_class(doc, ViewDrafting) if not getattr(v, "IsTemplate", False)]


def _view(doc: Any, target: str, label: str = "", reuse: bool = False) -> Any:
    """The legend view for a result of ``target``, empty and with its name.

    Each run has its own view. ``reuse``: the result of this run is drawn again
    (``show-last``), so its view (``current_view_name``) is cleared and used
    again, and a viewport on a sheet stays.
    """
    from Autodesk.Revit.DB import (  # type: ignore
        FilledRegion,
        TextNote,
        ViewDrafting,
        ViewFamily,
        ViewFamilyType,
    )

    views = _drafting_views(doc)
    names = [element_name(v) for v in views]
    current = current_view_name(target, label, names) if reuse else ""
    view = next((v for v, n in zip(views, names) if n == current), None) if current else None
    if view is not None:
        for cls in (FilledRegion, TextNote):
            for element in _by_class(doc, cls, view.Id):
                doc.Delete(element.Id)
        new = view_name(target, label, [n for n in names if n != current])
        if new != current:
            _set_name(view, new)
        return view
    family = next(t for t in _by_class(doc, ViewFamilyType) if t.ViewFamily == ViewFamily.Drafting)
    view = ViewDrafting.Create(doc, family.Id)
    _set_name(view, view_name(target, label, names))
    try:
        view.Scale = 1  # sizes are paper millimetres
    except Exception:
        pass
    return view


BAD_NAME_CHARS = "\\:{}[]|;<>?`~"  # Revit refuses these in a view name


def _unique(base: str, taken: Sequence[str]) -> str:
    name, n = base, 2
    while name in taken:
        name, n = "%s (%d)" % (base, n), n + 1
    return name


def view_name(target: str, label: str, taken: Sequence[str]) -> str:
    """The name of a legend view: the target and the run label, and unique.

    Without a label (a result saved by an earlier version): the target only.
    """
    clean = "".join("-" if c in BAD_NAME_CHARS else c for c in label).strip()
    return _unique(VIEW_PREFIX + target + (" - " + clean if clean else ""), taken)


def current_view_name(target: str, label: str, names: Sequence[str]) -> str:
    """The name of the legend view that a result in the model has.

    ``label``: the run label of that result. ``names``: the names of the
    drafting views. The view has the name that ``view_name`` gave it, the last
    one if several views have this label. If there is none, it is the view of
    an earlier version, with the target only. Empty: the result has no view.
    """
    base = VIEW_PREFIX + target
    if label.strip():
        stem = view_name(target, label, ())
        same = [
            n
            for n in names
            if n == stem or (n.startswith(stem + " (") and n.endswith(")") and n[len(stem) + 2 : -1].isdigit())
        ]
        if same:
            return max(same, key=lambda n: int(n[len(stem) + 2 : -1]) if n != stem else 1)
    return base if base in names else ""


def _set_name(view: Any, name: str) -> None:
    """Name the view. Through its name parameter first: in CPython3 the property
    setter alone left new views with the default name ("Drafting 1")."""
    from Autodesk.Revit.DB import BuiltInParameter  # type: ignore

    try:
        view.get_Parameter(BuiltInParameter.VIEW_NAME).Set(name)
    except Exception:
        pass
    if element_name(view) != name:
        view.Name = name
    if element_name(view) != name:
        raise RuntimeError("the new legend view could not be named %r" % name)


def old_legend_views(doc: Any) -> List[str]:
    """Drafting views with legend swatches but another name: legends that older
    versions of this script could not name. The user can delete them."""
    from Autodesk.Revit.DB import FilledRegion  # type: ignore

    found = []
    for view in _drafting_views(doc):
        name = element_name(view)
        if name.startswith(VIEW_PREFIX):
            continue
        try:  # only a hint: a view that cannot be read is skipped, not an error
            regions = _by_class(doc, FilledRegion, view.Id)
        except Exception:
            continue
        for region in regions:
            if element_name(doc.GetElement(region.GetTypeId())).startswith(REGION_PREFIX):
                found.append(name or str(view.Id))
                break
    return found


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
    known = {element_name(t): t for t in types}
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
    label: str = "",
    reuse: bool = False,
) -> str:
    """Draw the legend view of a result. Returns a line for the Watch node.

    ``label``: the run label of the result, for the view name. ``reuse``: the
    result is drawn again, so its view is drawn again and no new view is made.
    """
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
    view = _view(doc, target, label, reuse)
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
    line = "Legend view: \"%s\" (Project Browser > Views > Drafting Views)." % element_name(view)
    try:  # the legend is drawn by now: a failing hint must not report it as not drawn
        old = old_legend_views(doc)
    except Exception:
        old = []
    if old:
        line += " Older legend views without a name: %s. Delete them." % ", ".join(old)
    return line
