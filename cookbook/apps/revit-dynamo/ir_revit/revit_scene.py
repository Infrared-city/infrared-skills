"""What a run reads from the model: result elements, shade elements, terrain.

Result elements (a result is drawn on them, and they size the run area):

* the selection: elements of the open model, elements picked inside a linked
  model (Tab), and a linked model picked as a whole;
* with ``scope = "model"``: every building element of the open model and of
  its loaded links. No selection is needed.

Shade elements: every other building element of the open model and of its
loaded links. They shade the result; no result is drawn on them.
``scope = "alone"`` reads none of them (faster on a large model).

A building element is an element of a building category
(``ir_dynamo.obj_export.BUILDING_BUILTINS``) or an import (DWG, IFC). Terrain:
the Toposolids of the selection; else those of the open model and its links.

Revit API calls used here, more than ``revit_geometry``: ``RevitLinkInstance``
(``GetLinkDocument``, ``GetTotalTransform``), ``ElementMulticategoryFilter``,
``ImportInstance``, ``Element.get_BoundingBox``, ``Element.ViewSpecific``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from ir_dynamo import obj_export, summary

from . import revit_geometry as rg
from . import revit_location

# Shade elements farther than this from the result elements are not read. It
# covers the largest default margin (about 250 m) and ``run.SHADE_REACH_M``.
SHADE_READ_REACH_FT = 700.0 / revit_location.FEET_TO_M
Soup = Dict[str, List[float]]


class Link:
    """One loaded linked model: its instance, document and placement."""

    def __init__(self, instance: Any, document: Any) -> None:
        self.instance = instance
        self.document = document
        self.key = rg.element_key(instance)
        t = instance.GetTotalTransform()
        self.matrix = np.array(
            [[v.X, v.Y, v.Z] for v in (t.Origin, t.BasisX, t.BasisY, t.BasisZ)], dtype=np.float64
        )

    def to_host(self, feet: Sequence[float]) -> np.ndarray:
        """Flat xyz feet in the link -> flat xyz feet in the open model."""
        p = np.asarray(feet, dtype=np.float64).reshape(-1, 3)
        m = self.matrix
        return (m[0] + p[:, 0:1] * m[1] + p[:, 1:2] * m[2] + p[:, 2:3] * m[3]).reshape(-1)


def links(doc: Any) -> Tuple[List[Link], List[str]]:
    """The loaded links of the open model, and a line for those that are not loaded."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import FilteredElementCollector, RevitLinkInstance  # type: ignore

    found: List[Link] = []
    unloaded = 0
    for instance in list(FilteredElementCollector(doc).OfClass(clr.GetClrType(RevitLinkInstance))):
        document = instance.GetLinkDocument()
        if document is None:
            unloaded += 1
            continue
        try:
            found.append(Link(instance, document))
        except Exception:
            unloaded += 1
    notes = []
    if unloaded:
        notes.append(
            "%d linked model(s) are not loaded and are not read. Load them in Manage > "
            "Manage Links to have them shade the result." % unloaded
        )
    return found, notes


