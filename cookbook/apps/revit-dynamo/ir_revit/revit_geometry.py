"""Selected Revit elements -> triangles in the Revit frame (metres, true north).

The terrain is what the ``terrain`` input holds, of any type (a Toposolid, a
floor, a mass, an import). With an empty ``terrain`` input, the Toposolids and
TopographySurfaces in the main selection are terrain; with none there either,
every terrain element of the document is used. Everything else is a building.
A linked Revit model is not read (its elements are in another document).

One building per element. Its id is the ElementId as text. The triangles come
from the solids of the element at Fine detail, including the solids inside
family instances. A TopographySurface, a DirectShape or an imported model can
give a Mesh instead of a Solid: its triangles are read directly. The result
shapes this script draws (``revit_display.APP_ID``) are never read back. Feet become metres and the model is turned to true
north by ``revit_location``.

Revit API calls used here (nothing else): ``Element.get_Geometry``, ``Options``,
``Solid.Faces``, ``Face.Triangulate``, ``Face.GetBoundingBox``,
``Face.ComputeNormal``, ``Mesh.NumTriangles``, ``Mesh.get_Triangle``,
``MeshTriangle.get_Vertex``, ``GeometryInstance.GetInstanceGeometry``,
``FilteredElementCollector.OfClass`` with ``Toposolid`` / ``TopographySurface``,
``Element.Category``, ``Element.ApplicationId`` (a DirectShape).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from ir_dynamo import summary

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


def _element_feet(element: Any, options: Any) -> List[float]:
    """The triangles of the solids and meshes of one element: flat x, y, z in feet."""
    feet: List[float] = []
    for item in _solids(element.get_Geometry(options), meshes=True):
        if hasattr(item, "NumTriangles"):  # a Mesh
            feet.extend(_mesh_triangles_ft(item))
        else:
            feet.extend(_solid_triangles_ft(item))
    return feet


def describe(element: Any) -> str:
    """``"Walls, Wall"``: the category and the class of an element, for a message."""
    category = getattr(getattr(element, "Category", None), "Name", None) or "no category"
    try:
        kind = element.GetType().Name
    except Exception:
        kind = type(element).__name__
    return "%s, %s" % (category, kind)


def category_names(element: Any) -> Tuple[str, str]:
    """``("OST_Walls", "Walls")``: the BuiltInCategory name and the display name."""
    category = getattr(element, "Category", None)
    if category is None:
        return "", ""
    builtin = ""
    try:  # the enum name, e.g. "OST_Walls"; str() of a .NET enum can be a number
        import clr  # type: ignore
        from System import Enum  # type: ignore
        from Autodesk.Revit.DB import BuiltInCategory  # type: ignore

        builtin = str(Enum.GetName(clr.GetClrType(BuiltInCategory), category.BuiltInCategory) or "")
    except Exception:
        try:
            builtin = str(category.BuiltInCategory)
        except Exception:
            builtin = ""
    return builtin, str(getattr(category, "Name", "") or "")


def is_link(element: Any) -> bool:
    """True for a linked Revit model (``RevitLinkInstance``)."""
    try:
        return element.GetType().Name == "RevitLinkInstance"
    except Exception:
        return False


def _link_warning(element: Any) -> str:
    return (
        "Element %s is a linked Revit model. Its elements are not read: open the "
        "linked file, or bind the link, and select the elements there." % element_key(element)
    )


def is_own_result(element: Any) -> bool:
    """True for a result shape that this script drew (it must not be analysed)."""
    from .revit_display import APP_ID

    return getattr(element, "ApplicationId", None) == APP_ID


def _terrain_feet(element: Any, options: Any) -> List[float]:
    feet: List[float] = []
    for item in _solids(element.get_Geometry(options), meshes=True):
        if hasattr(item, "NumTriangles"):  # a Mesh (TopographySurface)
            feet.extend(_mesh_triangles_ft(item))
        else:
            feet.extend(_solid_triangles_ft(item, up_only=True))
    return feet


TERRAIN_HINT = (
    "A ground modelled as a floor, a mass or an import is not terrain: it is analysed "
    "as a building. Model the site as a Toposolid."
)


def collect_scene(
    doc: Any,
    elements: Any,
    true_north_rad: float,
    terrain_selection: Any = None,
    skip: Optional[Callable[[str, str], bool]] = None,
    categories: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], List[str]]:
    """Read the selected elements: buildings and terrain.

    Parameters
    ----------
    doc : Autodesk.Revit.DB.Document
        Used only to find the terrain when no terrain is selected.
    elements : Any
        What the Dynamo "Select Model Elements" node gives: elements or lists
        of elements (Dynamo wrappers or Revit API elements).
    true_north_rad : float
        ``revit_location.SiteLocation.true_north_rad``.
    terrain_selection : Any
        The ``terrain`` input (same shape as ``elements``). Each element in it
        is terrain, of any type, and is not a building.
    skip : callable, optional
        ``skip(builtin_name, display_name)``: True leaves the element out (for
        example ``ir_dynamo.obj_export.not_building``). One summary line counts them.
    categories : dict, optional
        Filled with ``{ElementId text: category display name}`` of each building.

    Returns
    -------
    buildings_m, terrain_m : dict
        ``{ElementId text: flat [x, y, z, ...]}``, 9 numbers per triangle,
        metres, Revit frame (x east, y true north, z up). Terrain triangles are
        the upward faces only.
    warnings : list of str
        The categories of the selection, one text for each element that gave
        no geometry, and a line that says where the terrain came from.
    """
    options = _options()
    buildings: Dict[str, List[float]] = {}
    terrain: Dict[str, List[float]] = {}
    picked = [unwrap(item) for item in flatten(elements)]
    chosen = [unwrap(item) for item in flatten(terrain_selection)]
    warnings: List[str] = [summary.selection_line("Selection", [describe(e) for e in picked])]
    if chosen:
        warnings.append(summary.selection_line("Terrain input", [describe(e) for e in chosen]))
        terrain_elements = chosen
    else:
        terrain_elements = [e for e in picked if is_terrain(e)]
        if terrain_elements:
            warnings.append("Terrain: the Toposolids and Topography surfaces of the selection.")
        else:
            terrain_elements = _document_terrain(doc)
            warnings.append(
                "Terrain: no Toposolid in the selection; using the %d Toposolid and "
                "Topography element(s) of the document. %s" % (len(terrain_elements), TERRAIN_HINT)
            )
    terrain_keys = set()
    for element in terrain_elements:
        key = element_key(element)
        terrain_keys.add(key)
        if is_link(element):
            warnings.append(_link_warning(element))
            continue
        feet = _terrain_feet(element, options)
        if not feet:
            warnings.append("Terrain %s (%s) has no geometry. It is skipped." % (key, describe(element)))
            continue
        terrain[key] = revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
    own = 0
    skipped: List[str] = []
    empty: List[str] = []
    for element in picked:
        key = element_key(element)
        if key in terrain_keys or (not chosen and is_terrain(element)):
            continue
        if is_own_result(element):
            own += 1
            continue
        if is_link(element):
            warnings.append(_link_warning(element))
            continue
        builtin, name = category_names(element)
        if skip is not None and skip(builtin, name):
            skipped.append(describe(element))
            continue
        feet = _element_feet(element, options)
        if not feet:
            empty.append(describe(element))
            continue
        buildings[key] = revit_location.internal_ft_to_site_m(feet, true_north_rad).tolist()
        if categories is not None:
            categories[key] = name or "no category"
    if skipped:
        warnings.append(summary.selection_line("Left out (not a building category)", skipped))
    if empty:
        warnings.append(summary.selection_line("Skipped, no 3D geometry", empty))
    if own:
        warnings.append("%d Infrared result shape(s) in the selection are not analysed." % own)
    return buildings, terrain, warnings
