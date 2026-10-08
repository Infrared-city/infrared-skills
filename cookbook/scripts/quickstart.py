"""Quick start: sky view factor for one city area, from public buildings.

Run:
    pip install "infrared-sdk[geodata]" matplotlib
    export INFRARED_API_KEY=...
    python quickstart.py  # --yes: no cost question, --verbose: SDK progress lines

It reads the public buildings of a 400 m x 300 m area in Vienna, shows the
jobs and the cost, runs the sky view factor (how much open sky each point
sees, 0-100 %), prints the statistics and saves `quickstart_svf.png`.
Docs: https://infrared.city/docs/sdk/
"""

from __future__ import annotations

import math
import os
import sys

import matplotlib

matplotlib.use("Agg")  # no window: write a file
import matplotlib.pyplot as plt
import numpy as np

# SDK progress lines stay hidden unless you pass --verbose (set before the import).
if "--verbose" not in sys.argv:
    os.environ.setdefault("INFRARED_QUIET", "1")

from infrared_sdk import InfraredClient, SvfModelRequest  # noqa: E402
from infrared_sdk.analyses.types import AnalysesName  # noqa: E402

# 1. The area: a lon/lat polygon. Its south-west corner is the origin of the model.
LON, LAT = 16.3505, 48.2015  # Vienna, Neubau (south-west corner)
WIDTH, HEIGHT = 400.0, 300.0  # metres
dlon = WIDTH / (111_195.0 * math.cos(math.radians(LAT)))
dlat = HEIGHT / 111_195.0
polygon = {
    "type": "Polygon",
    "coordinates": [[[LON, LAT], [LON + dlon, LAT], [LON + dlon, LAT + dlat], [LON, LAT + dlat], [LON, LAT]]],
}


def main() -> None:
    client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])

    # 2. Public buildings (no model of your own yet). Keep the object: it knows its origin.
    buildings = client.buildings.get_area(polygon)
    print(f"{buildings.total_buildings} buildings")

    # 3. The request, and a free local preview of the jobs and the cost.
    request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)
    preview = client.preview_area(polygon, payload=request, buildings=buildings)
    print(
        f"tiles {preview.tile_count}, jobs {preview.would_bill_jobs}, "
        f"cost {preview.estimated_cost_tokens} tokens"
    )
    if "--yes" not in sys.argv and input("Run? [y/N] ").strip().lower() != "y":
        return

    # 4. Run. physical_grid() gives real values (NaN = no value, e.g. inside a building).
    result = client.run_area_and_wait(request, polygon, buildings=buildings)
    grid = result.physical_grid()
    values = grid[np.isfinite(grid)]
    print(
        f"sky view factor: min {values.min() + 0.0:.0f} %, mean {values.mean():.0f} %, "
        f"max {values.max():.0f} %"
    )
    print(f"share of open ground with less than 50 % sky: {(values < 50).mean():.0%}")

    # 5. The map. Row 0 of the grid is the south edge, so draw with origin="lower".
    rows, cols = grid.shape
    fig, ax = plt.subplots(figsize=(8, 6.2))
    cmap = plt.get_cmap("viridis").with_extremes(bad="#d6d3d1")  # buildings (no value): grey
    im = ax.imshow(grid, origin="lower", cmap=cmap, vmin=0, vmax=100, extent=(0, cols, 0, rows))
    ax.set(
        xlim=(0, WIDTH),
        ylim=(0, HEIGHT),
        xlabel="x east [m]",
        ylabel="y north [m]",
        title="Sky view factor, Vienna Neubau",
    )
    ax.set_frame_on(False)
    fig.colorbar(im, ax=ax, shrink=0.8, label="sky view factor [%]")
    fig.tight_layout()
    fig.savefig("quickstart_svf.png", dpi=120)
    print("saved quickstart_svf.png")


if __name__ == "__main__":
    main()
