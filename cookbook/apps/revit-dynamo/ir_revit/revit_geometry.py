"""Selected Revit elements -> triangles in the Revit frame (metres, true north).

One building per element. Its id is the ElementId as text. The triangles come
from the solids of the element at Fine detail, including the solids inside
family instances. Feet become metres and the model is turned to true north by
``revit_location``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

from . import revit_location


def flatten(items: Any) -> Iterator[Any]:
    """Walk nested lists (Dynamo gives lists of lists) and yield each element."""
    if isinstance(items, (list, tuple)):
        for item in items:
            for inner in flatten(item):
                yield inner
    elif items is not None:
        yield items


def unwrap(element: Any) -> Any:
    """A Dynamo element wrapper -> the Revit API element (``InternalElement``)."""
    return getattr(element, "InternalElement", element)


def element_key(element: Any) -> str:
    """The ElementId of an element as text. Revit 2024+ has ``Id.Value``."""
    eid = element.Id
    value = getattr(eid, "Value", None)
    if value is None:
        value = getattr(eid, "IntegerValue", None)
    return str(value if value is not None else eid)


def _solids(geometry: Any, depth: int = 0) -> Iterator[Any]:
    """Yield the solids of a GeometryElement. Go into family instances."""
    from Autodesk.Revit.DB import GeometryInstance, Solid  # type: ignore

    if geometry is None or depth > 8:
        return
    for item in geometry:
        if isinstance(item, Solid):
            if item.Volume > 0 and item.Faces.Size > 0:
                yield item
        elif isinstance(item, GeometryInstance):
            # GetInstanceGeometry: already moved to model (internal) coordinates.
            for solid in _solids(item.GetInstanceGeometry(), depth + 1):
                yield solid


def _solid_triangles_ft(solid: Any) -> List[float]:
    """The triangles of the faces of one solid: flat x, y, z in feet."""
    out: List[float] = []
    for face in solid.Faces:
        mesh = face.Triangulate()
        if mesh is None:
            continue
        for index in range(mesh.NumTriangles):
            triangle = mesh.get_Triangle(index)
            for corner in range(3):
                vertex = triangle.get_Vertex(corner)
                out.extend((vertex.X, vertex.Y, vertex.Z))
    return out


def collect_buildings(
    elements: Any, true_north_rad: float
) -> Tuple[Dict[str, List[float]], List[str]]:
    """Read the geometry of the selected elements.

    Parameters
    ----------
    elements : Any
        What the Dynamo "Select Model Elements" node gives: elements or lists
        of elements (Dynamo wrappers or Revit API elements).
    true_north_rad : float
        ``revit_location.SiteLocation.true_north_rad``.

    Returns
    -------
    buildings_m : dict
        ``{ElementId text: flat [x, y, z, ...]}``, 9 numbers per triangle,
        metres, Revit frame (x east, y true north, z up).
    warnings : list of str
        One text for each element that gave no solid.
    """
    from Autodesk.Revit.DB import Options, ViewDetailLevel  # type: ignore

    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    options.ComputeReferences = False
    options.IncludeNonVisibleObjects = False
    buildings: Dict[str, List[float]] = {}
    warnings: List[str] = []
    for item in flatten(elements):
        element = unwrap(item)
        key = element_key(element)
        feet: List[float] = []
        for solid in _solids(element.get_Geometry(options)):
            feet.extend(_solid_triangles_ft(solid))
        if not feet:
            warnings.append("Element %s has no solid geometry. It is skipped." % key)
            continue
        metres = revit_location.internal_ft_to_site_m(feet, true_north_rad)
        buildings[key] = metres.tolist()
    return buildings, warnings
