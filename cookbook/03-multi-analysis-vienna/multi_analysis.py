"""Demo: run all 8 analysis types over a polygon and visualize results.

Demonstrates the full Infrared SDK pipeline:
  1. Fetch buildings, vegetation, and ground materials once
  2. Fetch and filter weather data
  3. Run all 8 analysis types grouped by layer requirements
  4. Visualize results as a multi-panel Plotly HTML

Usage::

    python multi_analysis.py

Requires INFRARED_API_KEY in environment or a .env file in the repo root.
"""

from __future__ import annotations

import logging
import math
import os

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import (
    AnalysesName,
    BaseAnalysisPayload,
    PwcCriteria,
    PwcModelRequest,
    SolarModelRequest,
    SolarRadiationModelRequest,
    SvfModelRequest,
    TcsModelBaseRequest,
    TcsModelRequest,
    TcsSubtype,
    UtciModelBaseRequest,
    UtciModelRequest,
    WindModelRequest,
)
from infrared_sdk.tiling.types import AreaResult, AreaState
from infrared_sdk.models import Location, TimePeriod, extract_weather_fields

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logging.getLogger("infrared_sdk").setLevel(logging.WARNING)
logger = logging.getLogger("demo_vienna")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [16.331274, 48.204341],
        [16.331274, 48.200881],
        [16.338484, 48.200881],
        [16.338484, 48.204341],
        [16.331274, 48.204341],
    ]],
}

LATITUDE = 48.2026
LONGITUDE = 16.3349

TIME_PERIOD = TimePeriod(
    start_month=8, start_day=1, start_hour=9,
    end_month=8, end_day=31, end_hour=17,
)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "outputs", "vienna_output.html")

# Visualization config per analysis type
_VIZ = {
    AnalysesName.wind_speed:                 ("Wind Speed",            "Turbo",     "m/s"),
    AnalysesName.sky_view_factors:           ("Sky View Factors",      "Viridis",   "SVF"),
    AnalysesName.pedestrian_wind_comfort:    ("PWC (Lawson LDDC)",     None,        "class"),
    AnalysesName.daylight_availability:      ("Daylight Availability", "YlOrRd",    "hours"),
    AnalysesName.direct_sun_hours:           ("Direct Sun Hours",      "YlOrBr",    "hours"),
    AnalysesName.solar_radiation:            ("Solar Radiation",       "Inferno",   "kWh/m2"),
    AnalysesName.thermal_comfort_index:      ("UTCI",                  "RdBu_r",   "UTCI C"),
    AnalysesName.thermal_comfort_statistics: ("TCS (Heat Stress)",     "RdYlGn_r", "stress"),
}

_PWC_COLORSCALE = [
    [0.0, "rgb(0,100,0)"], [0.25, "rgb(144,238,144)"],
    [0.5, "rgb(255,255,0)"], [0.75, "rgb(255,165,0)"], [1.0, "rgb(220,20,60)"],
]
_PWC_LABELS = ["A: Sit long", "B: Sit short", "C: Stroll", "D: Walk", "E: Unsafe"]


def _on_progress(state: AreaState) -> None:
    logger.info("  [%s] %d/%d done, %d running, %d failed", state.status,
                state.succeeded, state.total, state.running, state.failed)


