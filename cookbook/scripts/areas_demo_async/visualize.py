"""Plotly heatmap visualization generator for area analysis results.

Takes merged AreaResult objects and produces a self-contained HTML file
with a 5-panel heatmap: building footprints, wind speed, sky view factor,
UTCI thermal index, and thermal comfort statistics.

Usage::

    from visualize import generate_visualization

    generate_visualization("barcelona", results, "outputs")
"""

from __future__ import annotations

import logging
import os
from typing import Dict

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from infrared_sdk.tiling.types import AreaResult

from db import EXPECTED_ANALYSIS_TYPES, FRIENDLY_NAMES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colorscale + unit mapping keyed by SDK analysis-type string
# ---------------------------------------------------------------------------

_COLORSCALES: dict[str, str] = {
    "wind-speed": "Turbo",
    "sky-view-factors": "Viridis",
    "thermal-comfort-index": "RdYlBu_r",
    "thermal-comfort-statistics": "RdYlBu_r",
}

_UNITS: dict[str, str] = {
    "wind-speed": "m/s",
    "sky-view-factors": "SVF",
    "thermal-comfort-index": "\u00b0C",
    "thermal-comfort-statistics": "TCS",
}


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
    """Derive a binary building-footprint grid from wind results.

    Non-NaN cells are marked 1 (building), NaN cells stay NaN so they
    appear as gaps in the heatmap.
    """
    footprints = np.full_like(grid, np.nan, dtype=float)
    footprints[~np.isnan(grid)] = 1.0
    return footprints


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_visualization(
    area_name: str,
    results: Dict[str, AreaResult],
    output_dir: str,
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

    Returns
    -------
    str
        Absolute path to the written HTML file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Order panels consistently: building footprints first, then the four
    # analysis types in EXPECTED_ANALYSIS_TYPES order.
    panels: list[tuple[str, np.ndarray, object, str | None]] = []

    # --- Building footprints (prefer wind result for stable selection) ---
    first_result = results.get("wind-speed") or next(iter(results.values()), None)
    if first_result is not None:
        panels.append(
            (
                "Building Footprints",
                first_result.merged_grid,
                [[0, "rgb(40,40,40)"], [1, "rgb(220,220,220)"]],
                None,  # no colorbar unit for footprints
            )
        )

    # --- One panel per analysis type (in canonical order) ---
    for analysis_type in EXPECTED_ANALYSIS_TYPES:
        result = results.get(analysis_type)
        friendly = FRIENDLY_NAMES.get(analysis_type, analysis_type)
        colorscale = _COLORSCALES.get(analysis_type, "Viridis")
        unit = _UNITS.get(analysis_type, "")

        if result is None:
            # Analysis not present at all -- skip panel
            continue

        title = f"{friendly.upper()} ({analysis_type})"
        panels.append((title, result.merged_grid, colorscale, unit))

    if not panels:
        logger.warning("No results to visualise for area %s", area_name)
        return ""

    # --- Layout ---
    n_panels = len(panels)
    n_cols = 2
    n_rows = (n_panels + n_cols - 1) // n_cols

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=[f"{i + 1}. {p[0]}" for i, p in enumerate(panels)],
        horizontal_spacing=0.08,
        vertical_spacing=0.06,
    )

    # --- Traces ---
    for idx, (title, grid, colorscale, unit) in enumerate(panels):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        # For building footprints use the binary mask; for analyses use
        # the raw grid.  Both go through _to_display to replace NaN->None.
        if unit is None:
            z = _to_display(_building_footprints(grid))
        else:
            z = _to_display(grid)

        show_scale = unit is not None
        colorbar = dict(title=unit, len=1.0 / n_rows * 0.8) if show_scale else None

        fig.add_trace(
            go.Heatmap(
                z=z,
                colorscale=colorscale,
                showscale=show_scale,
                colorbar=colorbar,
            ),
            row=row,
            col=col,
        )

    # --- Title ---
    title_parts = [area_name]

    if first_result is not None:
        grid_shape = first_result.grid_shape
        title_parts.append(f"{grid_shape[0]}x{grid_shape[1]} cells")

    # Aggregate job counts across all results
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

    fig.update_layout(
        title_text="  |  ".join(title_parts),
        title_font_size=15,
        height=n_rows * 450,
        width=1200,
        template="plotly_white",
    )

    # --- Write HTML ---
    output_path = os.path.join(output_dir, f"{area_name}_outputs.html")
    fig.write_html(output_path, include_plotlyjs=True)

    logger.info("Saved visualization to %s", output_path)
    return os.path.abspath(output_path)
