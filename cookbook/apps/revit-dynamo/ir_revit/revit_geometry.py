"""Selected Revit elements -> triangles in the Revit frame (metres, true north).

The selection is split in two: terrain (a Toposolid, or a legacy
TopographySurface) and buildings (everything else). With no terrain in the
selection, every terrain element of the document is used.

One building per element. Its id is the ElementId as text. The triangles come
from the solids of the element at Fine detail, including the solids inside
family instances. A TopographySurface gives a Mesh instead of a Solid: its
triangles are read directly. Feet become metres and the model is turned to true
north by ``revit_location``.

Revit API calls used here (nothing else): ``Element.get_Geometry``, ``Options``,
``Solid.Faces``, ``Face.Triangulate``, ``Face.GetBoundingBox``,
``Face.ComputeNormal``, ``Mesh.NumTriangles``, ``Mesh.get_Triangle``,
``MeshTriangle.get_Vertex``, ``GeometryInstance.GetInstanceGeometry``,
``FilteredElementCollector.OfClass`` with ``Toposolid`` / ``TopographySurface``.
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


def _solids(geometry: Any, depth: int = 0, meshes: bool = False) -> Iterator[Any]:
    """Yield the solids of a GeometryElement (and its Mesh objects if ``meshes``).

    Go into family instances.
    """
    from Autodesk.Revit.DB import GeometryInstance, Mesh, Solid  # type: ignore

    if geometry is None or depth > 8:
        return
    for item in geometry:
        if isinstance(item, Solid):
            if item.Volume > 0 and item.Faces.Size > 0:
                yield item
        elif meshes and isinstance(item, Mesh):
            yield item
        elif isinstance(item, GeometryInstance):
            # GetInstanceGeometry: already moved to model (internal) coordinates.
            for solid in _solids(item.GetInstanceGeometry(), depth + 1, meshes):
                yield solid


def _mesh_triangles_ft(mesh: Any) -> List[float]:
    """The triangles of a Revit Mesh (or a face triangulation): flat x, y, z in feet."""
    out: List[float] = []
    for index in range(mesh.NumTriangles):
        triangle = mesh.get_Triangle(index)
        for corner in range(3):
            vertex = triangle.get_Vertex(corner)
            out.extend((vertex.X, vertex.Y, vertex.Z))
    return out


def _faces_up(face: Any) -> bool:
    """True when the face normal, at the middle of the face, points up (z > 0.01)."""
    from Autodesk.Revit.DB import UV  # type: ignore

    try:
        box = face.GetBoundingBox()
        middle = UV(0.5 * (box.Min.U + box.Max.U), 0.5 * (box.Min.V + box.Max.V))
        return face.ComputeNormal(middle).Z > 0.01
    except Exception:
        # Unknown: keep the face. ir_dynamo.terrain turns every triangle up and
        # drops the steep ones.
        return True


def _solid_triangles_ft(solid: Any, up_only: bool = False) -> List[float]:
    """The triangles of the faces of one solid: flat x, y, z in feet.

    ``up_only`` skips the faces whose normal points down or sideways (the
    underside and the edge of a terrain slab).
    """
    out: List[float] = []
    for face in solid.Faces:
        if up_only and not _faces_up(face):
            continue
        mesh = face.Triangulate()
        if mesh is None:
            continue
        out.extend(_mesh_triangles_ft(mesh))
    return out


def _terrain_classes() -> List[Any]:
    """Toposolid (Revit 2024+) and TopographySurface. A class that is missing is left out."""
    import Autodesk.Revit.DB as db  # type: ignore

    names = ("Toposolid", "TopographySurface")
    return [getattr(db, n) for n in names if getattr(db, n, None) is not None]


def is_terrain(element: Any) -> bool:
    """True for a Toposolid or a TopographySurface."""
    return any(isinstance(element, cls) for cls in _terrain_classes())


def _document_terrain(doc: Any) -> List[Any]:
    """Every terrain element of the document (not in a linked file)."""
    import clr  # type: ignore
    from Autodesk.Revit.DB import FilteredElementCollector  # type: ignore

    found: List[Any] = []
    for cls in _terrain_classes():
        found.extend(FilteredElementCollector(doc).OfClass(clr.GetClrType(cls)))
    return found


def _options() -> Any:
    from Autodesk.Revit.DB import Options, ViewDetailLevel  # type: ignore

    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    options.ComputeReferences = False
    options.IncludeNonVisibleObjects = False
    return options


def _terrain_feet(element: Any, options: Any) -> List[float]:
    feet: List[float] = []
    for item in _solids(element.get_Geometry(options), meshes=True):
        if hasattr(item, "NumTriangles"):  # a Mesh (TopographySurface)
            feet.extend(_mesh_triangles_ft(item))
        else:
            feet.extend(_solid_triangles_ft(item, up_only=True))
    return feet


def collect_scene(
    doc: Any, elements: Any, true_north_rad: float
) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], List[str]]:
    """Read the selected elements: buildings and terrain.

    Parameters
    ----------
    doc : Autodesk.Revit.DB.Document
        Used only to find the terrain when the selection holds none.
    elements : Any
        What the Dynamo "Select Model Elements" node gives: elements or lists
        of elements (Dynamo wrappers or Revit API elements).
    true_north_rad : float
        ``revit_location.SiteLocation.true_north_rad``.

    Returns
    -------
    buildings_m, terrain_m : dict
        ``{ElementId text: flat [x, y, z, ...]}``, 9 numbers per triangle,
        metres, Revit frame (x east, y true north, z up). Terrain triangles are
        the upward faces only.
    warnings : list of str
        One text for each element that gave no geometry, and a line when the
        terrain was taken from the document.
    """
    options = _options()
    buildings: Dict[str, List[float]] = {}
    terrain: Dict[str, List[float]] = {}
    warnings: List[str] = []
    picked = [unwrap(item) for item in flatten(elements)]
    terrain_elements = [e for e in picked if is_terrain(e)]
    if not terrain_elements:
        terrain_elements = _document_terrain(doc)
        if terrain_elements:
            warnings.append(
                "No terrain selected: using the %d terrain element(s) of the document."
                % len(terrain_elements)
            )
    for element in terrain_elements:
        key = element_key(element)
        feet = _terrain_feet(element, options)
        if not feet:
            warnings.append("Terrain %s has no geometry. It is skipped." % key)
            continue
        terrain[key] = revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
    for element in picked:
        if is_terrain(element):
            continue
        key = element_key(element)
        feet = []
        for solid in _solids(element.get_Geometry(options)):
            feet.extend(_solid_triangles_ft(solid))
        if not feet:
            warnings.append("Element %s has no solid geometry. It is skipped." % key)
            continue
        buildings[key] = revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
    return buildings, terrain, warnings
