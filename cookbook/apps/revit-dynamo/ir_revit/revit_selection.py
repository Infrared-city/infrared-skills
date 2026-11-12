"""The elements to analyse: what is selected in Revit now, else the selection of the last run.

The graph has no selection node. Two ways to select:

* select the elements in Revit, then press Run (Tab picks an element inside a
  linked model);
* the command ``select`` (``pick``): Revit asks to click the elements and to
  press Finish. ``select link`` picks elements inside linked models.

With nothing selected the script uses the last selection in the same model
(``SELECTION_FILE``), so ``show-last`` or a second analysis needs no new pick.

Revit API calls used here: ``UIDocument.Selection`` (``GetElementIds``,
``GetReferences`` of Revit 2023 and later, for the picks inside a link),
``PickObjects`` with ``ObjectType.Element`` or ``LinkedElement``, ``SetElementIds``),
``Reference.LinkedElementId``, ``Document.GetElement`` (by id and by UniqueId),
``RevitLinkInstance.GetLinkDocument``.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

SELECTION_FILE = os.path.join(os.path.expanduser("~"), ".infrared", "revit-dynamo-selection.json")
Picks = Tuple[List[Any], List[Tuple[Any, Any]]]


def remember(path: str, document: str, host: List[str], linked: List[List[str]]) -> None:
    """Write the UniqueIds of a selection. A file that cannot be written stops nothing."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"document": document, "host": host, "linked": linked}, handle)
    except OSError:
        pass


