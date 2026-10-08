"""Thermal comfort: UTCI on a summer afternoon, with your trees and ground.

Run:
    pip install infrared-sdk matplotlib shapely
    export INFRARED_API_KEY=...
    python comfort.py  # --yes: no cost question; --verbose: SDK progress

Vienna Karlsplatz baseline (own buildings, trees, ground) + the nearest public weather
station. Runs UTCI (degrees C) for 15 July 12-17 h and saves `comfort_utci.png`.
Docs: https://infrared.city/docs/sdk/#weather-and-time-period
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# SDK progress lines stay hidden unless you pass --verbose (set before the import).
if "--verbose" not in sys.argv:
    os.environ.setdefault("INFRARED_QUIET", "1")

from infrared_sdk import InfraredClient  # noqa: E402
from infrared_sdk.analyses.types import AnalysesName, UtciModelBaseRequest, UtciModelRequest  # noqa: E402
from infrared_sdk.models import Location, TimePeriod  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "notebooks"))  # ir_site.py: GeoJSON -> SDK inputs
import ir_site as site  # noqa: E402

DATA = HERE.parent / "sample-data" / "vienna-demo" / "scenarios" / "01-baseline"
# UTCI stress classes (degrees C): the colour steps of the map.
CLASSES = [
    (9, "no thermal stress"),
    (26, "moderate heat stress"),
    (32, "strong heat stress"),
    (38, "very strong heat stress"),
    (46, "extreme heat stress"),
]


def main() -> None:
    client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])

    # 1. Your model: buildings as meshes (metres), trees and ground in lon/lat.
    footprints = site.read_geojson(DATA / "buildings.geojson")
    polygon = site.polygon_around(footprints["features"], pad_m=30)
    origin = site.origin_of(polygon)
    buildings = site.buildings_from_geojson(footprints, origin)
    trees = site.trees_from_geojson(site.read_geojson(DATA / "trees.geojson"))
    ground = site.ground_from_geojson(site.read_geojson(DATA / "surfaces.geojson"))
    print(f"{len(buildings)} buildings, {len(trees)} trees, ground layers {sorted(ground)}")

    # 2. Weather: the nearest public station, filtered to the window.
    lon, lat = np.mean(polygon["coordinates"][0][:4], axis=0)
    station = client.weather.get_weather_file_from_location(lat=lat, lon=lon)[0]
    window = TimePeriod(start_month=7, start_day=15, start_hour=12, end_month=7, end_day=15, end_hour=17)
    hours = client.weather.filter_weather_data(identifier=station["uuid"], time_period=window)
    print(f"weather: {station['location_data']['city']}, {len(hours)} hours")

    # 3. The request (the seven weather columns are filled in for you), and the cost.
    request = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
        location=Location(latitude=lat, longitude=lon),
        time_period=window,
        weather_data=hours,
    )
    layers = dict(buildings=buildings, vegetation=trees, ground_materials=ground)
    preview = client.preview_area(polygon, payload=request, **layers)
    print(
        f"tiles {preview.tile_count}, jobs {preview.would_bill_jobs}, "
        f"cost {preview.estimated_cost_tokens} tokens"
    )
    if "--yes" not in sys.argv and input("Run? [y/N] ").strip().lower() != "y":
        return

    # 4. Run. physical_grid() gives degrees C (never read the raw array).
    result = client.run_area_and_wait(request, polygon, **layers)
    grid = result.physical_grid()
    values = grid[np.isfinite(grid)]
    print(f"UTCI: min {values.min():.1f}, mean {values.mean():.1f}, max {values.max():.1f} °C")
    for (low, name), (high, _) in zip(CLASSES, CLASSES[1:] + [(99, "")]):
        print(f"  {name:24s} {((values >= low) & (values < high)).mean():6.1%}")

    # 5. The map in stress classes, with the footprints on top.
    width, depth = site.size_m(polygon)
    rows, cols = grid.shape
    bounds = [low for low, _ in CLASSES] + [50]
    # cold (below 9), no stress (green), then heat stress from yellow to dark red
    cmap = matplotlib.colors.ListedColormap(
        ["#74add1", "#a6d96a", "#fee08b", "#fdae61", "#f46d43", "#a50026"]
    )
    norm = matplotlib.colors.BoundaryNorm([0] + bounds, cmap.N)
    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(grid, origin="lower", cmap=cmap, norm=norm, extent=(0, cols, 0, rows))
    for feature in footprints["features"]:
        x, y = site.footprint_xy(feature, origin).exterior.xy
        ax.plot(x, y, color="#44403c", lw=0.5)
    ax.set(
        xlim=(0, width),
        ylim=(0, depth),
        xlabel="x east [m]",
        ylabel="y north [m]",
        title="UTCI, 15 July 12-17 h, Karlsplatz",
    )
    ax.set_frame_on(False)
    fig.colorbar(im, ax=ax, shrink=0.75, label="UTCI [°C]", ticks=bounds)
    fig.tight_layout()
    fig.savefig("comfort_utci.png", dpi=120)
    print("saved comfort_utci.png")


if __name__ == "__main__":
    main()
