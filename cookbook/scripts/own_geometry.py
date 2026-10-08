"""Your own geometry: direct sun hours on midsummer day for a Vienna block.

Run:
    pip install infrared-sdk matplotlib shapely
    export INFRARED_API_KEY=...
    python own_geometry.py  # --yes: no cost question; --verbose: SDK progress

It reads your own model (here the Vienna Karlsplatz baseline in
`../sample-data/vienna-demo/scenarios/01-baseline`): footprints with heights,
and trees. It extrudes the footprints to closed meshes in metres, previews
the cost, runs direct sun hours for 21 June and saves `own_geometry_dsh.png`.
Replace the GeoJSON files with your own data.
Docs: https://infrared.city/docs/sdk/#your-inputs
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

from infrared_sdk import InfraredClient, SolarModelRequest  # noqa: E402
from infrared_sdk.analyses.types import AnalysesName  # noqa: E402
from infrared_sdk.models import TimePeriod  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "notebooks"))  # ir_site.py: GeoJSON -> meshes
import ir_site as site  # noqa: E402

DATA = HERE.parent / "sample-data" / "vienna-demo" / "scenarios" / "01-baseline"


def main() -> None:
    client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])

    # 1. Your model. The run polygon is the bbox of the footprints plus 30 m; its
    #    south-west corner is the origin. Buildings are meshes in metres (z up).
    footprints = site.read_geojson(DATA / "buildings.geojson")
    polygon = site.polygon_around(footprints["features"], pad_m=30)
    origin = site.origin_of(polygon)
    buildings = site.buildings_from_geojson(footprints, origin)
    # Trees stay in lon/lat: the SDK moves them into each tile.
    trees = site.trees_from_geojson(site.read_geojson(DATA / "trees.geojson"))
    print(f"{len(buildings)} buildings, {len(trees)} trees")

    # 2. Direct sun hours on 21 June, 05-21 h. It needs a time window and a location.
    lon, lat = np.mean(polygon["coordinates"][0][:4], axis=0)
    request = SolarModelRequest(
        analysis_type=AnalysesName.direct_sun_hours,
        latitude=lat,
        longitude=lon,
        time_period=TimePeriod(
            start_month=6, start_day=21, start_hour=5, end_month=6, end_day=21, end_hour=21
        ),
    )
    preview = client.preview_area(polygon, payload=request, buildings=buildings, vegetation=trees)
    print(
        f"tiles {preview.tile_count}, jobs {preview.would_bill_jobs}, "
        f"cost {preview.estimated_cost_tokens} tokens"
    )
    if "--yes" not in sys.argv and input("Run? [y/N] ").strip().lower() != "y":
        return

    # 3. Run, and read real values (NaN = no value).
    result = client.run_area_and_wait(request, polygon, buildings=buildings, vegetation=trees)
    grid = result.physical_grid()
    values = grid[np.isfinite(grid)]
    print(
        f"direct sun hours: mean {values.mean():.1f} h, max {values.max():.1f} h, "
        f"less than 4 h on {(values < 4).mean():.0%} of the open ground"
    )

    # 4. The map, with your footprints on top: they must sit on the gaps of the grid.
    width, depth = site.size_m(polygon)
    rows, cols = grid.shape
    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(
        grid, origin="lower", cmap="plasma", vmin=0, vmax=np.nanmax(grid), extent=(0, cols, 0, rows)
    )  # row 0 = south
    for feature in footprints["features"]:
        x, y = site.footprint_xy(feature, origin).exterior.xy
        ax.plot(x, y, color="white", lw=0.6)
    ax.set(
        xlim=(0, width),
        ylim=(0, depth),
        xlabel="x east [m]",
        ylabel="y north [m]",
        title="Direct sun hours on 21 June, Karlsplatz (your own model)",
    )
    ax.set_frame_on(False)
    fig.colorbar(im, ax=ax, shrink=0.75, label="hours of direct sun")
    fig.tight_layout()
    fig.savefig("own_geometry_dsh.png", dpi=120)
    print("saved own_geometry_dsh.png")


if __name__ == "__main__":
    main()
