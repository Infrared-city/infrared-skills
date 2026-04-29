"""Fetch buildings, vegetation, and ground materials and plot the layers.

No analysis is run — useful for visually inspecting which layers the SDK will
inject into a simulation, and for sanity-checking polygon coverage.

Usage::

    uv run python demos/demo_fetch_layers.py

Requires INFRARED_API_KEY in environment or a .env file in the repo root.
"""

from __future__ import annotations

import logging
import os

import plotly.graph_objects as go
from dotenv import load_dotenv

from infrared_sdk import InfraredClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("demo_fetch_layers")

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

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "outputs", "layers_overview.html")

GM_COLORS = {
    "vegetation": "rgba(76,175,80,0.45)",
    "water": "rgba(33,150,243,0.45)",
    "asphalt": "rgba(80,80,80,0.45)",
    "concrete": "rgba(180,180,180,0.45)",
    "soil": "rgba(141,110,99,0.45)",
    "building": "rgba(255,152,0,0.30)",
}


def main() -> None:
    with InfraredClient(logger=logger) as client:
        logger.info("Fetching layers...")
        area = client.buildings.get_area(POLYGON)
        area_veg = client.vegetation.get_area(POLYGON)
        area_gm = client.ground_materials.get_area(POLYGON)
        logger.info(
            "Buildings=%d, trees=%d, ground material features=%d",
            area.total_buildings,
            area_veg.total_trees,
            area_gm.total_features,
        )

    fig = go.Figure()

    # Polygon outline
    ring = POLYGON["coordinates"][0]
    fig.add_trace(
        go.Scatter(
            x=[p[0] for p in ring],
            y=[p[1] for p in ring],
            mode="lines",
            line=dict(color="black", width=2, dash="dash"),
            name="Polygon",
        )
    )

    # Ground materials (filled polygons in lon/lat)
    for name, fc in (area_gm.layers or {}).items():
        if not isinstance(fc, dict):
            continue
        for feat in fc.get("features", []):
            geom = feat.get("geometry", {})
            rings = []
            if geom.get("type") == "Polygon":
                rings = [geom.get("coordinates", [[]])[0]]
            elif geom.get("type") == "MultiPolygon":
                rings = [p[0] for p in geom.get("coordinates", [])]
            for poly_ring in rings:
                if not poly_ring:
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=[pt[0] for pt in poly_ring],
                        y=[pt[1] for pt in poly_ring],
                        mode="lines",
                        fill="toself",
                        fillcolor=GM_COLORS.get(name, "rgba(200,200,200,0.3)"),
                        line=dict(
                            width=0.5,
                            color=GM_COLORS.get(name, "rgba(120,120,120,0.6)"),
                        ),
                        name=name,
                        legendgroup=name,
                        showlegend=False,
                    )
                )
        # one legend marker per material
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(
                    size=10, color=GM_COLORS.get(name, "rgba(200,200,200,0.6)")
                ),
                name=name,
                legendgroup=name,
                showlegend=True,
            )
        )

    # Trees (points in lon/lat)
    if area_veg.features:
        lons, lats = [], []
        for feat in area_veg.features.values():
            coords = (feat.get("geometry") or {}).get("coordinates", [])
            if len(coords) >= 2:
                lons.append(coords[0])
                lats.append(coords[1])
        fig.add_trace(
            go.Scatter(
                x=lons,
                y=lats,
                mode="markers",
                marker=dict(
                    size=6, color="rgb(56,142,60)", opacity=0.85, symbol="circle"
                ),
                name=f"Trees ({len(lons)})",
            )
        )

    fig.update_layout(
        title=(
            f"Layer coverage | buildings={area.total_buildings}, "
            f"trees={area_veg.total_trees}, ground features={area_gm.total_features}"
        ),
        width=1100,
        height=900,
        template="plotly_white",
        xaxis_title="Longitude",
        yaxis_title="Latitude",
        yaxis=dict(scaleanchor="x", scaleratio=1.4),  # rough Munich-latitude correction
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.write_html(OUTPUT_PATH, include_plotlyjs=True)
    logger.info("Saved: %s", os.path.abspath(OUTPUT_PATH))


if __name__ == "__main__":
    main()
