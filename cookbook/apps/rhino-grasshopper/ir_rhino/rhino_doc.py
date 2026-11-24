"""Rhino objects in, a coloured mesh out. Rhino only: import it inside Rhino.

RhinoCommon calls used here: ``RhinoDoc.ActiveDoc``, ``RhinoMath.UnitScale``,
``EarthAnchorPoint`` (``EarthLocationIsSet``, ``EarthBasepointLatitude``,
``EarthBasepointLongitude``, ``ModelBasePoint``, ``ModelNorth``),
``ObjectTable.GetSelectedObjects`` / ``GetObjectList`` / ``FindId`` / ``AddMesh`` / ``Hide``,
``Mesh.CreateFromBrep``, ``Mesh.Faces.ToIntArray``, ``Mesh.Vertices.ToFloatArray``,
``Layer``, ``ObjectAttributes`` with user strings.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from .site import Site, north_rad

LAYER = "Infrared"
TAG = "infrared"  # user string key; "result" on every drawn result
TARGET_TAG = "infrared-target"


def active_doc() -> Any:
    import Rhino  # type: ignore

    return Rhino.RhinoDoc.ActiveDoc


def read_site(doc: Any, lat: Optional[float] = None, lon: Optional[float] = None) -> Site:
    """The site of ``doc``: the EarthAnchorPoint, or ``lat`` and ``lon`` of the command.

    Raises
    ------
    ValueError
        When the model has no location and the command gives none.
    """
    import Rhino  # type: ignore

    unit_m = float(Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Meters))
    anchor = doc.EarthAnchorPoint
    is_set = bool(anchor.EarthLocationIsSet())
    north = anchor.ModelNorth if is_set else None
    turn = north_rad(float(north.X), float(north.Y)) if north is not None else 0.0
    base = anchor.ModelBasePoint if is_set else None
    base_xyz = (float(base.X), float(base.Y), float(base.Z)) if base is not None else (0.0, 0.0, 0.0)
    if (lat is None) != (lon is None):
        raise ValueError("Give both lat and lon, or neither.")
    if lat is not None and lon is not None:
        return Site(float(lon), float(lat), turn, base_xyz, unit_m, "command")
    if not is_set:
        raise ValueError(
            "The model has no location. Set it with the Rhino command EarthAnchorPoint, "
            "or add lat and lon to the command, for example: svf lat 48.2085 lon 16.3721"
        )
    return Site(
        float(anchor.EarthBasepointLongitude),
        float(anchor.EarthBasepointLatitude),
        turn,
        base_xyz,
        unit_m,
        "rhino",
    )


def is_result(obj: Any) -> bool:
    """True for an object this app drew: a result, or the public buildings of ``context``.

    It is never read back as a building: the context is fetched again by the SDK.
    """
    try:
        return obj.Attributes.GetUserString(TAG) in ("result", "context")
    except Exception:
        return False


def _mesh_of(geometry: Any) -> Any:
    """One triangle mesh of a Brep, Extrusion, Surface, SubD or Mesh; None for others."""
    import Rhino  # type: ignore

    g = Rhino.Geometry
    if isinstance(geometry, g.Mesh):
        mesh = geometry.DuplicateMesh()
    else:
        brep = None
        if isinstance(geometry, g.Brep):
            brep = geometry
        elif isinstance(geometry, g.SubD):
            brep = geometry.ToBrep(g.SubDToBrepOptions.Default)
        elif hasattr(geometry, "ToBrep"):  # Extrusion, Surface, Box
            brep = geometry.ToBrep()
        if brep is None:
            return None
        parts = g.Mesh.CreateFromBrep(brep, g.MeshingParameters.Default) or []
        mesh = g.Mesh()
        for part in parts:
            mesh.Append(part)
    if mesh.Faces.Count == 0:
        return None
    mesh.Faces.ConvertQuadsToTriangles()
    return mesh


def triangles(geometry: Any) -> Optional[List[float]]:
    """Flat ``x, y, z, ...`` (9 per triangle) in model units; None when not a solid or mesh."""
    mesh = _mesh_of(geometry)
    if mesh is None:
        return None
    xyz = np.array(list(mesh.Vertices.ToFloatArray()), dtype=np.float64).reshape(-1, 3)
    faces = np.array(list(mesh.Faces.ToIntArray(True)), dtype=np.int64).reshape(-1, 3)
    return xyz[faces].reshape(-1).tolist()


def _objects(doc: Any, items: Optional[Iterable[Any]]) -> List[Any]:
    """Rhino objects from ids, objects or nothing (the selection)."""
    if items is None:
        return list(doc.Objects.GetSelectedObjects(False, False))
    out = []
    for item in items:
        if hasattr(item, "Attributes") and hasattr(item, "Geometry"):
            out.append(item)
            continue
        found = doc.Objects.FindId(item) if not hasattr(item, "Faces") else None
        out.append(found if found is not None else item)
    return out


def _all_objects(doc: Any) -> List[Any]:
    import Rhino  # type: ignore

    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = False
    settings.LockedObjects = True
    settings.NormalObjects = True
    return list(doc.Objects.GetObjectList(settings))


def collect(
    doc: Any, items: Optional[Iterable[Any]], scope: str
) -> Tuple[Dict[str, List[float]], List[str]]:
    """``(buildings, notes)`` in model units, keyed by object id: the SDK ``buildings``.

    ``items``: ids, Rhino objects or bare geometry; None is the selection.
    ``scope``: "" (the selection) or "model" (every object). Infrared results are
    left out. Nothing else of the model is sent: the surroundings come from ``context``.
    """
    notes: List[str] = []
    if scope == "model":
        picked = [o for o in _all_objects(doc) if not is_result(o)]
    else:
        picked = _objects(doc, items)
        if not picked and items is None:
            notes.append(
                "Nothing is selected in Rhino. Click the buildings in a viewport (they turn "
                "yellow), then run again."
            )
    buildings: Dict[str, List[float]] = {}
    skipped = 0
    for k, obj in enumerate(picked):
        if hasattr(obj, "Attributes") and is_result(obj):
            skipped += 1
            continue
        geometry = obj.Geometry if hasattr(obj, "Geometry") else obj
        soup = triangles(geometry)
        if soup is None:
            skipped += 1
            continue
        key = str(obj.Id) if hasattr(obj, "Id") else "gh-%d" % k
        buildings[key] = soup
    if skipped:
        notes.append(
            "Skipped %d object(s): not a solid or mesh (curves, points, blocks), or an Infrared result."
            % skipped
        )
    return buildings, notes


CONTEXT_LAYER = "context"  # a sub-layer of LAYER
CONTEXT_GREY = (190, 190, 190)


def _layer_index(doc: Any, child: str = "") -> int:
    """The index of ``Infrared`` (or ``Infrared::<child>``); made when missing."""
    import Rhino  # type: ignore

    index = doc.Layers.FindByFullPath(LAYER, -1)
    if index < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = LAYER
        index = doc.Layers.Add(layer)
    if not child:
        return int(index)
    path = "%s::%s" % (LAYER, child)
    found = doc.Layers.FindByFullPath(path, -1)
    if found >= 0:
        return int(found)
    layer = Rhino.DocObjects.Layer()
    layer.Name = child
    layer.ParentLayerId = doc.Layers[int(index)].Id
    return int(doc.Layers.Add(layer))


def _net_array(values: np.ndarray, element_type: Any, count: int) -> Any:
    """A .NET array of ``count`` structs, filled with one memory copy of ``values``.

    ``Point3d`` is 3 doubles and ``MeshFace`` 4 ints, both plain sequential
    structs: the bytes of a C-ordered numpy array of that shape are the array.
    One copy instead of one Python call per vertex: a facade result of 1.3
    million triangles took over a minute the slow way (live run 2026-11-19).
    """
    import ctypes

    import System  # type: ignore
    from System.Runtime.InteropServices import GCHandle, GCHandleType  # type: ignore

    data = np.ascontiguousarray(values)
    out = System.Array.CreateInstance(element_type, count)
    if count:
        handle = GCHandle.Alloc(out, GCHandleType.Pinned)
        try:
            ctypes.memmove(int(handle.AddrOfPinnedObject().ToInt64()), data.ctypes.data, data.nbytes)
        finally:
            handle.Free()
    return out


def _plain_mesh(tri: np.ndarray) -> Any:
    """A Rhino mesh of ``(k, 3, 3)`` triangles, each with its own 3 vertices."""
    import Rhino  # type: ignore

    g = Rhino.Geometry
    k = len(tri)
    mesh = g.Mesh()
    mesh.Vertices.AddVertices(_net_array(tri.reshape(-1, 3).astype(np.float64), g.Point3d, 3 * k))
    first = np.arange(0, 3 * k, 3, dtype=np.int32)
    faces = np.stack([first, first + 1, first + 2, first + 2], axis=1)  # D == C: a triangle
    mesh.Faces.AddFaces(_net_array(faces, g.MeshFace, k))
    return mesh


def _mesh(tri_model: np.ndarray, rgb: Optional[np.ndarray] = None) -> Any:
    """A Rhino mesh of ``(n, 3, 3)`` triangles; with ``rgb`` (n, 3) a colour per triangle.

    With colours: one single-colour mesh per colour (at most the 256 of the
    legend), joined with one ``Append``. So the number of calls into Rhino
    does not grow with the number of triangles.
    """
    import Rhino  # type: ignore
    import System  # type: ignore
    from System.Collections.Generic import List as NetList  # type: ignore

    tri = np.asarray(tri_model, dtype=np.float64).reshape(-1, 3, 3)
    if rgb is None:
        mesh = _plain_mesh(tri)
    else:
        colour = np.asarray(rgb, dtype=np.int64).reshape(-1, 3)
        key = (colour[:, 0] << 16) | (colour[:, 1] << 8) | colour[:, 2]
        parts = NetList[Rhino.Geometry.Mesh]()
        groups = []
        for value in np.unique(key).tolist():
            part = _plain_mesh(tri[key == value])
            shade = System.Drawing.Color.FromArgb((value >> 16) & 255, (value >> 8) & 255, value & 255)
            part.VertexColors.CreateMonotoneMesh(shade)
            parts.Add(part)
            groups.append((shade, part.Vertices.Count))
        mesh = Rhino.Geometry.Mesh()
        mesh.Append(parts)
        if mesh.VertexColors.Count != mesh.Vertices.Count:  # Append did not keep them: slow but right
            colours = System.Array.CreateInstance(System.Drawing.Color, mesh.Vertices.Count)
            i = 0
            for shade, count in groups:
                for _ in range(count):
                    colours[i] = shade
                    i += 1
            mesh.VertexColors.SetColors(colours)
    # One zero-area triangle (facade results have some) makes the whole mesh
    # invalid, and AddMesh then adds nothing. Compact drops the unused vertices
    # with their colours, so the colours stay with their faces.
    mesh.Faces.CullDegenerateFaces()
    mesh.Compact()
    mesh.Normals.ComputeNormals()
    return mesh


def ground_meshes(polygons: Dict[str, List[List[np.ndarray]]], rgb: Dict[str, Tuple[int, int, int]],
                  tolerance: float, lift: float = 0.0) -> List[Any]:
    """One coloured mesh per material. ``polygons``: ``{material: [[outer, hole, ...], ...]}``,
    each ring ``(m, 3)`` model points on one plane. Holes stay open (a planar Brep of the rings)."""
    import Rhino  # type: ignore
    import System  # type: ignore
    from System.Collections.Generic import List as NetList  # type: ignore

    g = Rhino.Geometry
    settings = g.MeshingParameters.FastRenderMesh
    out = []
    for material in sorted(polygons):
        parts = NetList[g.Mesh]()
        for rings in polygons[material]:
            curves = NetList[g.Curve]()
            outline = None
            for ring in rings:
                points = [g.Point3d(float(x), float(y), float(z)) for x, y, z in ring]
                if points[0].DistanceTo(points[-1]) > tolerance:
                    points.append(points[0])
                if len(points) >= 4:
                    curves.Add(g.PolylineCurve(points))
                    outline = outline or g.Polyline(points)
            if not curves.Count:
                continue
            breps = g.Brep.CreatePlanarBreps(curves, tolerance)
            if breps is None:  # a ring that is not planar or crosses itself: its outline only
                mesh = g.Mesh.CreateFromClosedPolyline(outline)
                if mesh is not None:
                    parts.Add(mesh)
                continue
            for brep in breps:
                for mesh in g.Mesh.CreateFromBrep(brep, settings) or []:
                    parts.Add(mesh)
        if not parts.Count:
            continue
        mesh = g.Mesh()
        mesh.Append(parts)
        mesh.Faces.CullDegenerateFaces()  # a sliver of the public data makes the mesh invalid
        mesh.Compact()
        # Each material a little higher (lift, model units) than the one before, so that two
        # that overlap do not flicker. Only the picture: the SDK gets the flat polygons.
        mesh.Translate(0.0, 0.0, lift * len(out))
        r, gr, b = rgb.get(material, (200, 200, 200))
        mesh.VertexColors.CreateMonotoneMesh(System.Drawing.Color.FromArgb(r, gr, b))
        mesh.Normals.ComputeNormals()
        out.append(mesh)
    return out


def _added(new_id: Any, what: str) -> Any:
    """``new_id``, or ``RuntimeError`` when Rhino added nothing (an empty id)."""
    import System  # type: ignore

    if new_id == System.Guid.Empty:
        raise RuntimeError("Rhino did not add the %s mesh (the mesh is not valid)." % what)
    return new_id


def add_context(doc: Any, soups_model: Dict[str, List[float]], label: str) -> Tuple[Any, int]:
    """Draw the public buildings of ``context`` as one grey mesh on ``Infrared::context``.

    The context drawn by an earlier command is deleted first: the same area
    must not be drawn twice. Returns ``(object id, number of buildings)``.
    """
    import Rhino  # type: ignore
    import System  # type: ignore

    for obj in _all_objects(doc):
        if obj.Attributes.GetUserString(TAG) == "context":
            doc.Objects.Delete(obj, True)
    if not soups_model:
        return None, 0
    tri = np.concatenate([np.asarray(s, dtype=np.float64) for s in soups_model.values()])
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = _layer_index(doc, CONTEXT_LAYER)
    attributes.Name = "context - %s" % label
    attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = System.Drawing.Color.FromArgb(*CONTEXT_GREY)
    attributes.SetUserString(TAG, "context")
    new_id = _added(doc.Objects.AddMesh(_mesh(tri.reshape(-1, 3, 3)), attributes), "context")
    doc.Views.Redraw()
    return new_id, len(soups_model)


def add_result(doc: Any, tri_model: np.ndarray, rgb: np.ndarray, target: str, label: str) -> Any:
    """Add one mesh with a colour per triangle; hide the earlier results of ``target``.

    Returns the id of the new object.
    """
    import Rhino  # type: ignore

    mesh = _mesh(tri_model, rgb)
    if not mesh.IsValid:  # check before hiding the earlier results
        raise RuntimeError("The %s result mesh is not valid; nothing was drawn." % target)
    for obj in _all_objects(doc):
        if obj.Attributes.GetUserString(TARGET_TAG) == target:
            doc.Objects.Hide(obj, True)
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = _layer_index(doc)
    attributes.Name = "%s - %s" % (target, label)
    attributes.SetUserString(TAG, "result")
    attributes.SetUserString(TARGET_TAG, target)
    new_id = _added(doc.Objects.AddMesh(mesh, attributes), "%s result" % target)
    doc.Views.Redraw()
    return new_id
