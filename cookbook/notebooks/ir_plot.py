"""Plot and cache helpers for the Infrared cookbook notebooks. Copy it into your app.

- Site: a square area polygon; lon/lat to the metre frame of a run (the SDK frame).
- Cache: keep results and public data on disk, so a second run costs nothing.
- Maps: a ground grid on a light basemap, with the correct extent, a legend with
  units and a scale bar. Row 0 of a ground grid is SOUTH: we draw it with
  ``origin="lower"``, so north is up.
"""

from __future__ import annotations

import gzip
import math
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from matplotlib.patheffects import withStroke

CACHE = Path(os.environ.get("IR_CACHE", Path.home() / ".cache" / "infrared-cookbook"))
BASEMAP = cx.providers.Esri.WorldGrayCanvas  # light, free, no key
EARTH_RADIUS_M = 6_371_000.0  # the sphere of the SDK's local frame

# One colour map and one legend label for each analysis.
STYLE: dict[str, tuple[str, str]] = {
    "sky-view-factors": ("viridis", "Sky view factor (%)"),
    "solar-radiation": ("inferno", "Solar radiation (kWh/m²)"),
    "direct-sun-hours": ("magma", "Direct sun hours (h)"),
    "daylight-availability": ("cividis", "Daylight availability (%)"),
    "thermal-comfort-index": ("RdYlBu_r", "UTCI (°C)"),
    "thermal-comfort-statistics": ("YlOrRd", "Share of hours (%)"),
    "wind-speed": ("YlGnBu", "Wind speed (m/s)"),
    "pedestrian-wind-comfort": ("RdYlGn_r", "Wind comfort class"),
}

try:  # JPEG figures keep a notebook with basemaps small
    __import__("matplotlib_inline.backend_inline").backend_inline.set_matplotlib_formats("jpeg")
except Exception:  # not in a notebook
    pass
plt.rcParams.update({"figure.dpi": 96, "font.size": 9, "axes.titlesize": 11,
                     "axes.titleweight": "bold", "figure.titleweight": "bold"})


def site(lon: float, lat: float, width_m: float, height_m: Optional[float] = None) -> dict:
    """A GeoJSON polygon of ``width_m`` x ``height_m`` metres around a centre."""
    k = EARTH_RADIUS_M * math.radians(1)  # metres per degree of latitude
    dlon, dlat = width_m / 2 / (k * math.cos(math.radians(lat))), (height_m or width_m) / 2 / k
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def to_local(lon: Any, lat: Any, polygon: dict) -> tuple[Any, Any]:
    """lon/lat to metres of the run frame: x east, y north, origin = SW corner of the bbox.

    This is the local projection of the SDK, so own meshes line up with the result grid.
    """
    ring = np.asarray(polygon["coordinates"][0], dtype=float)
    lon0, lat0 = ring[:, 0].min(), ring[:, 1].min()
    k = EARTH_RADIUS_M * math.radians(1)
    return (np.asarray(lon) - lon0) * k * math.cos(math.radians(lat0)), (np.asarray(lat) - lat0) * k


@dataclass
class Grid:
    """The part of an area result that a map needs. Row 0 is south."""

    values: np.ndarray                         # real values, NaN = no value
    bounds: tuple[float, float, float, float]  # west, south, east, north
    analysis_type: str
    legend: Optional[list[str]] = None         # class labels (wind comfort)

    @classmethod
    def of(cls, result: Any) -> "Grid":
        # physical_grid() gives real values whatever the wire type is.
        return cls(result.physical_grid(np.float32), tuple(result.bounds),
                   result.analysis_type, result.legend)

    def __sub__(self, other: "Grid") -> "Grid":
        # A difference map needs the same cells. Same polygon = same grid.
        assert self.values.shape == other.values.shape, "grids differ in shape"
        return Grid(self.values - other.values, self.bounds, "delta")

    def mean(self) -> float:
        return float(np.nanmean(self.values))


def cached(name: str, run: Callable[[], Any]) -> Any:
    """The grids of ``run()`` (one area result or a list), kept on disk.

    Only the real values are kept, so this works for every analysis.
    Delete the file to run again.
    """
    def make() -> Any:
        result = run()
        return [Grid.of(r) for r in result] if isinstance(result, list) else Grid.of(result)
    return cached_object(name, make)


def cached_object(name: str, make: Callable[[], Any]) -> Any:
    """Keep any Python object (public buildings, trees, weather, grids) on disk."""
    path = CACHE / f"{name}.pkl.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(pickle.dumps(make()), 1))
    return pickle.loads(gzip.decompress(path.read_bytes()))


def _merc(lon: float, lat: float) -> tuple[float, float]:
    """lon/lat to Web Mercator metres (the frame of the basemap tiles)."""
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return 6378137 * math.radians(lon), 6378137 * y


