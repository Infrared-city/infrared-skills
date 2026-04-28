"""Demo: visualize the tiling orchestration pipeline with Plotly.

NOTE: This demo uses INTERNAL tiling modules (TileService, merger) directly
for educational purposes. These are not part of the public SDK API -- the
public interface is InfraredClient.run_area() / run_area_and_wait().
See demo_barcelona.py for the recommended high-level API usage.

Runs entirely offline using mock analysis results (synthetic gradient grids)
so no API key or network access is needed.

Usage:
    cd infrared-api-sdk
    python demos/demo_tiling.py
"""

import math
import logging
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- SDK imports --------------------------------------------------------------

from infrared_sdk.utilities.tiles import TileService, TILE_SIZE_M
from infrared_sdk.tiling.merger import (
    merge_tiles,
    clip_to_polygon,
    project_polygon_to_meters,
    merged_grid_shape,
    TILE_SIZE_CELLS,
)

# -----------------------------------------------------------------------------
# 1. Define a sample polygon (irregular quadrilateral in Munich area)
# -----------------------------------------------------------------------------
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [11.5700, 48.1370],
            [11.5780, 48.1370],
            [11.5800, 48.1420],
            [11.5730, 48.1430],
            [11.5690, 48.1400],
            [11.5700, 48.1370],  # closed ring
        ]
    ],
}


def make_synthetic_grid(row: int, col: int, seed: int) -> np.ndarray:
    """Generate a 512x512 synthetic grid that looks like a wind-speed field.

    Each tile gets a slightly different gradient + noise so you can see the
    blending effect in overlap regions.
    """
    rng = np.random.default_rng(seed + row * 1000 + col)
    # Base: radial gradient from center
    y = np.linspace(-1, 1, TILE_SIZE_CELLS)
    x = np.linspace(-1, 1, TILE_SIZE_CELLS)
    xx, yy = np.meshgrid(x, y)
    base = 5.0 + 3.0 * np.sqrt(xx**2 + yy**2)
    # Per-tile tilt so neighbours differ slightly
    tilt = 0.5 * (row - col)
    noise = rng.normal(0, 0.3, (TILE_SIZE_CELLS, TILE_SIZE_CELLS))
    return base + tilt + noise


# -----------------------------------------------------------------------------
# 2. Generate tiles
# -----------------------------------------------------------------------------

logger = logging.getLogger("demo")
logging.basicConfig(level=logging.INFO)

svc = TileService(polygon=POLYGON, logger=logger, max_tiles_override=200)
tile_grid = svc.generate_tiles_for_polygon()

num_rows = len(tile_grid)
num_cols = len(tile_grid[0]) if tile_grid else 0

non_empty = []
for r, row in enumerate(tile_grid):
    for c, tile in enumerate(row):
        if not tile.empty:
            non_empty.append((r, c, tile))

print(f"Grid: {num_rows} rows x {num_cols} cols, {len(non_empty)} non-empty tiles")

# -----------------------------------------------------------------------------
# 3. Merge synthetic tiles with bilinear blending
# -----------------------------------------------------------------------------
tile_grids = []
for r, c, tile in non_empty:
    grid = make_synthetic_grid(r, c, seed=42)
    tile_grids.append((r, c, grid))

merged = merge_tiles(tile_grids, num_rows, num_cols)

# Clip to polygon
polygon_meters, origin_lon, origin_lat = project_polygon_to_meters(POLYGON)
clipped = clip_to_polygon(merged.copy(), polygon_meters)

# -----------------------------------------------------------------------------
# 4. Visualize with Plotly
# -----------------------------------------------------------------------------
fig = make_subplots(
    rows=2,
    cols=2,
    subplot_titles=[
        "1. Tile Grid Layout",
        "2. Raw Merged Grid (before clipping)",
        "3. Merged + Polygon Clip",
        "4. Tile Overlap Heatmap (# contributors)",
    ],
    horizontal_spacing=0.08,
    vertical_spacing=0.12,
)

# --- Panel 1: Tile layout (scatter of tile bboxes on a map-like view) --------
for r, c, tile in non_empty:
    lat = tile.centroid.latitude
    lon = tile.centroid.longitude
    # Half-tile extents in degrees
    m_per_deg_lng = 111320.0 * math.cos(math.radians(lat))
    hlat = (TILE_SIZE_M / 2) / 111320.0
    hlon = (TILE_SIZE_M / 2) / m_per_deg_lng

    # Rectangle corners (closed)
    lons = [lon - hlon, lon + hlon, lon + hlon, lon - hlon, lon - hlon]
    lats = [lat - hlat, lat - hlat, lat + hlat, lat + hlat, lat - hlat]

    fig.add_trace(
        go.Scatter(
            x=lons,
            y=lats,
            mode="lines",
            line=dict(color="royalblue", width=1.5),
            fill="toself",
            fillcolor="rgba(65,105,225,0.15)",
            name=f"Tile ({r},{c})",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

# Add polygon outline
ring = POLYGON["coordinates"][0]
fig.add_trace(
    go.Scatter(
        x=[p[0] for p in ring],
        y=[p[1] for p in ring],
        mode="lines",
        line=dict(color="red", width=2.5),
        name="Polygon",
    ),
    row=1,
    col=1,
)

fig.update_xaxes(title_text="Longitude", row=1, col=1)
fig.update_yaxes(title_text="Latitude", scaleanchor="x", row=1, col=1)

# --- Panel 2: Raw merged grid (no clipping) ----------------------------------
fig.add_trace(
    go.Heatmap(
        z=merged,
        colorscale="Viridis",
        colorbar=dict(x=0.45, len=0.4, y=0.82, title="m/s"),
    ),
    row=1,
    col=2,
)
fig.update_xaxes(title_text="Col (cells)", row=1, col=2)
fig.update_yaxes(title_text="Row (cells)", row=1, col=2)

# --- Panel 3: Clipped to polygon ---------------------------------------------
# Replace NaN with None for Plotly (it handles None as gaps)
clipped_display = np.where(np.isnan(clipped), None, clipped)
fig.add_trace(
    go.Heatmap(
        z=clipped_display.tolist(),
        colorscale="Viridis",
        colorbar=dict(x=1.0, len=0.4, y=0.82, title="m/s"),
    ),
    row=2,
    col=1,
)
fig.update_xaxes(title_text="Col (cells)", row=2, col=1)
fig.update_yaxes(title_text="Row (cells)", row=2, col=1)

# --- Panel 4: Overlap contributor count (how many tiles per cell) -------------
height, width = merged_grid_shape(num_rows, num_cols)
contrib = np.zeros((height, width), dtype=np.int32)
for r, c, grid in tile_grids:
    start_r = r * 256
    start_c = c * 256
    contrib[start_r : start_r + 512, start_c : start_c + 512] += 1

fig.add_trace(
    go.Heatmap(
        z=contrib,
        colorscale="YlOrRd",
        colorbar=dict(x=1.0, len=0.4, y=0.18, title="# tiles"),
    ),
    row=2,
    col=2,
)
fig.update_xaxes(title_text="Col (cells)", row=2, col=2)
fig.update_yaxes(title_text="Row (cells)", row=2, col=2)

# --- Layout -------------------------------------------------------------------
fig.update_layout(
    title_text="Infrared SDK - Tiling Orchestration Demo",
    title_font_size=20,
    height=900,
    width=1200,
    template="plotly_white",
)

fig.show()
print("\nDone! The Plotly figure should have opened in your browser.")
