"""Rendering helpers for the advanced direct-API demo notebooks.

Two render styles, both designed to look good inline in a notebook:

* :func:`surface_mesh` -- the headline. Renders ``analysis-surfaces`` results
  as a **Lambert-shaded colored triangle mesh on the building geometry in 3D**
  (a real mesh, not a scatter cloud). Each kept cell is drawn from its exact
  clipped footprint (``cell-tris``, via ``ir_advanced.reconstruct_cells``),
  edges off, over a faint building context. Boundary cells are real polygons,
  not blocky squares.

* :func:`grid_heatmap` -- a clean 2D heatmap for the 512x512 grid models
  (UTCI, terrain-drape, flat solar) with a perceptual colormap and colorbar.

Both use a perceptual colormap by default and add a compact stats caption.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def surface_mesh(
    tris: np.ndarray,
    values: np.ndarray,
    *,
    normals: Optional[np.ndarray] = None,
    context_faces: Optional[Sequence] = None,
    title: str = "",
    cbar_label: str = "",
    cmap: str = "inferno",
    note: str = "",
    elev: float = 22,
    azim: float = -60,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    figsize=(12, 9),
    zmax: Optional[float] = None,
    context_alpha: float = 0.05,
):
    """Render a colored, Lambert-shaded surface-sensor mesh in 3D.

    Parameters
    ----------
    tris : (T, 3, 3) array
        World-space triangle vertices, one cell's clipped footprint expanded to
        triangles (from :func:`ir_advanced.reconstruct_cells`).
    values : (T,) array
        Per-triangle value (its cell's value) used for the fill color.
    normals : (T, 3) array, optional
        Per-triangle frame-plane normal, used for soft Lambert shading.
    context_faces : list of (3,3) arrays, optional
        Building triangles drawn as a faint translucent grey context so the
        colored sensors read against the massing without clutter.
    """
    tris = np.asarray(tris, float)
    values = np.asarray(values, float)
    if len(tris) == 0:
        raise ValueError("no triangles to render (empty surface result)")
    if vmin is None:
        vmin = float(np.percentile(values, 1))
    if vmax is None:
        vmax = float(np.percentile(values, 99))
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0

    cmap_obj = matplotlib.colormaps[cmap]
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    rgb = cmap_obj(norm(values))[:, :3]

    # Soft Lambert shading from the per-triangle plane normal -> a little depth
    # without washing the colormap out. Falls back to flat color if no normals.
    if normals is not None and len(normals) == len(tris):
        light = np.array([0.4, 0.5, 0.75])
        light /= np.linalg.norm(light)
        lam = np.abs(np.asarray(normals, float) @ light)
        shade = (0.6 + 0.4 * lam)[:, None]
        rgb = np.clip(rgb * shade, 0, 1)
    facecolors = np.concatenate([rgb, np.ones((len(tris), 1))], axis=1)

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection="3d")

    if context_faces is not None and len(context_faces):
        ctx = Poly3DCollection(
            list(context_faces),
            facecolor=(0.82, 0.82, 0.85, context_alpha),
            edgecolor="none",
            linewidths=0,
        )
        ax.add_collection3d(ctx)

    pc = Poly3DCollection(
        tris, facecolors=facecolors, edgecolors="none", linewidths=0, shade=False
    )
    ax.add_collection3d(pc)

    # axis extent from the colored sensors only (context may sprawl wider)
    allpts = tris.reshape(-1, 3)
    mn, mx = allpts.min(axis=0), allpts.max(axis=0)
    span = mx - mn
    span[span < 1e-6] = 1.0
    pad = 0.03
    ax.set_xlim(mn[0] - pad * span[0], mx[0] + pad * span[0])
    ax.set_ylim(mn[1] - pad * span[1], mx[1] + pad * span[1])
    zhi = zmax if zmax is not None else mx[2] + pad * span[2]
    ax.set_zlim(0, zhi)
    z_eff = max(span[2], 0.10 * max(span[0], span[1]))
    try:  # real-world aspect so buildings don't look squashed/stretched
        ax.set_box_aspect((span[0], span[1], z_eff))
    except Exception:  # noqa: BLE001 -- older matplotlib
        pass

    ax.view_init(elev=elev, azim=azim)
    ax.set_proj_type("persp")
    ax.set_axis_off()
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.02, aspect=22)
    cb.set_label(cbar_label)
    if title:
        ax.set_title(title, fontsize=14, weight="bold", pad=8)

    caption = (
        f"{len(values):,} cell-triangles  |  mean {np.nanmean(values):.2f}  "
        f"range [{np.nanmin(values):.2f}, {np.nanmax(values):.2f}]"
    )
    if note:
        caption += f"\n{note}"
    fig.text(0.5, 0.02, caption, ha="center", fontsize=7.5, color="#555")
    return fig, ax


def grid_heatmap(
    grid: np.ndarray,
    *,
    title: str = "",
    cbar_label: str = "",
    cmap: str = "viridis",
    diverging: bool = False,
    crop: bool = True,
    pad: int = 8,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    note: str = "",
    figsize=(8, 7),
):
    """Clean 2D heatmap of a 512x512 grid result (``null`` cells masked).

    ``crop`` trims to the finite bounding box so the AOI fills the frame.
    ``diverging`` centres a symmetric colormap at zero (for delta plots).
    """
    grid = np.asarray(grid, float)
    ox = oy = 0
    if crop:
        finite = np.isfinite(grid)
        if finite.any():
            rows = np.where(finite.any(axis=1))[0]
            cols = np.where(finite.any(axis=0))[0]
            r0, r1 = max(0, rows.min() - pad), min(grid.shape[0], rows.max() + pad + 1)
            c0, c1 = max(0, cols.min() - pad), min(grid.shape[1], cols.max() + pad + 1)
            grid = grid[r0:r1, c0:c1]
            ox, oy = c0, r0

    valid = grid[np.isfinite(grid)]
    if vmin is None:
        vmin = float(np.nanmin(grid)) if valid.size else 0.0
    if vmax is None:
        vmax = float(np.nanmax(grid)) if valid.size else 1.0
    if diverging:
        m = max(abs(vmin), abs(vmax))
        vmin, vmax = -m, m

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(
        grid,
        origin="lower",
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        extent=[ox, ox + grid.shape[1], oy, oy + grid.shape[0]],
    )
    if title:
        ax.set_title(title, fontsize=12, weight="bold")
    ax.set_xlabel("E-W (m, AOI bbox SW origin)")
    ax.set_ylabel("S-N (m)")
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label(cbar_label)

    caption = (
        (
            f"valid cells {int(valid.size):,}  |  mean {np.nanmean(grid):.2f}  "
            f"range [{np.nanmin(grid):.2f}, {np.nanmax(grid):.2f}]"
        )
        if valid.size
        else "no valid cells"
    )
    if note:
        caption += f"  |  {note}"
    ax.text(0.0, -0.13, caption, transform=ax.transAxes, fontsize=8, color="#444")
    fig.tight_layout()
    return fig, ax


def terrain_3d(
    heights: np.ndarray,
    *,
    size_m: float = 512.0,
    context_faces: Optional[Sequence] = None,
    target_faces: Optional[Sequence] = None,
    title: str = "",
    cbar_label: str = "elevation (m)",
    cmap: str = "terrain",
    note: str = "",
    elev: float = 28,
    azim: float = -60,
    figsize=(12, 9),
):
    """3D render of a synthesized terrain surface, optionally with buildings.

    ``heights`` is the (n, n) elevation grid from ``ir_terrain.generate_terrain``.
    Buildings sit on the relief. ``target_faces`` (if given) are drawn as solid
    blue massing and ``context_faces`` as light translucent grey occluders, so a
    busy urban scene stays readable instead of a single grey mass. The vertical
    axis is held to a real-world aspect so the buildings are not squashed.
    """
    n = heights.shape[0]
    xs = np.linspace(0.0, size_m, n)
    ys = np.linspace(0.0, size_m, n)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(
        gx,
        gy,
        heights,
        cmap=matplotlib.colormaps[cmap],
        linewidth=0,
        antialiased=True,
        alpha=0.95,
        rcount=n,
        ccount=n,
    )

    zmax = float(heights.max())

    def _add(faces, facecolor, alpha):
        if not faces:
            return
        coll = Poly3DCollection(
            list(faces),
            facecolor=facecolor,
            edgecolor="none",
            linewidths=0,
            alpha=alpha,
        )
        ax.add_collection3d(coll)
        nonlocal zmax
        zmax = max(
            zmax, float(np.concatenate([np.asarray(f) for f in faces])[:, 2].max())
        )

    # context first (behind), then the solid target on top
    _add(context_faces, "#c4c8cf", 0.22)
    _add(target_faces, "#2b6cb0", 0.92)

    ax.view_init(elev=elev, azim=azim)
    ax.set_proj_type("persp")
    ax.set_axis_off()
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, size_m)
    ax.set_ylim(0, size_m)
    ax.set_zlim(min(0.0, float(heights.min())), zmax * 1.05 + 1.0)
    try:  # real-world vertical aspect (a touch lifted so relief is legible)
        ax.set_box_aspect((size_m, size_m, max(zmax, 0.12 * size_m)))
    except Exception:  # noqa: BLE001
        pass

    if title:
        ax.set_title(title, fontsize=14, weight="bold", pad=8)
    cb = fig.colorbar(surf, ax=ax, shrink=0.55, pad=0.02, aspect=22)
    cb.set_label(cbar_label)
    caption = (
        f"terrain relief {heights.min():.1f} -> {heights.max():.1f} m "
        f"(synthesized, illustrative)"
    )
    if note:
        caption += f"\n{note}"
    fig.text(0.5, 0.02, caption, ha="center", fontsize=7.5, color="#555")
    return fig, ax


def footprints_2d(
    buildings: dict,
    *,
    target_ids: Optional[set] = None,
    title: str = "",
    note: str = "",
    figsize=(8, 8),
):
    """Plan-view of building footprints, optionally splitting target vs context.

    Buildings whose id is in ``target_ids`` are drawn solid blue; the rest
    (context) are drawn grey. Used by the context-occluder notebook to make
    the target/context split obvious before running.
    """
    fig, ax = plt.subplots(figsize=figsize)
    for bid, mesh in buildings.items():
        co = np.asarray(mesh["coordinates"], float).reshape(-1, 3)
        is_target = target_ids is None or bid in target_ids
        color = "#2b6cb0" if is_target else "#b0b0b0"
        # footprint outline = convex-ish hull via min/max is too coarse; instead
        # draw all base edges (z near min) as a light wireframe.
        zmin = co[:, 2].min()
        base = co[np.abs(co[:, 2] - zmin) < 0.5]
        if len(base) >= 2:
            order = np.argsort(
                np.arctan2(
                    base[:, 1] - base[:, 1].mean(), base[:, 0] - base[:, 0].mean()
                )
            )
            ring = base[order][:, :2]
            ring = np.vstack([ring, ring[:1]])
            segs = [[ring[i], ring[i + 1]] for i in range(len(ring) - 1)]
            ax.add_collection(LineCollection(segs, colors=color, linewidths=0.8))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_xlabel("E-W (m)")
    ax.set_ylabel("S-N (m)")
    if title:
        ax.set_title(title, fontsize=12, weight="bold")
    if note:
        ax.text(0.0, -0.1, note, transform=ax.transAxes, fontsize=8, color="#444")
    fig.tight_layout()
    return fig, ax
