"""The result shapes in the model: the run and the target of each, and ``clear``.

Every run adds a shape; no run deletes the shape of another run. A shape is a
DirectShape with ``ApplicationId`` ``APP_ID``, the target in ``ApplicationDataId``
and the run in its Comments: ``"ground - wind 5 270 ground run (2026-11-13 09.10)"``.
The view filters (``revit_filters``) and the legend views (``revit_legend``) are
found by that text. A shape of the same run is replaced: ``show-last`` draws a
saved result again and must not leave two of it.

Shapes of earlier versions: the Comments have no target, and the data id can be
``"kept"`` (the word keep) or ``"result"`` (before there were two targets).

Call ``delete_same_run`` and ``clear`` inside the Dynamo transaction.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from . import revit_filters, revit_legend

APP_ID = "Infrared Dynamo"
TARGETS = ("ground", "facades")


def shape_label(target: str, label: str) -> str:
    """The Comments of a result shape: the target and the run label. Empty without a label."""
    return "%s - %s" % (target, label) if label else ""


def target_of(data_id: str, comment: str) -> str:
    """The target of a shape; empty when a shape of an earlier version does not tell."""
    if data_id in TARGETS:
        return data_id
    return next((t for t in TARGETS if comment.startswith(t + " - ")), "")


def same_run(comment: str, data_id: str, target: str, label: str) -> bool:
    """True: the shape with these Comments and this data id is this run on this target."""
    if label and comment == shape_label(target, label):
        return True
    return comment == label and data_id == target  # drawn by an earlier version, or no label


def comments(element: Any) -> Any:
    from Autodesk.Revit.DB import BuiltInParameter  # type: ignore

    return element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)


def results(doc: Any) -> List[Tuple[Any, str, str]]:
    """The result shapes of the model: ``(shape, Comments, data id)`` of each."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import DirectShape, FilteredElementCollector  # type: ignore

    out = []
    # A list first: deleting while the collector runs breaks the iterator.
    for shape in list(FilteredElementCollector(doc).OfClass(clr.GetClrType(DirectShape))):
        if shape.ApplicationId != APP_ID:
            continue
        try:
            comment = str(comments(shape).AsString() or "")
        except Exception:
            comment = ""
        out.append((shape, comment, str(shape.ApplicationDataId or "")))
    return out


def delete_same_run(doc: Any, target: str, label: str) -> int:
    """Delete the shapes of this run on this target. Returns their number."""
    same = [s for s, comment, data_id in results(doc) if same_run(comment, data_id, target, label)]
    for shape in same:
        doc.Delete(shape.Id)
    return len(same)


def clear(doc: Any) -> List[str]:
    """Delete every result shape, legend view and result filter. Lines for the Watch node."""
    from Autodesk.Revit.DB import ParameterFilterElement  # type: ignore

    name = revit_legend.element_name
    groups = [
        ("result shape(s)", [s for s, _, _ in results(doc)]),
        (
            "legend view(s)",
            [v for v in revit_legend._drafting_views(doc) if name(v).startswith(revit_legend.VIEW_PREFIX)],
        ),
        (
            "view filter(s)",
            [
                f
                for f in revit_legend._by_class(doc, ParameterFilterElement)
                if name(f).startswith(revit_filters.FILTER_PREFIX)
            ],
        ),
    ]
    done, failed = [], []
    for what, elements in groups:
        count = 0
        for element in elements:
            label = name(element) or str(element.Id)
            try:
                doc.Delete(element.Id)
                count += 1
            except Exception as error:  # Revit does not delete the view that is open and active
                failed.append("%s (%s)" % (label, error))
        done.append("%d %s" % (count, what))
    lines = ["Deleted %s." % ", ".join(done)]
    if failed:
        lines.append(
            "Not deleted: %s. Make a 3D view the active view and run clear again." % "; ".join(failed)
        )
    return lines + [
        "The saved results stay on disk: show-last draws the last result of each target again.",
        "Manage > Purge Unused removes the Infrared materials.",
    ]
