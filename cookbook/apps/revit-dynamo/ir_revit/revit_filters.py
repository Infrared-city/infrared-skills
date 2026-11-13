"""One view filter per result, so the user can hide and show each result.

A result shape is a Generic Model with the target and the run (the command and
the time) in its Comments (``revit_results.shape_label``). After each run,
``sync`` makes one ``ParameterFilterElement`` for each Comments text ("Comments
equals the text") and adds it to the active view. There it hides the earlier
results of the same target, which lie in the same place as the new one. The
user opens Visibility/Graphics > Filters and changes Visibility to show or hide
a result. A filter whose result is no longer in the model is deleted.

Shapes of an earlier version have no target in the Comments: the two shapes of
a ``both`` run then have one filter.

Call it inside the Dynamo transaction (``revit_display.show`` does).

Revit API calls used here: ``ParameterFilterElement.Create``,
``ParameterFilterRuleFactory.CreateEqualsRule``, ``ElementParameterFilter``,
``View.AreGraphicsOverridesAllowed``, ``View.GetFilters``, ``View.AddFilter``,
``View.SetFilterVisibility``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from . import revit_legend

FILTER_PREFIX = "Infrared result - "


def filter_name(label: str) -> str:
    """The name of the filter of one run label. Revit refuses some characters."""
    clean = "".join("-" if c in revit_legend.BAD_NAME_CHARS else c for c in label).strip()
    return FILTER_PREFIX + (clean or "result")


def plan(labels: Sequence[str], existing: Sequence[str]) -> Tuple[Dict[str, str], List[str]]:
    """What to create and what to delete.

    ``labels``: the Comments of the result shapes in the model. ``existing``: the
    names of the filters in the model. Returns ``{name: label}`` of the filters
    to create, and the names of the Infrared filters that have no result.
    """
    wanted = {filter_name(label): label for label in labels if label}
    create = {name: label for name, label in wanted.items() if name not in existing}
    delete = [n for n in existing if n.startswith(FILTER_PREFIX) and n not in wanted]
    return create, delete


def _equals_rule(label: str) -> Any:
    from Autodesk.Revit.DB import (  # type: ignore
        BuiltInParameter,
        ElementId,
        ParameterFilterRuleFactory,
    )

    comments = ElementId(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    try:
        return ParameterFilterRuleFactory.CreateEqualsRule(comments, label)
    except TypeError:  # Revit 2021 and earlier: a third argument, case sensitive
        return ParameterFilterRuleFactory.CreateEqualsRule(comments, label, True)


def sync(doc: Any, labels: Sequence[str], show: str = "", hide: Sequence[str] = ()) -> str:
    """Make the filters agree with the result shapes. Return a line for the Watch text.

    ``labels``: the Comments of the result shapes. In the active view the result
    ``show`` is made visible and the results ``hide`` are hidden: the earlier
    results of the same target lie in the same place as the new one.
    """
    from Autodesk.Revit.DB import (  # type: ignore
        BuiltInCategory,
        ElementId,
        ElementParameterFilter,
        ParameterFilterElement,
    )
    from System.Collections.Generic import List as NetList  # type: ignore

    filters = {revit_legend.element_name(f): f for f in revit_legend._by_class(doc, ParameterFilterElement)}
    create, delete = plan(labels, list(filters))
    for name in delete:
        doc.Delete(filters.pop(name).Id)
    for name, label in create.items():
        categories = NetList[ElementId]()
        categories.Add(ElementId(BuiltInCategory.OST_GenericModel))
        filters[name] = ParameterFilterElement.Create(
            doc, name, categories, ElementParameterFilter(_equals_rule(label))
        )
    ours = [(name, f) for name, f in sorted(filters.items()) if name.startswith(FILTER_PREFIX)]
    if not ours:
        return "View filters: none (the result shapes have no run label)."
    shown, hidden = filter_name(show) if show else "", {filter_name(h) for h in hide}
    view = doc.ActiveView
    view_name = revit_legend.element_name(view) if view is not None else ""
    count = 0
    try:
        if view is None or not view.AreGraphicsOverridesAllowed():
            raise RuntimeError("this view type has no filters")
        applied = {str(i) for i in view.GetFilters()}
        for name, f in ours:
            if str(f.Id) not in applied:
                view.AddFilter(f.Id)  # visible at first; a filter already there keeps its state
            if name == shown:
                view.SetFilterVisibility(f.Id, True)
            elif name in hidden:
                view.SetFilterVisibility(f.Id, False)
                count += 1
    except Exception as error:
        return (
            "View filters: %d result filter(s) made, but not set in the view %r (%s). The results "
            "lie in the same place: in a 3D view, add the filters in Visibility/Graphics (VG) > "
            "Filters > Add and clear Visibility of the results to hide." % (len(ours), view_name, error)
        )
    return (
        "View filters: %d result(s) in the view %r; %d earlier result(s) of this target are hidden "
        "there. To show or hide a result, open Visibility/Graphics (VG) > Filters and change "
        "Visibility. Another view shows every result: add the filters there with Filters > Add."
        % (len(ours), view_name, count)
    )
