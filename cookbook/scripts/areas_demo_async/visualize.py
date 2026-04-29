"""Plotly visualization generator for area analysis results.

Produces a self-contained HTML file per area with the following panels:

    1. Building Footprints   (from any available merged grid)
    2. Ground Materials + Trees  (GeoJSON polygons + tree markers in lon/lat,
                                  clipped to the area polygon so the panel
                                  outline matches the analysis heatmaps)
    3..N One heatmap panel per analysis type in ``EXPECTED_ANALYSIS_TYPES``
         order (e.g. wind-speed, thermal-comfort-index-morning,
         thermal-comfort-index) — each with its own colorbar anchored to
         the subplot via paper-coordinate positioning.

Usage::

    from visualize import generate_visualization

    generate_visualization("barcelona", results, "outputs")
    generate_visualization(
        "barcelona",
        results,
        "outputs",
        ground_materials=gm,
        vegetation=veg,
    )
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from infrared_sdk.tiling.types import AreaResult

from db import EXPECTED_ANALYSIS_TYPES, FRIENDLY_NAMES

if TYPE_CHECKING:
    from infrared_sdk.layers.ground_materials import AreaGroundMaterials
    from infrared_sdk.layers.vegetation import AreaVegetation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colorscale + unit mapping keyed by SDK analysis-type string
# ---------------------------------------------------------------------------

_COLORSCALES: dict[str, str] = {
    "wind-speed": "Turbo",
    "thermal-comfort-index": "RdYlBu_r",
}

_UNITS: dict[str, str] = {
    "wind-speed": "m/s",
    "thermal-comfort-index": "°C",
}

_GROUND_MATERIAL_FILL = {
    "vegetation": "rgba(76, 175, 80, 0.45)",
    "water": "rgba(33, 150, 243, 0.55)",
    "asphalt": "rgba(97, 97, 97, 0.45)",
    "concrete": "rgba(189, 189, 189, 0.45)",
    "soil": "rgba(141, 110, 99, 0.45)",
    "building": "rgba(255, 152, 0, 0.45)",
}

_GROUND_MATERIAL_LINE = {
    "vegetation": "rgb(56, 142, 60)",
    "water": "rgb(21, 101, 192)",
    "asphalt": "rgb(66, 66, 66)",
    "concrete": "rgb(117, 117, 117)",
    "soil": "rgb(93, 64, 55)",
    "building": "rgb(230, 126, 34)",
}

_TREE_FILL = "rgb(46, 125, 50)"  # bright green triangle fill
_TREE_OUTLINE = "rgb(13, 50, 20)"  # dark outline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_display(grid: np.ndarray) -> list:
    """Convert a numpy grid to a nested list with NaN replaced by None.

    Plotly treats ``None`` as a gap in heatmaps, which is the desired
    behaviour for missing / outside-polygon cells.
    """
    result = grid.copy().astype(object)
    result[np.isnan(grid)] = None
    return result.tolist()


def _building_footprints(grid: np.ndarray) -> np.ndarray:
    """Derive a binary building-footprint grid from an analysis result.

    Non-NaN cells are marked 1 (building), NaN cells stay NaN so they
    appear as gaps in the heatmap.
    """
    footprints = np.full_like(grid, np.nan, dtype=float)
    footprints[~np.isnan(grid)] = 1.0
    return footprints


def _area_shape(area_polygon: dict):
    """Build a shapely Polygon/MultiPolygon from a GeoJSON polygon dict.

    Returns ``None`` if the polygon is empty or shapely is unavailable.
    Used for clipping the geo panel so it visually matches the
    diagonal Gràcia outline shown by the analysis heatmap panels
    instead of a surrounding bbox rectangle.
    """
    try:
        from shapely.geometry import Polygon, MultiPolygon
    except ImportError:
        return None

    if not area_polygon:
        return None
    coords = area_polygon.get("coordinates") or []
    ptype = area_polygon.get("type")
    if ptype == "Polygon" and coords:
        outer = coords[0]
        holes = coords[1:] if len(coords) > 1 else []
        if len(outer) < 3:
            return None
        return Polygon(outer, holes)
    if ptype == "MultiPolygon" and coords:
        polys = [
            Polygon(p[0], p[1:] if len(p) > 1 else [])
            for p in coords
            if p and len(p[0]) >= 3
        ]
        return MultiPolygon(polys) if polys else None
    return None


def _iter_polygon_rings(shapely_geom):
    """Yield ``(outer_ring_coords, [hole_ring_coords])`` tuples for a shapely geom.

    Handles ``Polygon`` / ``MultiPolygon`` outputs of an ``intersection``
    call. Silently skips non-area geometry types (``Point``, ``LineString``,
    ``GeometryCollection`` residuals) — they contribute no area to a
    ground-cover overlay.
    """
    gtype = getattr(shapely_geom, "geom_type", None)
    if gtype == "Polygon":
        if shapely_geom.is_empty:
            return
        outer = list(shapely_geom.exterior.coords)
        holes = [list(r.coords) for r in shapely_geom.interiors]
        yield outer, holes
    elif gtype == "MultiPolygon":
        for poly in shapely_geom.geoms:
            yield from _iter_polygon_rings(poly)
    elif gtype == "GeometryCollection":
        for sub in shapely_geom.geoms:
            yield from _iter_polygon_rings(sub)


def _add_ground_material_traces(
    fig: go.Figure,
    ground_materials: "AreaGroundMaterials",
    row: int,
    col: int,
    clip_shape=None,
) -> None:
    """Add filled-polygon Scatter traces for each ground-material layer.

    When *clip_shape* is provided (a shapely Polygon/MultiPolygon of the
    source area polygon), every feature is clipped to it. Features and
    feature-parts outside the area are dropped, so the panel's visual
    outline matches the analysis heatmap panels.
    """
    from shapely.geometry import shape as shapely_shape

    for layer_name, fc in ground_materials.layers.items():
        if not isinstance(fc, dict):
            continue

        features = fc.get("features", [])
        fill_color = _GROUND_MATERIAL_FILL.get(layer_name, "rgba(200,200,200,0.4)")
        line_color = _GROUND_MATERIAL_LINE.get(layer_name, "rgb(100,100,100)")

        first_in_layer = True
        for feat in features:
            geom = feat.get("geometry") or {}
            geom_type = geom.get("type", "")

            # Collect outer rings for the drawable surface area of this
            # feature, clipped to the area polygon when possible.
            rings: list[list] = []

            if clip_shape is not None and geom_type in ("Polygon", "MultiPolygon"):
                try:
                    clipped = shapely_shape(geom).intersection(clip_shape)
                except Exception:
                    clipped = None
                if clipped is None or clipped.is_empty:
                    continue
                for outer, _holes in _iter_polygon_rings(clipped):
                    rings.append(outer)
            else:
                if geom_type == "Polygon":
                    coords = geom.get("coordinates") or [[]]
                    if coords:
                        rings = [coords[0]]
                elif geom_type == "MultiPolygon":
                    rings = [
                        poly[0] for poly in (geom.get("coordinates") or []) if poly
                    ]

            for ring in rings:
                if len(ring) < 3:
                    continue
                lons = [pt[0] for pt in ring]
                lats = [pt[1] for pt in ring]
                fig.add_trace(
                    go.Scatter(
                        x=lons,
                        y=lats,
                        mode="lines",
                        fill="toself",
                        fillcolor=fill_color,
                        line=dict(color=line_color, width=1),
                        name=layer_name,
                        legendgroup=layer_name,
                        showlegend=first_in_layer,
                        hoverinfo="name",
                    ),
                    row=row,
                    col=col,
                )
                first_in_layer = False


def _add_vegetation_markers(
    fig: go.Figure,
    vegetation: "AreaVegetation",
    row: int,
    col: int,
    clip_shape=None,
) -> None:
    """Add dark-green triangle markers for each tree in *vegetation*.

    Trees are GeoJSON Point features with ``geometry.coordinates =
    [lon, lat]``. When *clip_shape* is supplied, markers outside the
    area polygon are dropped so the panel matches the Gràcia outline.
    """
    lons: list[float] = []
    lats: list[float] = []

    if clip_shape is not None:
        from shapely.geometry import Point

    for feature in vegetation.features.values():
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        if clip_shape is not None and not clip_shape.covers(Point(lon, lat)):
            continue
        lons.append(lon)
        lats.append(lat)

    if not lons:
        return

    fig.add_trace(
        go.Scatter(
            x=lons,
            y=lats,
            mode="markers",
            marker=dict(
                symbol="triangle-up",
                size=9,
                color=_TREE_FILL,
                opacity=0.95,
                line=dict(width=1, color=_TREE_OUTLINE),
            ),
            name=f"Trees ({len(lons)})",
            legendgroup="vegetation-trees",
            hoverinfo="name",
            showlegend=True,
        ),
        row=row,
        col=col,
    )


def _add_area_outline(
    fig: go.Figure,
    area_polygon: dict,
    row: int,
    col: int,
) -> None:
    """Draw the source area polygon outline on top of the geo panel.

    A thin red line plus legend entry so the viewer can see the clip
    boundary against the filled ground-material surfaces.
    """
    if not area_polygon:
        return
    coords = area_polygon.get("coordinates") or []
    rings: list[list] = []
    if area_polygon.get("type") == "Polygon":
        rings = [coords[0]] if coords else []
    elif area_polygon.get("type") == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly]

    first = True
    for ring in rings:
        if len(ring) < 3:
            continue
        fig.add_trace(
            go.Scatter(
                x=[pt[0] for pt in ring],
                y=[pt[1] for pt in ring],
                mode="lines",
                line=dict(color="rgba(200,30,30,0.8)", width=1.5),
                name="Area boundary",
                legendgroup="area-outline",
                showlegend=first,
                hoverinfo="name",
            ),
            row=row,
            col=col,
        )
        first = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_visualization(
    area_name: str,
    results: Dict[str, AreaResult],
    output_dir: str,
    ground_materials: Optional["AreaGroundMaterials"] = None,
    vegetation: Optional["AreaVegetation"] = None,
) -> str:
    """Generate a self-contained Plotly HTML visualization.

    Parameters
    ----------
    area_name:
        Human-readable area identifier (e.g. ``"barcelona"``).
    results:
        Dict keyed by SDK analysis-type string (e.g. ``"wind-speed"``)
        mapping to ``AreaResult`` objects.
    output_dir:
        Directory in which to write the HTML file.
    ground_materials:
        Optional ``AreaGroundMaterials`` rendered in the geo panel.
    vegetation:
        Optional ``AreaVegetation``; trees are plotted as dark-green
        triangle markers on top of the geo panel.

    Returns
    -------
    str
        Absolute path to the written HTML file, or ``""`` if nothing
        could be plotted.
    """
    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Decide which panels to draw, in order:
    #   1. Building footprints
    #   2. Ground materials + tree markers
    #   3+. One heatmap per analysis type (canonical order)
    # ------------------------------------------------------------------

    first_result = next(
        (results.get(t) for t in EXPECTED_ANALYSIS_TYPES if results.get(t) is not None),
        None,
    )
    if first_result is None:
        first_result = next(iter(results.values()), None)

    has_ground_materials = ground_materials is not None and bool(
        ground_materials.layers
    )
    has_vegetation = vegetation is not None and bool(vegetation.features)
    has_geo_panel = has_ground_materials or has_vegetation

    panel_titles: list[str] = []
    if first_result is not None:
        panel_titles.append("Building Footprints")
    if has_geo_panel:
        panel_titles.append("Ground Materials + Trees")

    analysis_panels: list[tuple[str, AreaResult]] = []
    for analysis_type in EXPECTED_ANALYSIS_TYPES:
        result = results.get(analysis_type)
        if result is None:
            continue
        friendly = FRIENDLY_NAMES.get(analysis_type, analysis_type)
        title = f"{friendly.upper()} ({analysis_type})"
        analysis_panels.append((title, result))
        panel_titles.append(title)

    if not panel_titles:
        logger.warning("No results to visualise for area %s", area_name)
        return ""

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    n_panels = len(panel_titles)
    n_cols = 2
    n_rows = (n_panels + n_cols - 1) // n_cols

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=[f"{i + 1}. {t}" for i, t in enumerate(panel_titles)],
        horizontal_spacing=0.08,
        vertical_spacing=0.06,
    )

    panel_idx = 0

    # --- Panel 1: Building footprints ---
    if first_result is not None:
        row = panel_idx // n_cols + 1
        col = panel_idx % n_cols + 1
        fig.add_trace(
            go.Heatmap(
                z=_to_display(_building_footprints(first_result.merged_grid)),
                colorscale=[[0, "rgb(40,40,40)"], [1, "rgb(220,220,220)"]],
                showscale=False,
            ),
            row=row,
            col=col,
        )
        panel_idx += 1

    # --- Panel 2: Ground materials + tree markers ---
    if has_geo_panel:
        row = panel_idx // n_cols + 1
        col = panel_idx % n_cols + 1

        # Source polygon for clipping + outline. Prefer GM's polygon
        # (same coordinate frame as its features); fall back to the
        # first analysis result's polygon (always present when we got
        # this far).
        area_polygon: Optional[dict] = None
        if has_ground_materials:
            area_polygon = ground_materials.polygon
        if area_polygon is None and first_result is not None:
            area_polygon = first_result.polygon
        clip_shape = _area_shape(area_polygon) if area_polygon else None

        if has_ground_materials:
            _add_ground_material_traces(
                fig, ground_materials, row, col, clip_shape=clip_shape
            )
        if has_vegetation:
            _add_vegetation_markers(fig, vegetation, row, col, clip_shape=clip_shape)
        if area_polygon is not None:
            _add_area_outline(fig, area_polygon, row, col)
        panel_idx += 1

    # --- Analysis heatmap panels ---
    for title, result in analysis_panels:
        row = panel_idx // n_cols + 1
        col = panel_idx % n_cols + 1

        analysis_type = result.analysis_type
        colorscale = _COLORSCALES.get(analysis_type, "Viridis")
        unit = _UNITS.get(analysis_type, "")

        # Anchor each colorbar to its own subplot so multiple heatmaps
        # don't end up stacked at Plotly's default x=1.02, y=0.5. Paper
        # coordinates: 0..1 left-to-right, 0..1 bottom-to-top.
        col_right = col / n_cols
        row_center = 1 - (row - 0.5) / n_rows
        colorbar = dict(
            title=unit,
            len=0.8 / n_rows,
            x=col_right + 0.02,
            y=row_center,
            xanchor="left",
            yanchor="middle",
            thickness=14,
        )

        heatmap_kwargs: dict = dict(
            z=_to_display(result.merged_grid),
            colorscale=colorscale,
            showscale=True,
            colorbar=colorbar,
        )
        if result.min_legend is not None:
            heatmap_kwargs["zmin"] = result.min_legend
        if result.max_legend is not None:
            heatmap_kwargs["zmax"] = result.max_legend

        fig.add_trace(
            go.Heatmap(**heatmap_kwargs),
            row=row,
            col=col,
        )
        panel_idx += 1

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------

    title_parts = [area_name]

    if first_result is not None:
        grid_shape = first_result.grid_shape
        title_parts.append(f"{grid_shape[0]}x{grid_shape[1]} cells")

    total_jobs = sum(getattr(r, "total_jobs", 0) for r in results.values())
    succeeded = sum(getattr(r, "succeeded_jobs", 0) for r in results.values())
    failed_count = sum(len(getattr(r, "failed_jobs", [])) for r in results.values())

    title_parts.append(f"{total_jobs} jobs ({succeeded} ok, {failed_count} failed)")
    title_parts.append(
        " + ".join(
            FRIENDLY_NAMES.get(t, t).upper()
            for t in EXPECTED_ANALYSIS_TYPES
            if t in results
        )
    )

    if has_ground_materials:
        title_parts.append(
            f"{ground_materials.total_features} ground-material features "
            f"across {len(ground_materials.layers)} layers"
        )
    if has_vegetation:
        title_parts.append(f"{vegetation.total_trees} trees")

    fig.update_layout(
        title_text="  |  ".join(title_parts),
        title_font_size=15,
        height=n_rows * 450,
        width=1200,
        template="plotly_white",
    )

    # ------------------------------------------------------------------
    # Write HTML
    # ------------------------------------------------------------------

    output_path = os.path.join(output_dir, f"{area_name}_outputs.html")
    fig.write_html(output_path, include_plotlyjs=True)

    logger.info("Saved visualization to %s", output_path)
    return os.path.abspath(output_path)
