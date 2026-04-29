"""Educational walkthrough of the tiling internals.

The Infrared API simulates a fixed 512x512 m tile at a time. For polygons
larger than one tile, the SDK auto-tiles, runs each tile in parallel, and
stitches the results into a single merged grid. This demo:

  1. previews tile cost with ``preview_area``
  2. runs a wind analysis over a multi-tile polygon
  3. overlays the per-tile boundaries on the merged grid so you can see
     where one tile ends and the next begins

Wind tiling uses 50% overlap — adjacent tile centres are 256 m apart, and the
SDK keeps the inner 256x256 cells of each tile. Solar/thermal tiling is
edge-to-edge with a 666 m context window. See README §How tiling works.

Usage::

    uv run python demos/demo_tiling.py

Requires INFRARED_API_KEY in environment or a .env file in the repo root.
"""

from __future__ import annotations

import logging
import os

import plotly.graph_objects as go
from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName, WindModelRequest

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("demo_tiling")

# Polygon spanning ~2x2 tiles (~1 km on each side at this latitude)
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [11.560, 48.190],
            [11.580, 48.190],
            [11.580, 48.205],
            [11.560, 48.205],
            [11.560, 48.190],
        ]
    ],
}

# Wind tile geometry (see README §How tiling works)
WIND_STEP_CELLS = 256

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "outputs", "tiling_walkthrough.html"
)


def main() -> None:
    with InfraredClient(logger=logger) as client:
        # 1. Preview tile cost before running anything ------------------------
        preview = client.preview_area(POLYGON)
        logger.info(
            "Preview: %d tiles, ~%.0fs estimated, ~%d tokens",
            preview.tile_count,
            preview.estimated_time_s,
            preview.estimated_cost_tokens,
        )

        # 2. Fetch buildings and run a wind analysis --------------------------
        logger.info("Fetching buildings...")
        area = client.buildings.get_area(POLYGON)
        logger.info("Found %d buildings", area.total_buildings)

        logger.info("Running wind analysis across all tiles...")
        result = client.run_area_and_wait(
            WindModelRequest(
                analysis_type=AnalysesName.wind_speed,
                wind_speed=8,
                wind_direction=180,
            ),
            POLYGON,
            buildings=area.buildings,
        )
        logger.info(
            "Merged grid=%s, %d/%d jobs OK",
            result.grid_shape,
            result.succeeded_jobs,
            result.total_jobs,
        )

    # 3. Plot the merged grid and overlay tile boundaries ---------------------
    rows, cols = result.grid_shape
    fig = go.Figure(
        go.Heatmap(
            z=result.merged_grid,
            colorscale="Turbo",
            zmin=result.min_legend,
            zmax=result.max_legend,
            colorbar=dict(title="m/s"),
        )
    )

    # Wind: each tile contributes its centre 256x256 cells to the merged grid,
    # so tile boundaries fall on multiples of WIND_STEP_CELLS.
    tile_lines_x = list(range(WIND_STEP_CELLS, cols, WIND_STEP_CELLS))
    tile_lines_y = list(range(WIND_STEP_CELLS, rows, WIND_STEP_CELLS))
    for x in tile_lines_x:
        fig.add_vline(x=x - 0.5, line=dict(color="white", width=1, dash="dot"))
    for y in tile_lines_y:
        fig.add_hline(y=y - 0.5, line=dict(color="white", width=1, dash="dot"))

    fig.update_layout(
        title=(
            f"Wind speed | {preview.tile_count} tiles | merged grid {rows}x{cols} "
            f"(dotted lines = tile boundaries)"
        ),
        width=1000,
        height=900,
        template="plotly_white",
        yaxis=dict(scaleanchor="x", scaleratio=1),
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.write_html(OUTPUT_PATH, include_plotlyjs=True)
    logger.info("Saved: %s", os.path.abspath(OUTPUT_PATH))


if __name__ == "__main__":
    main()
