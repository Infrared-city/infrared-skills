# Python quick start

Install, set the key, run one analysis on your own building, read the result.
This page shows the shape of the code. For each call, the docs page has the full detail.

- Guide: <https://infrared.city/docs/sdk/> (one file: <https://infrared.city/docs/sdk/sdk.md>)
- Client reference: <https://infrared.city/docs/sdk/1.0/python/sdk/index.md>

## Install and key

```bash
pip install infrared-sdk                 # Python 3.9 or later
pip install "infrared-sdk[geodata]"      # only to read public buildings, trees and ground
export INFRARED_API_KEY=...              # the client reads this variable
```

Never write the key in code or in a repository.

## One run, end to end

```python
import numpy as np
from infrared_sdk import InfraredClient, SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

# 1. The area: one GeoJSON polygon in WGS84, ring order [lon, lat].
lon, lat = 16.371, 48.208
polygon = {"type": "Polygon", "coordinates": [[
    [lon, lat], [lon + 0.004, lat], [lon + 0.004, lat + 0.003],
    [lon, lat + 0.003], [lon, lat]]]}

# 2. Your own geometry, in metres. The origin (0, 0) is the south-west
#    corner of the polygon bounding box. x is east, y is north, z is up.
#    This stand-in is one box tower, 20 m wide and 30 m high.
xy = [(100, 100), (120, 100), (120, 120), (100, 120)]
coordinates = [c for z in (0, 30) for x, y in xy for c in (x, y, z)]
indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
buildings = {"tower": {"coordinates": coordinates, "indices": indices}}

# 3. The client reads INFRARED_API_KEY from the environment.
client = InfraredClient()

# 4. The request. Sky view factor needs no weather and no time period.
request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)

# 5. Preview first. It is free and local: it sends no job.
preview = client.preview_area(polygon, payload=request)
print(preview.would_bill_jobs, preview.estimated_cost_tokens)

# 6. Run. The SDK tiles the area, uploads, polls and merges for you.
result = client.run_area_and_wait(request, polygon, buildings=buildings)

# 7. Read values with the helper. NaN means "no value".
grid = result.physical_grid()          # 2-D array, row 0 = south, 1 m cells
print(grid.shape, float(np.nanmin(grid)), float(np.nanmax(grid)))
print(result.bounds)                   # (west, south, east, north) of the grid
```

## Look at it

```python
import matplotlib
matplotlib.use("Agg")                  # no display needed
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(5, 5))
# origin="lower" puts row 0 (south) at the bottom, so north is up.
im = ax.imshow(grid, origin="lower", cmap="viridis", vmin=0, vmax=100)
fig.colorbar(im, label="Sky view factor (%)")
fig.savefig("svf.png", dpi=120)
```

Use a fixed colour scale per analysis, so two runs stay comparable. See
[../recipes/rendering-results-well.md](../recipes/rendering-results-well.md).

## Rules that save you a run

- Always read results with `physical_grid()`. Never read `merged_grid` directly:
  its stored type changes with the analysis.
- Use `result.bounds` to place the picture on a map. Do not compute the extent yourself.
- Call `preview_area` with the same `payload=` as the run. Price from `would_bill_jobs`.
- A failed tile never gives a map with holes. The call raises `AreaRunError`.
  See [errors-and-retries.md](errors-and-retries.md).
- To run several analyses on one geometry, pass a list as the first argument.
  You get a list of results in the same order.

## Next

| You want | Read |
|---|---|
| Your buildings, trees and ground | [own-data.md](own-data.md) |
| Weather, UTCI, solar radiation, a year or winter window | [weather-and-time.md](weather-and-time.md) |
| Values on facades, roofs or your own points | [surfaces-and-sensors.md](surfaces-and-sensors.md) |
| Rooms: daylight factor, energy balance | [interior.md](interior.md) |
| Errors, retries, no credits | [errors-and-retries.md](errors-and-retries.md) |
| Each analysis: parameters and how to read it | [../analyses/](../analyses/01-wind-speed.md) |