def building_elements(document: Any) -> Iterator[Any]:
    """The building elements of one document: the building categories and the imports."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import (  # type: ignore
        BuiltInCategory,
        ElementMulticategoryFilter,
        FilteredElementCollector,
        ImportInstance,
    )
    from System.Collections.Generic import List as NetList  # type: ignore

    categories = NetList[BuiltInCategory]()
    for name in sorted(obj_export.BUILDING_BUILTINS):
        value = getattr(BuiltInCategory, name, None)
        if value is not None:
            categories.Add(value)
    collector = FilteredElementCollector(document).WhereElementIsNotElementType()
    for element in list(collector.WherePasses(ElementMulticategoryFilter(categories))):
        if not getattr(element, "ViewSpecific", False) and not rg.is_own_result(element):
            yield element
    for element in list(FilteredElementCollector(document).OfClass(clr.GetClrType(ImportInstance))):
        if not getattr(element, "ViewSpecific", False):
            yield element


def _xy_box(feet: Sequence[float]) -> Tuple[float, float, float, float]:
    p = np.asarray(feet, dtype=np.float64).reshape(-1, 3)
    return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())


def _is_near(element: Any, link: Optional[Link], box: Tuple[float, float, float, float]) -> bool:
    """True when the bounding box of the element meets ``box`` (feet, open model)."""
    try:
        bounds = element.get_BoundingBox(None)
    except Exception:
        return True
    if bounds is None:
        return False  # no geometry
    corners = [bounds.Min.X, bounds.Min.Y, bounds.Min.Z, bounds.Max.X, bounds.Max.Y, bounds.Max.Z]
    if link is not None:
        corners = link.to_host(corners)
    x0, x1 = sorted((corners[0], corners[3]))
    y0, y1 = sorted((corners[1], corners[4]))
    return x0 < box[2] and x1 > box[0] and y0 < box[3] and y1 > box[1]


def _key(element: Any, link: Optional[Link]) -> str:
    key = rg.element_key(element)
    return key if link is None else "link%s-%s" % (link.key, key)


def collect(
    doc: Any,
    host: Sequence[Any],
    linked: Sequence[Tuple[Any, Any]],
    true_north_rad: float,
    scope: str = "",
    progress: Optional[Callable[[str], None]] = None,
) -> Tuple[Soup, Soup, Soup, List[str]]:
    """Read the model for one run.

    Parameters
    ----------
    doc : Autodesk.Revit.DB.Document
    host : sequence
        Selected elements of the open model (Revit API elements).
    linked : sequence of (RevitLinkInstance, element)
        Elements picked inside a linked model.
    true_north_rad : float
        ``revit_location.SiteLocation.true_north_rad``.
    scope : str
        ``""``, ``"model"`` or ``"alone"`` (see the module text).
    progress : callable, optional
        Called with a short text at each stage.

    Returns
    -------
    buildings_m, shade_m, terrain_m : dict
        ``{id: flat [x, y, z, ...]}``, 9 numbers per triangle, metres, Revit
        frame. The id of a linked element is ``"link<link id>-<element id>"``.
    notes : list of str
    """
    say = progress or (lambda text: None)
    fine, medium = rg._options(), rg._options(fine=False)
    found, notes = links(doc)
    by_key = {link.key: link for link in found}
    result_ft: Dict[str, Any] = {}
    terrain_picked: List[Tuple[Any, Optional[Link]]] = []
    described: List[str] = []
    empty: List[str] = []
    own = 0

    def add(element: Any, link: Optional[Link]) -> None:
        feet = rg._element_feet(element, fine)
        if not feet:
            empty.append(rg.describe(element))
            return
        result_ft[_key(element, link)] = feet if link is None else link.to_host(feet)

    picked_links = {rg.element_key(instance) for instance, _ in linked}
    whole: List[Link] = []
    for element in host:
        if rg.is_own_result(element):
            own += 1
        elif rg.is_link(element):
            key = rg.element_key(element)
            if key in by_key and key not in picked_links:
                whole.append(by_key[key])
        elif rg.is_terrain(element):
            terrain_picked.append((element, None))
        else:
            described.append(rg.describe(element))
            add(element, None)
    for instance, element in linked:
        link = by_key.get(rg.element_key(instance))
        if link is None:
            continue
        if rg.is_terrain(element):
            terrain_picked.append((element, link))
        else:
            described.append(rg.describe(element))
            add(element, link)
    if described or scope != "model":
        notes.append(summary.selection_line("Selection", described))
    sources: List[Tuple[Any, Optional[Link]]] = [(doc, None)] + [(link.document, link) for link in found]
    if scope == "model":
        say("reading every building element of the model and %d link(s)" % len(found))
        before = len(result_ft)
        for document, link in sources:
            for element in building_elements(document):
                if _key(element, link) not in result_ft:
                    add(element, link)
        notes.append(
            "Model: %d more building element(s) of the model and its %d loaded link(s) get a result."
            % (len(result_ft) - before, len(found))
        )
    for link in whole:
        before = len(result_ft)
        for element in building_elements(link.document):
            add(element, link)
        notes.append(
            "Linked model %s is selected as a whole: its %d building element(s) get a result."
            % (link.key, len(result_ft) - before)
        )
    shade_ft: Dict[str, Any] = {}
    if scope == "" and result_ft:
        boxes = [_xy_box(feet) for feet in result_ft.values()]
        reach = SHADE_READ_REACH_FT
        box = (
            min(b[0] for b in boxes) - reach,
            min(b[1] for b in boxes) - reach,
            max(b[2] for b in boxes) + reach,
            max(b[3] for b in boxes) + reach,
        )
        say("reading the other building elements of the model and %d link(s) (shade)" % len(found))
        for document, link in sources:
            for element in building_elements(document):
                key = _key(element, link)
                if key in result_ft or not _is_near(element, link, box):
                    continue
                feet = rg._element_feet(element, medium)
                if feet:
                    shade_ft[key] = feet if link is None else link.to_host(feet)
        say("shade: %d element(s) read" % len(shade_ft))
    terrain_ft, terrain_notes = _terrain(doc, terrain_picked, found, fine)
    notes += terrain_notes
    if empty:
        notes.append(summary.selection_line("Skipped, no 3D geometry", empty))
    if own:
        notes.append("%d Infrared result shape(s) in the selection are not analysed." % own)

    def metres(soups: Dict[str, Any]) -> Soup:
        return {
            key: revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
            for key, feet in soups.items()
        }

    return metres(result_ft), metres(shade_ft), metres(terrain_ft), notes


def link_buildings(
    doc: Any,
    instances: Sequence[Any],
    linked: Sequence[Tuple[Any, Any]],
    true_north_rad: float,
    skip: Optional[Callable[[str, str], bool]] = None,
    categories: Optional[Dict[str, str]] = None,
    every_link: bool = False,
) -> Tuple[Soup, List[str]]:
    """The building elements of linked models, for ``export-obj``. No terrain.

    Parameters
    ----------
    doc : Autodesk.Revit.DB.Document
    instances : sequence
        Linked models selected as a whole (``RevitLinkInstance``): every
        building element of each is read.
    linked : sequence of (RevitLinkInstance, element)
        Elements picked inside a linked model.
    true_north_rad : float
        ``revit_location.SiteLocation.true_north_rad``.
    skip : callable, optional
        ``skip(builtin_name, display_name)``: True leaves a picked element out
        (``ir_dynamo.obj_export.not_building``).
    categories : dict, optional
        Filled with ``{id: category display name}``.
    every_link : bool
        Read every building element of every loaded link (``export-obj model``).

    Returns
    -------
    buildings_m : dict
        ``{"link<link id>-<element id>": flat [x, y, z, ...]}``, metres, Revit
        frame of the open model.
    notes : list of str
    """
    fine = rg._options()
    found, notes = links(doc)
    by_key = {link.key: link for link in found}
    feet_by_key: Dict[str, Any] = {}
    skipped: List[str] = []
    empty: List[str] = []

    def add(element: Any, link: Link, check: bool) -> None:
        key = _key(element, link)
        if key in feet_by_key or rg.is_terrain(element):
            return
        builtin, name = rg.category_names(element)
        if check and skip is not None and skip(builtin, name):
            skipped.append(rg.describe(element))
            return
        feet = rg._element_feet(element, fine)
        if not feet:
            empty.append(rg.describe(element))
            return
        feet_by_key[key] = link.to_host(feet)
        if categories is not None:
            categories[key] = name or "no category"

    for instance, element in linked:
        link = by_key.get(rg.element_key(instance))
        if link is not None:
            add(element, link, True)
    if linked:
        notes.append("Linked models: %d picked element(s) inside them are exported." % len(feet_by_key))
    keys = list(dict.fromkeys(rg.element_key(instance) for instance in instances))
    whole = found if every_link else [by_key[key] for key in keys if key in by_key]
    for link in whole:
        before = len(feet_by_key)
        for element in building_elements(link.document):
            add(element, link, False)
        notes.append(
            "Linked model %s: its %d building element(s) are exported." % (link.key, len(feet_by_key) - before)
        )
    if skipped:
        notes.append(summary.selection_line("Left out in linked models (not a building category)", skipped))
    if empty:
        notes.append(summary.selection_line("Skipped in linked models, no 3D geometry", empty))
    metres = {
        key: revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
        for key, feet in feet_by_key.items()
    }
    return metres, notes


def _terrain(
    doc: Any, picked: List[Tuple[Any, Optional[Link]]], found: List[Link], options: Any
) -> Tuple[Dict[str, Any], List[str]]:
    """The terrain triangles (feet, open model) and the line that says where they came from."""
    notes: List[str] = []
    if picked:
        elements = picked
        notes.append("Terrain: the %d Toposolid and Topography element(s) of the selection." % len(picked))
    else:
        elements = [(e, None) for e in rg._document_terrain(doc)]
        in_links = 0
        for link in found:
            more = [(e, link) for e in rg._document_terrain(link.document)]
            in_links += len(more)
            elements += more
        notes.append(
            "Terrain: no Toposolid in the selection; using the %d Toposolid and Topography "
            "element(s) of the model (%d of them in linked models). %s"
            % (len(elements), in_links, rg.TERRAIN_HINT)
        )
    out: Dict[str, Any] = {}
    for element, link in elements:
        feet = rg._terrain_feet(element, options)
        if not feet:
            notes.append("Terrain %s (%s) has no geometry. It is skipped." % (_key(element, link), rg.describe(element)))
            continue
        out[_key(element, link)] = feet if link is None else link.to_host(feet)
    return out, notes
