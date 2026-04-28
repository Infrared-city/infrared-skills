"""Quickstart: run a wind-speed analysis over a polygon and plot the result.

Follows the README Quick Start pattern exactly:
  1. Define a GeoJSON polygon
  2. Fetch buildings for the area
  3. Run analysis with run_area_and_wait
  4. Plot the merged result grid

Usage::

    python wind_analysis.py
    python wind_analysis.py --speed 20 --direction 90
"""

from __future__ import annotations

import argparse
import logging
import os

import plotly.graph_objects as go
from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName, WindModelRequest

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logger = logging.getLogger("demo_wind")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--speed", type=int, default=15, help="Wind speed in m/s (1-100)")
parser.add_argument("--direction", type=int, default=180, help="Wind direction in degrees (0-360)")
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Polygon (small area in Munich, same as README)
# ---------------------------------------------------------------------------

POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [11.570, 48.195], [11.580, 48.195],
        [11.580, 48.201], [11.570, 48.201],
        [11.570, 48.195],
    ]],
}

# ---------------------------------------------------------------------------
# Run analysis
# ---------------------------------------------------------------------------

with InfraredClient(logger=logger) as client:
    # 1. Fetch buildings for the area
    area = client.buildings.get_area(POLYGON)
    logger.info("Fetched %d buildings", area.total_buildings)

    # 2. Run wind analysis over the polygon
    result = client.run_area_and_wait(
        WindModelRequest(
            analysis_type=AnalysesName.wind_speed,
            wind_speed=args.speed,
            wind_direction=args.direction,
        ),
        POLYGON,
        buildings=area.buildings,
    )

    logger.info("Grid shape: %s, %d/%d jobs succeeded", result.grid_shape, result.succeeded_jobs, result.total_jobs)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

fig = go.Figure(
    go.Heatmap(
        z=result.merged_grid,
        colorscale="Turbo",
        zmin=result.min_legend,
        zmax=result.max_legend,
        colorbar=dict(title="m/s"),
    )
)
fig.update_layout(
    title=f"Wind Speed | {args.speed} m/s @ {args.direction}deg | {result.grid_shape[0]}x{result.grid_shape[1]}",
    width=800, height=800, template="plotly_white",
    yaxis=dict(scaleanchor="x", scaleratio=1),
)

output_dir = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "wind_speed_result.html")
fig.write_html(output_path, include_plotlyjs=True)
logger.info("Saved: %s", os.path.abspath(output_path))
