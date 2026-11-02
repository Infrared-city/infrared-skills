"""Show a result in the ACTIVE Revit view with the Analysis Visualization Framework (AVF).

Both results are drawn as coloured points (no face reference):

* ground: one point at the centre of each grid cell;
* facades (v1): one point at the centre of each result triangle.

Revit draws them as markers with one legend (title and unit of the result).
The legend range is the range of the data: Revit takes it from the values.

Dynamo wraps a node run in a transaction. This file asks Dynamo's
``TransactionManager`` for it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from . import revit_location

SCHEMA_NAME = "Infrared"
STYLE_NAME = "Infrared"
POINTS_PER_PRIMITIVE = 5000
MARKER_SIZE = 6.0  # points on screen


def _supported_view_types() -> List[Any]:
    from Autodesk.Revit.DB import ViewType  # type: ignore

    return [
        ViewType.ThreeD,
        ViewType.FloorPlan,
        ViewType.CeilingPlan,
        ViewType.EngineeringPlan,
        ViewType.AreaPlan,
        ViewType.Elevation,
        ViewType.Section,
    ]


def check_view(view: Any) -> str:
    """An empty text if AVF can draw in this view, else the reason (for the user)."""
    if view is None:
        return "There is no active view."
    if view.ViewType not in _supported_view_types():
        return (
            "The active view is a %s. Open a 3D view or a plan, section or "
            "elevation view and run again." % view.ViewType
        )
    return ""


def point_set(result: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """The points (flat x, y, z in the Revit frame, metres) and the values of a result.

    Facade triangles give the centre of each triangle (v1).
    """
    if result["kind"] == "points":
        points = np.asarray(result["points"], dtype=np.float64).reshape(-1)
    else:
        corners = np.asarray(result["triangles"], dtype=np.float64).reshape(-1, 3, 3)
        points = corners.mean(axis=1).reshape(-1)
    return points, np.asarray(result["values"], dtype=np.float64)


def _display_style(doc: Any) -> Any:
    """Create the "Infrared" analysis display style: marker points and a legend."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import (  # type: ignore
        AnalysisDisplayColorSettings,
        AnalysisDisplayLegendSettings,
        AnalysisDisplayMarkersAndTextSettings,
        AnalysisDisplayStyle,
        AnalysisDisplayStyleMarkerType,
        Color,
        FilteredElementCollector,
    )

    style_type = clr.GetClrType(AnalysisDisplayStyle)
    for old in FilteredElementCollector(doc).OfClass(style_type):
        if old.Name == STYLE_NAME:
            doc.Delete(old.Id)  # create it fresh: no guessing which setter exists
    markers = AnalysisDisplayMarkersAndTextSettings()
    markers.MarkerType = AnalysisDisplayStyleMarkerType.Circle
    markers.MarkerSize = MARKER_SIZE
    markers.ShowText = False
    colors = AnalysisDisplayColorSettings()
    colors.MinColor = Color(0, 0, 255)  # blue = low
    colors.MaxColor = Color(255, 0, 0)  # red = high
    legend = AnalysisDisplayLegendSettings()
    legend.NumberOfSteps = 10
    legend.ShowLegend = True
    legend.ShowDataDescription = True
    return AnalysisDisplayStyle.CreateAnalysisDisplayStyle(
        doc, STYLE_NAME, markers, colors, legend
    )


def _schema_index(sfm: Any, title: str, unit: str) -> int:
    """Register the result schema (legend title and unit). Return its index."""
    from Autodesk.Revit.DB.Analysis import AnalysisResultSchema  # type: ignore
    from System import Double, String  # type: ignore
    from System.Collections.Generic import List as NetList  # type: ignore

    schema = AnalysisResultSchema("%s - %s" % (SCHEMA_NAME, title), unit)
    names = NetList[String]()
    names.Add(unit)
    multipliers = NetList[Double]()
    multipliers.Add(1.0)
    schema.SetUnits(names, multipliers)
    for index, known in dict(sfm.GetRegisteredResults()).items():
        if known.Name == schema.Name:
            sfm.SetResultSchema(index, schema)
            return int(index)
    return int(sfm.RegisterResult(schema))


def _add_points(
    sfm: Any, schema_index: int, feet: np.ndarray, values: Sequence[float]
) -> None:
    from Autodesk.Revit.DB import XYZ  # type: ignore
    from Autodesk.Revit.DB.Analysis import (  # type: ignore
        FieldDomainPointsByXYZ,
        FieldValues,
        ValueAtPoint,
    )
    from System import Double  # type: ignore
    from System.Collections.Generic import List as NetList  # type: ignore

    xyz = feet.reshape(-1, 3)
    step = POINTS_PER_PRIMITIVE
    for start in range(0, len(xyz), step):
        points = NetList[XYZ]()
        at_points = NetList[ValueAtPoint]()
        for row, value in zip(xyz[start : start + step], values[start : start + step]):
            points.Add(XYZ(float(row[0]), float(row[1]), float(row[2])))
            one = NetList[Double]()
            one.Add(float(value))
            at_points.Add(ValueAtPoint(one))
        primitive = sfm.AddSpatialFieldPrimitive()  # no face: points in space
        sfm.UpdateSpatialFieldPrimitive(
            primitive,
            FieldDomainPointsByXYZ(points),
            FieldValues(at_points),
            schema_index,
        )


def show(result: Dict[str, Any], title: str, unit: str, true_north_rad: float) -> str:
    """Draw the result in the active view. Return one line for the user.

    Parameters
    ----------
    result : dict
        ``results.ground_points`` or ``results.facade_triangles`` of ir_dynamo.
    title, unit : str
        Legend title and unit.
    true_north_rad : float
        The angle that ``revit_geometry`` used. The points are turned back with it.
    """
    from Autodesk.Revit.DB.Analysis import SpatialFieldManager  # type: ignore
    from RevitServices.Persistence import DocumentManager  # type: ignore
    from RevitServices.Transactions import TransactionManager  # type: ignore

    doc = DocumentManager.Instance.CurrentDBDocument
    view = doc.ActiveView
    problem = check_view(view)
    if problem:
        return problem
    metres, values = point_set(result)
    if values.size == 0:
        return "The result has no values to show."
    feet = revit_location.site_m_to_internal_ft(metres, true_north_rad)
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        sfm = SpatialFieldManager.GetSpatialFieldManager(view)
        if sfm is None:
            sfm = SpatialFieldManager.CreateSpatialFieldManager(view, 1)
        sfm.Clear()
        index = _schema_index(sfm, title, unit)
        _add_points(sfm, index, feet, values)
        view.AnalysisDisplayStyleId = _display_style(doc).Id
    except Exception:
        TransactionManager.Instance.ForceCloseTransaction()
        raise
    TransactionManager.Instance.TransactionTaskDone()
    return "Showed %d points in view '%s': %s (%s), %.3g to %.3g." % (
        values.size,
        view.Name,
        title,
        unit,
        float(values.min()),
        float(values.max()),
    )