def _scale_bar(ax: Any, lat: float, metres: int = 100) -> None:
    """A plain scale bar in the lower right corner."""
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    length = metres / math.cos(math.radians(lat))  # Mercator stretch
    xe, ys = x1 - 0.04 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    ax.plot([xe - length, xe], [ys, ys], color="#222", lw=3, solid_capstyle="butt", zorder=5,
            path_effects=[withStroke(linewidth=5, foreground="white")])
    ax.text(xe - length / 2, ys + 0.015 * (y1 - y0), f"{metres} m", ha="center",
            va="bottom", fontsize=8, color="#222", zorder=5,
            path_effects=[withStroke(linewidth=2.5, foreground="white")])


def map_grid(grid: Grid, ax: Any = None, *, cmap: Optional[str] = None,
             vmin: Optional[float] = None, vmax: Optional[float] = None,
             label: Optional[str] = None, title: Optional[str] = None,
             polygon: Optional[dict] = None, colorbar: bool = True,
             alpha: float = 0.85, scale_m: int = 100) -> Any:
    """Draw one ground grid on a basemap. Returns the image (for a shared colour bar)."""
    if ax is None:
        _, ax = plt.subplots(figsize=(8.5, 7.2))
    style_cmap, style_label = STYLE.get(grid.analysis_type, ("RdBu_r", ""))
    w, s, e, n = grid.bounds
    (x0, y0), (x1, y1) = _merc(w, s), _merc(e, n)
    colour: dict[str, Any] = dict(cmap=cmap or style_cmap, vmin=vmin, vmax=vmax)
    if grid.legend:  # categorical: one colour for each class code 0..k-1
        k = len(grid.legend)
        colours = plt.get_cmap(cmap or style_cmap, k)(range(k))
        colour = dict(cmap=ListedColormap(colours), norm=BoundaryNorm(np.arange(-0.5, k), k))
    image = ax.imshow(np.ma.masked_invalid(grid.values), origin="lower", zorder=2,
                      extent=(x0, x1, y0, y1), alpha=alpha, interpolation="nearest", **colour)
    if grid.legend:
        handles = [Patch(color=c, label=t) for c, t in zip(colours, grid.legend)]
        ax.legend(handles=handles, title=label or style_label, loc="upper left",
                  fontsize=8, title_fontsize=8, framealpha=0.92)
    elif colorbar:
        plt.colorbar(image, ax=ax, shrink=0.75, pad=0.02, label=label or style_label)

    if polygon is not None:
        xy = [_merc(lon, lat) for lon, lat in polygon["coordinates"][0]]
        ax.plot(*zip(*xy), color="#333", lw=0.8, ls="--", zorder=3)
    # Zoom to the cells with a value: the grid of whole tiles can be larger.
    (ny, nx), (rows, cols) = grid.values.shape, np.nonzero(np.isfinite(grid.values))
    xa, xb = x0 + (x1 - x0) * cols.min() / nx, x0 + (x1 - x0) * (cols.max() + 1) / nx
    ya, yb = y0 + (y1 - y0) * rows.min() / ny, y0 + (y1 - y0) * (rows.max() + 1) / ny
    pad = 0.03 * max(xb - xa, yb - ya)
    ax.set(xlim=(xa - pad, xb + pad), ylim=(ya - pad, yb + pad))
    # About four basemap tiles across the view; the light tiles stop at zoom 16.
    zoom = int(min(16, math.log2(40_075_016 * 4 / (xb - xa))))  # Mercator tile width
    cx.add_basemap(ax, crs="EPSG:3857", source=BASEMAP, zoom=zoom, attribution_size=6, zorder=1)
    _scale_bar(ax, (s + n) / 2, scale_m)
    ax.set_axis_off()
    if title:
        ax.set_title(title)
    return image


def map_grids(grids: Sequence[Grid], titles: Sequence[str], *, ncols: Optional[int] = None,
              label: Optional[str] = None, suptitle: Optional[str] = None,
              panel: float = 4.2, **kw: Any) -> Any:
    """Small multiples with ONE shared colour scale and one colour bar."""
    ncols = ncols or len(grids)
    nrows = math.ceil(len(grids) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(panel * ncols + 1.2, panel * nrows),
                             squeeze=False, layout="constrained")
    image = None
    for ax, grid, title in zip(axes.flat, grids, titles):
        image = map_grid(grid, ax, title=title, colorbar=False, **kw)
    [ax.set_axis_off() for ax in list(axes.flat)[len(grids):]]  # empty panels
    if image is not None and not grids[0].legend:
        fig.colorbar(image, ax=axes, shrink=0.8, pad=0.01,
                     label=label or STYLE.get(grids[0].analysis_type, ("", ""))[1])
    if suptitle:
        fig.suptitle(suptitle)
    return fig


def symmetric_limit(grid: Grid, q: float = 99) -> float:
    """A colour limit for a difference map: the q-th percentile of |delta|."""
    finite = np.abs(grid.values[np.isfinite(grid.values)])
    return float(np.percentile(finite, q)) if finite.size else 1.0
