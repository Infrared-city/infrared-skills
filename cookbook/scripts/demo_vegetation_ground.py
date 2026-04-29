"""Fetch-once-reuse pattern for vegetation and ground materials.

Layers (buildings, trees, ground materials) don't change when you sweep wind
direction or tweak weather windows, so fetch them once and reuse across runs to
avoid redundant API calls.

Usage::

    uv run python demos/demo_vegetation_ground.py

Requires INFRARED_API_KEY in environment or a .env file in the repo root.
"""

from __future__ import annotations

import logging
import os

import plotly.graph_objects as go
from dotenv import load_dotenv
from plotly.subplots import make_subplots

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName, WindModelRequest

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("demo_veg_ground")

POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [11.570, 48.195],
            [11.580, 48.195],
            [11.580, 48.201],
            [11.570, 48.201],
            [11.570, 48.195],
        ]
    ],
}

WIND_DIRECTIONS = [0, 90, 180, 270]
WIND_SPEED = 8

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "outputs", "wind_direction_sweep.html"
)


def main() -> None:
    with InfraredClient(logger=logger) as client:
        # Fetch all layers once -------------------------------------------------
        logger.info("Fetching layers (one-time)...")
        area = client.buildings.get_area(POLYGON)
        area_veg = client.vegetation.get_area(POLYGON)
        area_gm = client.ground_materials.get_area(POLYGON)
        logger.info(
            "Cached %d buildings, %d trees, %d ground material features",
            area.total_buildings,
            area_veg.total_trees,
            area_gm.total_features,
        )

        gm_for_run = area_gm.layers if area_gm.total_features <= 5000 else {}

        # Reuse the cached layers across N analysis runs ------------------------
        results = []
        for direction in WIND_DIRECTIONS:
            logger.info("Running wind sweep at %d°...", direction)
            payload = WindModelRequest(
                analysis_type=AnalysesName.wind_speed,
                wind_speed=WIND_SPEED,
                wind_direction=direction,
            )
            result = client.run_area_and_wait(
                payload,
                POLYGON,
                buildings=area.buildings,
                vegetation=area_veg.features,
                ground_materials=gm_for_run,
            )
            results.append((direction, result))
            logger.info(
                "  grid=%s, legend=[%.2f, %.2f] m/s",
                result.grid_shape,
                result.min_legend,
                result.max_legend,
            )

        logger.info(
            "Layers fetched 1x, reused across %d analysis runs",
            len(WIND_DIRECTIONS),
        )

    # Plot 2x2 panel of wind directions
    fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{d}°" for d, _ in results])
    zmin = min(r.min_legend for _, r in results)
    zmax = max(r.max_legend for _, r in results)
    for idx, (direction, r) in enumerate(results):
        row, col = idx // 2 + 1, idx % 2 + 1
        fig.add_trace(
            go.Heatmap(
                z=r.merged_grid,
                colorscale="Turbo",
                zmin=zmin,
                zmax=zmax,
                showscale=(idx == 0),
                colorbar=dict(title="m/s") if idx == 0 else None,
            ),
            row=row,
            col=col,
        )
    fig.update_layout(
        title=f"Wind speed at {WIND_SPEED} m/s — direction sweep",
        width=1200,
        height=1200,
        template="plotly_white",
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.write_html(OUTPUT_PATH, include_plotlyjs=True)
    logger.info("Saved: %s", os.path.abspath(OUTPUT_PATH))


if __name__ == "__main__":
    main()
