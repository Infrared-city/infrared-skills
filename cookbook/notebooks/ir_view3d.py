"""3D views for the cookbook notebooks (pyvista, off-screen PNG).

One look for every notebook: light ground, soft light, grey context, a
coloured result, a colour bar with units, the same camera rules.

    cells = v3.cells_mesh(result.columns.render_buffers())
    pl = v3.plotter()
    v3.add_ground(pl, cells.bounds)
    v3.add_meshes(pl, buildings)                     # your {id: mesh} dict
    v3.add_values(pl, cells, cmap="inferno", clim=(0, 450))
    v3.show(pl, "solar.png", cmap="inferno", clim=(0, 450), label="kWh/m²", title="Sun")

On a server without a display, run under `xvfb-run -a`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pyvista as pv
import shapely

pv.OFF_SCREEN = True
BACKGROUND = "#f4f2ee"  # warm paper white
GROUND = "#e9e6df"
CONTEXT = "#c4bfb5"
TEXT = "#333333"


def cells_mesh(buffers: Any) -> pv.PolyData:
    """Render buffers -> triangles for each cell that has a value.

    `buffers` is `result.columns.render_buffers()`. A frame is one flat
    wall or roof part with a regular grid of `nu x nv` cells. A point
    `(s, t)` of the frame (in cell units) is at `corner + s*u_step + t*v_step`.
    The `outline` triangles give the exact border of the surface, so we cut
    the edge cells to it: no cell sticks out over a roof edge.
    The values keep their wire type (f16 or f32); we widen them to float32.
    A cell with a clear validity bit has no value: we drop it.
    """
    frames = np.asarray(buffers.frames, dtype=np.float64).reshape(-1, 9)
    dims = np.asarray(buffers.dims, dtype=np.int64).reshape(-1, 3)
    values = np.asarray(buffers.values, dtype=np.float32)
    valid = np.unpackbits(np.asarray(buffers.validity), bitorder="little")[: len(values)]

    # The frame and the (row, column) of every valid cell, without a loop.
    per_frame = dims[:, 0] * dims[:, 1]
    frame_of = np.repeat(np.arange(len(dims)), per_frame)
    local = np.arange(per_frame.sum()) - np.repeat(dims[:, 2], per_frame)
    keep = np.flatnonzero(valid[: len(frame_of)].astype(bool))
    f, local = frame_of[keep], local[keep]
    row, col = local // dims[f, 0], local % dims[f, 0]

    # Outline of each frame as one polygon in (s, t), then cut the cells.
    tri = np.asarray(buffers.outline, dtype=np.float64).reshape(-1, 3, 2)
    offsets = np.asarray(buffers.outline_offsets, dtype=np.int64)
    tri_polys = shapely.polygons(tri)
    outline = np.array([shapely.union_all(tri_polys[a:b]) for a, b in zip(offsets[:-1], offsets[1:])])
    cells = shapely.box(col, row, col + 1, row + 1)
    shapely.prepare(outline)
    inside = shapely.contains(outline[f], cells)
    cut = np.flatnonzero(~inside)
    cells[cut] = shapely.intersection(cells[cut], outline[f[cut]])

    # Triangulate every cell polygon (a quad gives two triangles).
    parts, owner = shapely.get_parts(shapely.constrained_delaunay_triangles(cells), return_index=True)
    st = shapely.get_coordinates(parts.astype(object)).reshape(-1, 4, 2)[:, :3]  # drop ring closure
    ff = f[owner]
    corner, u, v = frames[ff, 0:3], frames[ff, 3:6], frames[ff, 6:9]
    xyz = corner[:, None] + st[..., :1] * u[:, None] + st[..., 1:] * v[:, None]
    points = xyz.reshape(-1, 3) + np.asarray(buffers.anchor)  # back to site metres
    faces = np.c_[np.full(len(parts), 3), np.arange(3 * len(parts)).reshape(-1, 3)]
    mesh = pv.PolyData(points, faces.ravel())
    mesh.cell_data["value"] = values[dims[ff, 2] + local[owner]]
    return mesh


def is_wall(mesh: pv.PolyData) -> np.ndarray:
    """True for the cells of a mesh that stand (near) vertical."""
    normals = mesh.compute_normals(cell_normals=True, point_normals=False)["Normals"]
    return np.abs(normals[:, 2]) < 0.5


def mesh_from_dicts(meshes: Mapping[str, dict] | Iterable[dict]) -> pv.PolyData:
    """`{id: {coordinates, indices}}` (the SDK mesh shape) -> one PolyData."""
    items = meshes.values() if isinstance(meshes, Mapping) else meshes
    parts = []
    for m in items:
        pts = np.asarray(m["coordinates"], dtype=np.float64).reshape(-1, 3)
        tri = np.asarray(m["indices"], dtype=np.int64).reshape(-1, 3)
        parts.append(pv.PolyData(pts, np.c_[np.full(len(tri), 3), tri].ravel()))
    return pv.merge(parts) if parts else pv.PolyData()


def points_cloud(points: Any, values: Any) -> pv.PolyData:
    """Sensor points `[[x, y, z], ...]` with one value each."""
    cloud = pv.PolyData(np.asarray(points, dtype=np.float64))
    cloud.point_data["value"] = np.asarray(values, dtype=np.float32)
    return cloud


def grid_surface(values: np.ndarray, z: np.ndarray | float = 0.0, cell: float = 1.0) -> pv.StructuredGrid:
    """A ground grid (row 0 = south) as a 3D surface, optional height per cell."""
    rows, cols = values.shape
    x, y = np.meshgrid((np.arange(cols) + 0.5) * cell, (np.arange(rows) + 0.5) * cell)
    zz = np.broadcast_to(np.asarray(z, dtype=np.float64), values.shape) + 0.05
    surf = pv.StructuredGrid(x, y, np.array(zz))
    surf.point_data["value"] = values.ravel(order="F").astype(np.float32)
    return surf


def plotter(size: tuple[int, int] = (1400, 860)) -> pv.Plotter:
    """An off-screen plotter with soft three-point light and anti-aliasing."""
    pl = pv.Plotter(off_screen=True, window_size=list(size), lighting="none")
    pl.set_background(BACKGROUND)
    # Key light from the south-west, a soft fill and a cool sky light.
    pl.add_light(pv.Light(position=(-1.0, -1.4, 1.6), light_type="scene light", intensity=0.75))
    pl.add_light(pv.Light(position=(1.2, 0.6, 0.8), light_type="scene light", intensity=0.30))
    pl.add_light(pv.Light(position=(0, 0, 1), light_type="scene light", intensity=0.35, color="#eaf0ff"))
    pl.enable_anti_aliasing("ssaa")
    return pl


def add_ground(pl: pv.Plotter, bounds: Any, pad: float = 60.0, z: float = -0.05) -> None:
    """A flat ground plane a little larger than `bounds`."""
    x0, x1, y0, y1 = bounds[:4]
    plane = pv.Plane(
        center=((x0 + x1) / 2, (y0 + y1) / 2, z), i_size=x1 - x0 + 2 * pad, j_size=y1 - y0 + 2 * pad
    )
    pl.add_mesh(plane, color=GROUND, ambient=0.35, diffuse=0.6, specular=0.0)


def add_meshes(pl: pv.Plotter, meshes: Any, color: str = CONTEXT, opacity: float = 1.0, **kw: Any) -> None:
    """Context (buildings, terrain, occluders) in a quiet grey."""
    mesh = meshes if isinstance(meshes, pv.DataSet) else mesh_from_dicts(meshes)
    if mesh.n_points:
        pl.add_mesh(mesh, color=color, opacity=opacity, ambient=0.5, diffuse=0.55, specular=0.0, **kw)


def add_values(pl: pv.Plotter, mesh: pv.DataSet, *, cmap: str, clim: tuple, point_size: float = 0) -> None:
    """The result, coloured by its `value` array. No colour bar here: `show`
    draws a sharper one with matplotlib."""
    style = dict(render_points_as_spheres=True, point_size=point_size) if point_size else {}
    # High ambient light keeps the colours true to the colour bar; a little
    # diffuse light still shows the shape of the buildings.
    look = dict(ambient=0.72, diffuse=0.32, specular=0.0, show_scalar_bar=False)
    pl.add_mesh(mesh, scalars="value", cmap=cmap, clim=clim, **look, **style)


def finish(pl: pv.Plotter, path: str | Path, *, azimuth=-35.0, elevation=35.0, zoom=1.15, focus=None) -> Path:
    """Set the camera and write the raw PNG. `azimuth` is in degrees from
    the south (the viewer stands south of the site at 0, east at 90);
    `elevation` is the angle above the horizon; `focus` an (x, y, z) point."""
    pl.camera_position = "xy"
    pl.reset_camera()
    if focus is not None:
        pl.set_focus(focus)
    cam = pl.camera
    cam.up = (0, 0, 1)
    distance = cam.distance
    center = np.asarray(cam.focal_point)
    az, el = np.radians(azimuth), np.radians(elevation)
    direction = np.array([np.sin(az) * np.cos(el), -np.cos(az) * np.cos(el), np.sin(el)])
    cam.position = tuple(center + direction * distance)
    cam.focal_point = tuple(center)
    pl.reset_camera_clipping_range()
    cam.zoom(zoom)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(path))
    pl.close()
    return path


def show(pl: pv.Plotter, path: str | Path, *, cmap: str, clim: tuple, label: str, title: str, **camera):
    """Render, then frame the image with a title and a colour bar (matplotlib).

    Returns the matplotlib figure: a notebook shows it, and it is saved
    next to the raw render as `<name>_framed.png`.
    """
    import matplotlib.image
    from matplotlib import cm, colors
    from matplotlib.figure import Figure  # not pyplot: the notebook shows it once

    raw = finish(pl, path, **camera)
    img = matplotlib.image.imread(raw)
    h, w = img.shape[:2]
    fig = Figure(figsize=(10, 10 * h / w * 0.9 / 0.93), dpi=110, facecolor=BACKGROUND)
    ax = fig.add_axes((0.0, 0.0, 0.9, 0.93))
    ax.imshow(img)
    ax.axis("off")
    cax = fig.add_axes((0.915, 0.18, 0.016, 0.6))
    bar = fig.colorbar(cm.ScalarMappable(colors.Normalize(*clim), cmap), cax=cax)
    bar.set_label(label, color=TEXT)
    bar.outline.set_visible(False)
    fig.text(0.015, 0.965, title, fontsize=13, color=TEXT, va="center")
    fig.savefig(Path(path).with_name(Path(path).stem + "_framed.png"), facecolor=BACKGROUND)
    return fig


def export_html(path: str | Path, values: pv.PolyData, context=None, *, cmap="Inferno", label="", clim=None):
    """Write one interactive HTML file (plotly; plotly.js loads from a CDN).

    `values` comes from `cells_mesh`; `context` is grey geometry. The file
    is large (about 35 bytes per triangle): keep it out of git.
    """
    import plotly.graph_objects as go

    def mesh3d(mesh: pv.PolyData, **kw: Any) -> Any:
        tri = mesh.triangulate().clean()  # merge shared corners: a smaller file
        p, f = tri.points.astype(np.float32), tri.faces.reshape(-1, 4)[:, 1:].astype(np.int32)
        if "intensity" in kw:
            kw["intensity"] = tri.cell_data["value"].astype(np.float32)
        xyz = dict(x=p[:, 0], y=p[:, 1], z=p[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2])
        return go.Mesh3d(**xyz, flatshading=True, **kw)

    lo, hi = clim or (float(np.nanmin(values["value"])), float(np.nanmax(values["value"])))
    traces = [
        mesh3d(
            values,
            intensity=True,
            intensitymode="cell",
            colorscale=cmap,
            cmin=lo,
            cmax=hi,
            colorbar=dict(title=label),
        )
    ]
    if context is not None:
        ctx = context if isinstance(context, pv.DataSet) else mesh_from_dicts(context)
        traces.append(mesh3d(ctx, color=CONTEXT, hoverinfo="skip"))
    fig = go.Figure(traces)
    hide = dict(xaxis_visible=False, yaxis_visible=False, zaxis_visible=False)
    fig.update_layout(
        scene=dict(aspectmode="data", **hide), margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=BACKGROUND
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs="cdn")
    return Path(path)