def recall(path: str, document: str) -> Optional[Dict[str, Any]]:
    """The saved selection of ``document``; None when there is none for it."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("document") != document:
        return None
    host = [str(i) for i in data.get("host") or []]
    linked = [[str(a), str(b)] for a, b in data.get("linked") or []]
    return {"host": host, "linked": linked} if host or linked else None


def _document_name(doc: Any) -> str:
    return str(doc.PathName or doc.Title)


def _current(doc: Any) -> Picks:
    """What is selected in Revit now: elements of the model, and picks inside links."""
    selection = _ui_selection()
    host = [doc.GetElement(i) for i in list(selection.GetElementIds())]
    host = [e for e in host if e is not None]
    try:
        references = list(selection.GetReferences())  # Revit 2023 and later
    except Exception:
        references = []
    return host, _linked(doc, references)


def _ui_selection() -> Any:
    from RevitServices.Persistence import DocumentManager  # type: ignore

    return DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument.Selection


def _linked(doc: Any, references: Any) -> List[Tuple[Any, Any]]:
    """The references that point inside a linked model: ``(link instance, element)``."""
    from Autodesk.Revit.DB import ElementId  # type: ignore

    linked: List[Tuple[Any, Any]] = []
    for reference in references:
        inner = reference.LinkedElementId
        if inner is None or inner == ElementId.InvalidElementId:
            continue
        instance = doc.GetElement(reference.ElementId)
        document = instance.GetLinkDocument() if instance is not None else None
        element = document.GetElement(inner) if document is not None else None
        if element is not None:
            linked.append((instance, element))
    return linked


def _remember(doc: Any, host: List[Any], linked: List[Tuple[Any, Any]]) -> None:
    remember(
        SELECTION_FILE,
        _document_name(doc),
        [str(e.UniqueId) for e in host],
        [[str(i.UniqueId), str(e.UniqueId)] for i, e in linked],
    )


def _result_filter() -> Any:
    """A pick filter that refuses the Infrared result shapes, or None.

    A result shape lies on the ground and on the facades, so a click on a
    building picked the shape (live run 2026-11-12). With the filter Revit does
    not offer it. The .NET class is made one time for a Revit session and kept on
    ``sys``: this module is loaded again on each run, and a second class with the
    same name is an error.
    """
    import sys

    cached = getattr(sys, "_infrared_pick_filter_2", None)
    if cached is not None:
        return cached()
    try:
        from Autodesk.Revit.UI.Selection import ISelectionFilter  # type: ignore

        from .revit_display import APP_ID

        class InfraredPickFilter(ISelectionFilter):  # type: ignore
            __namespace__ = "Infrared.RevitDynamo2"

            def AllowElement(self, element: Any) -> bool:
                try:
                    return getattr(element, "ApplicationId", None) != APP_ID
                except Exception:
                    return True

            def AllowReference(self, reference: Any, position: Any) -> bool:
                return True

        sys._infrared_pick_filter_2 = InfraredPickFilter  # type: ignore
        return InfraredPickFilter()
    except Exception:
        return None


def pick(doc: Any, in_link: bool = False) -> List[str]:
    """The ``select`` command: the user clicks the elements in Revit and presses Finish.

    The picks are saved as the last selection, so the next commands use them.
    Picks in the open model also become the selection of Revit.
    """
    from Autodesk.Revit.DB import ElementId  # type: ignore
    from Autodesk.Revit.UI.Selection import ObjectType  # type: ignore
    from System.Collections.Generic import List as NetList  # type: ignore

    from ir_dynamo import summary

    from . import revit_geometry

    selection = _ui_selection()
    kind = ObjectType.LinkedElement if in_link else ObjectType.Element
    prompt = "Infrared: click the %s, then press Finish in the Options Bar (Esc cancels)." % (
        "elements inside the linked models" if in_link else "buildings"
    )
    picker = None if in_link else _result_filter()
    try:
        if picker is None:
            references = list(selection.PickObjects(kind, prompt))
        else:
            references = list(selection.PickObjects(kind, picker, prompt))
    except Exception as error:
        if "Cancel" in type(error).__name__:
            return [
                "Selection cancelled. The earlier selection stays.",
                "To end a pick, press Finish: it is in the Options Bar of Revit, top left, "
                "under the ribbon. Esc cancels. You can also select in Revit first, with no "
                "select command, and then run an analysis.",
            ]
        raise
    linked = _linked(doc, references) if in_link else []
    host = [] if in_link else [doc.GetElement(r.ElementId) for r in references]
    host = [e for e in host if e is not None]
    results = [e for e in host if revit_geometry.is_own_result(e)]
    host = [e for e in host if not revit_geometry.is_own_result(e)]
    dropped = (
        ["Warning: %d picked element(s) are Infrared result shapes, not buildings. They are "
         "left out. Hide the result shape (Hide in View) or move the pointer to the building "
         "and press Tab until it is highlighted." % len(results)]
        if results
        else []
    )
    if not host and not linked:
        return dropped + ["Nothing was picked. The earlier selection stays."]
    _remember(doc, host, linked)
    try:  # show the picks as the selection of Revit (not possible inside a link)
        ids = NetList[ElementId]()
        for element in host:
            ids.Add(element.Id)
        selection.SetElementIds(ids)
    except Exception:
        pass
    described = [revit_geometry.describe(e) for e in host] + [revit_geometry.describe(e) for _, e in linked]
    return dropped + [
        summary.selection_line("Selected", described) + (" (inside linked models)" if in_link else ""),
        "The next commands use this selection. Type an analysis, for example svf, and press Run.",
    ]


def _saved(doc: Any) -> Picks:
    data = recall(SELECTION_FILE, _document_name(doc))
    if data is None:
        return [], []
    host = [doc.GetElement(unique) for unique in data["host"]]
    linked: List[Tuple[Any, Any]] = []
    for link_unique, unique in data["linked"]:
        instance = doc.GetElement(link_unique)
        document = instance.GetLinkDocument() if instance is not None else None
        element = document.GetElement(unique) if document is not None else None
        if element is not None:
            linked.append((instance, element))
    return [e for e in host if e is not None], linked


def read(doc: Any, need: bool = True) -> Tuple[List[Any], List[Tuple[Any, Any]], List[str]]:
    """The elements to analyse and the Watch lines about them.

    ``need = False`` (the whole model is analysed): an empty selection is fine
    and the saved one is not used.
    """
    host, linked = _current(doc)
    if host or linked:
        _remember(doc, host, linked)
        return host, linked, []
    if not need:
        return [], [], []
    host, linked = _saved(doc)
    if host or linked:
        return host, linked, [
            "Nothing is selected in Revit: the last selection (%d element(s)) is used again. "
            "Select other elements in Revit, or use the command select, to change that."
            % (len(host) + len(linked))
        ]
    return [], [], []