def _to_display(grid: np.ndarray) -> list:
    result = grid.copy().astype(object)
    result[np.isnan(grid)] = None
    return result.tolist()


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def generate_visualization(
    results: dict[str, AreaResult],
    gm_layers: dict | None = None,
    veg_features: dict | None = None,
) -> None:
    order = list(_VIZ.keys())
    panels = [(t, results[t]) for t in order if t in results]
    if not panels:
        logger.warning("No results to visualize.")
        return

    n_cols = min(len(panels), 4)
    n_heat_rows = math.ceil(len(panels) / n_cols)
    has_layers = gm_layers or veg_features
    n_rows = n_heat_rows + (1 if has_layers else 0)

    titles = []
    for t, r in panels:
        label = _VIZ[t][0]
        titles.append(f"{label} ({r.succeeded_jobs}/{r.total_jobs})")
    if gm_layers:
        titles.append("Ground Materials")
    if veg_features:
        titles.append("Vegetation")
    while len(titles) < n_rows * n_cols:
        titles.append("")

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=titles[:n_rows * n_cols],
        horizontal_spacing=0.04, vertical_spacing=0.08,
    )

    for idx, (atype, result) in enumerate(panels):
        row, col = idx // n_cols + 1, idx % n_cols + 1
        title, colorscale, unit = _VIZ[atype]
        grid = result.merged_grid

        if atype == AnalysesName.pedestrian_wind_comfort:
            fig.add_trace(go.Heatmap(
                z=_to_display(grid), colorscale=_PWC_COLORSCALE,
                zmin=0, zmax=4, showscale=True,
                colorbar=dict(title="class", len=0.25, thickness=12,
                              tickvals=list(range(5)), ticktext=_PWC_LABELS),
            ), row=row, col=col)
        else:
            fig.add_trace(go.Heatmap(
                z=_to_display(grid), colorscale=colorscale,
                zmin=result.min_legend, zmax=result.max_legend,
                showscale=True, colorbar=dict(title=unit, len=0.25, thickness=12),
            ), row=row, col=col)

    # Layer panels
    if has_layers:
        layer_row = n_heat_rows + 1
        layer_col = 1
        if gm_layers:
            _COLORS = {
                "vegetation": "rgba(76,175,80,0.4)", "water": "rgba(33,150,243,0.4)",
                "asphalt": "rgba(158,158,158,0.4)", "concrete": "rgba(189,189,189,0.4)",
                "soil": "rgba(141,110,99,0.4)", "building": "rgba(255,152,0,0.3)",
            }
            for name, fc in gm_layers.items():
                if not isinstance(fc, dict):
                    continue
                for feat in fc.get("features", []):
                    geom = feat.get("geometry", {})
                    rings = []
                    if geom.get("type") == "Polygon":
                        rings = [geom.get("coordinates", [[]])[0]]
                    elif geom.get("type") == "MultiPolygon":
                        rings = [p[0] for p in geom.get("coordinates", [])]
                    for ring in rings:
                        if not ring:
                            continue
                        fig.add_trace(go.Scatter(
                            x=[pt[0] for pt in ring], y=[pt[1] for pt in ring],
                            mode="lines", fill="toself",
                            fillcolor=_COLORS.get(name, "rgba(200,200,200,0.3)"),
                            line=dict(width=1), name=name, legendgroup=name, showlegend=False,
                        ), row=layer_row, col=layer_col)
            layer_col += 1

        if veg_features:
            lons, lats = [], []
            for feat in veg_features.values():
                coords = (feat.get("geometry") or {}).get("coordinates", [])
                if len(coords) >= 2:
                    lons.append(coords[0])
                    lats.append(coords[1])
            if lons:
                fig.add_trace(go.Scatter(
                    x=lons, y=lats, mode="markers",
                    marker=dict(size=6, color="rgb(56,142,60)", opacity=0.7),
                    name=f"Trees ({len(lons)})", showlegend=True,
                ), row=layer_row, col=layer_col)

    first = panels[0][1]
    fig.update_layout(
        title_text=(
            f"{len(panels)} analyses | {first.grid_shape[0]}x{first.grid_shape[1]} cells | "
            f"{sum(r.total_jobs for _, r in panels)} jobs"
        ),
        title_font_size=14, height=400 * n_rows, width=1600, template="plotly_white",
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.write_html(OUTPUT_PATH, include_plotlyjs=True)
    logger.info("Saved visualization: %s", OUTPUT_PATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    with InfraredClient(logger=logger) as client:
        # 1. Fetch all layers once
        logger.info("Fetching buildings...")
        area = client.buildings.get_area(POLYGON)
        logger.info("Found %d buildings", area.total_buildings)

        logger.info("Fetching vegetation...")
        area_veg = client.vegetation.get_area(POLYGON)
        logger.info("Found %d trees", area_veg.total_trees)

        logger.info("Fetching ground materials...")
        area_gm = client.ground_materials.get_area(POLYGON)
        logger.info("Found %d ground material features", area_gm.total_features)

        # Skip ground materials injection if too large (HTTP 413 risk)
        gm_for_analyses = area_gm.layers if area_gm.total_features <= 5000 else {}
        if not gm_for_analyses and area_gm.total_features > 0:
            logger.warning("Ground materials too large (%d features), skipping for analyses", area_gm.total_features)

        # 2. Fetch weather data
        logger.info("Fetching weather data...")
        stations = client.weather.get_weather_file_from_location(lat=LATITUDE, lon=LONGITUDE, radius=50)
        if not stations:
            raise RuntimeError("No weather stations found")
        weather_id = stations[0].get("identifier") or stations[0].get("uuid")
        logger.info("Using weather station: %s", weather_id)

        weather_data = client.weather.filter_weather_data(identifier=weather_id, time_period=TIME_PERIOD)
        logger.info("Filtered %d weather data points", len(weather_data))

        wind_fields = extract_weather_fields(weather_data, ["windSpeed", "windDirection"])
        location = Location(latitude=LATITUDE, longitude=LONGITUDE)

        # 3. Build payloads in 3 groups by layer requirements
        group_a = [
            WindModelRequest(analysis_type=AnalysesName.wind_speed, wind_speed=5, wind_direction=270),
            SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                            latitude=LATITUDE, longitude=LONGITUDE),
            PwcModelRequest(analysis_type=AnalysesName.pedestrian_wind_comfort,
                            criteria=PwcCriteria.lawson_lddc, **wind_fields),
        ]

        group_b = [
            SolarModelRequest(analysis_type=AnalysesName.daylight_availability,
                              latitude=LATITUDE, longitude=LONGITUDE, time_period=TIME_PERIOD),
            SolarModelRequest(analysis_type=AnalysesName.direct_sun_hours,
                              latitude=LATITUDE, longitude=LONGITUDE, time_period=TIME_PERIOD),
            SolarRadiationModelRequest.from_weatherfile_payload(
                payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
                location=location, time_period=TIME_PERIOD, weather_data=weather_data),
        ]

        group_c = [
            UtciModelRequest.from_weatherfile_payload(
                payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
                location=location, time_period=TIME_PERIOD, weather_data=weather_data),
            TcsModelRequest.from_weatherfile_payload(
                payload=TcsModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_statistics,
                                            subtype=TcsSubtype.heat_stress),
                location=location, time_period=TIME_PERIOD, weather_data=weather_data),
        ]

        # 4. Run each group
        results: dict[str, AreaResult] = {}

        def _collect(label: str, result_list: list[AreaResult]) -> None:
            for r in result_list:
                logger.info("  %s: grid=%s, %d/%d jobs", _VIZ.get(r.analysis_type, (r.analysis_type,))[0],
                            r.grid_shape, r.succeeded_jobs, r.total_jobs)
                results[r.analysis_type] = r

        logger.info("Running group A: buildings only (%d analyses)...", len(group_a))
        _collect("A", client.run_area_and_wait(
            group_a, POLYGON, buildings=area.buildings,
            vegetation={}, ground_materials={}, on_progress=_on_progress))

        logger.info("Running group B: buildings + vegetation (%d analyses)...", len(group_b))
        _collect("B", client.run_area_and_wait(
            group_b, POLYGON, buildings=area.buildings,
            vegetation=area_veg.features, ground_materials={}, on_progress=_on_progress))

        logger.info("Running group C: all layers (%d analyses)...", len(group_c))
        _collect("C", client.run_area_and_wait(
            group_c, POLYGON, buildings=area.buildings,
            vegetation=area_veg.features, ground_materials=gm_for_analyses, on_progress=_on_progress))

        # 5. Summary
        total = sum(r.total_jobs for r in results.values())
        ok = sum(r.succeeded_jobs for r in results.values())
        logger.info("All done: %d/%d jobs succeeded across %d analyses", ok, total, len(results))

    # 6. Visualize
    generate_visualization(
        results,
        gm_layers=area_gm.layers if area_gm.total_features > 0 else None,
        veg_features=area_veg.features if area_veg.total_trees > 0 else None,
    )


if __name__ == "__main__":
    main()
