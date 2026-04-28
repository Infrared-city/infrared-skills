"""End-to-end UTCI (Universal Thermal Climate Index) analysis.

Pulls buildings, vegetation, ground materials, and weather for a Munich polygon,
runs a UTCI analysis over a summer afternoon time window, and plots the result
as a Plotly heatmap.

Usage::

    uv run python demos/demo_utci_analysis.py

Requires INFRARED_API_KEY in environment or a .env file in the repo root.
"""

from __future__ import annotations

import logging
import os

import plotly.graph_objects as go
from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
)
from infrared_sdk.models import Location, TimePeriod

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logger = logging.getLogger("demo_utci")

POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [11.570, 48.195], [11.580, 48.195],
        [11.580, 48.201], [11.570, 48.201],
        [11.570, 48.195],
    ]],
}

LATITUDE = 48.1983
LONGITUDE = 11.575

TIME_PERIOD = TimePeriod(
    start_month=7, start_day=1, start_hour=12,
    end_month=7, end_day=31, end_hour=16,
)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "outputs", "utci_result.html")


def main() -> None:
    with InfraredClient(logger=logger) as client:
        logger.info("Fetching buildings, vegetation, ground materials...")
        area = client.buildings.get_area(POLYGON)
        area_veg = client.vegetation.get_area(POLYGON)
        area_gm = client.ground_materials.get_area(POLYGON)
        logger.info(
            "Buildings=%d, trees=%d, ground material features=%d",
            area.total_buildings, area_veg.total_trees, area_gm.total_features,
        )

        # Pre-filter ground materials to avoid HTTP 413 on large polygons
        gm_for_run = area_gm.layers if area_gm.total_features <= 5000 else {}

        logger.info("Locating nearest weather station...")
        stations = client.weather.get_weather_file_from_location(
            lat=LATITUDE, lon=LONGITUDE, radius=50,
        )
        if not stations:
            raise RuntimeError("No weather stations found for the given location")
        weather_id = stations[0].get("identifier") or stations[0].get("uuid")
        logger.info("Weather station: %s", weather_id)

        weather_data = client.weather.filter_weather_data(
            identifier=weather_id, time_period=TIME_PERIOD,
        )
        logger.info("Filtered %d weather data points", len(weather_data))

        payload = UtciModelRequest.from_weatherfile_payload(
            payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
            location=Location(latitude=LATITUDE, longitude=LONGITUDE),
            time_period=TIME_PERIOD,
            weather_data=weather_data,
        )

        logger.info("Running UTCI analysis...")
        result = client.run_area_and_wait(
            payload, POLYGON,
            buildings=area.buildings,
            vegetation=area_veg.features,
            ground_materials=gm_for_run,
        )
        logger.info(
            "Grid=%s, %d/%d jobs OK, legend=[%.1f, %.1f] °C-UTCI",
            result.grid_shape, result.succeeded_jobs, result.total_jobs,
            result.min_legend, result.max_legend,
        )

    fig = go.Figure(go.Heatmap(
        z=result.merged_grid,
        colorscale="RdBu_r",
        zmin=result.min_legend, zmax=result.max_legend,
        colorbar=dict(title="UTCI °C"),
    ))
    fig.update_layout(
        title=f"UTCI | summer afternoons | {result.grid_shape[0]}x{result.grid_shape[1]} cells",
        width=900, height=900, template="plotly_white",
        yaxis=dict(scaleanchor="x", scaleratio=1),
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.write_html(OUTPUT_PATH, include_plotlyjs=True)
    logger.info("Saved: %s", os.path.abspath(OUTPUT_PATH))


if __name__ == "__main__":
    main()
