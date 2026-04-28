# Quickstart

End-to-end wind-speed run: define a polygon, fetch buildings for the area, run the analysis, read the merged grid. Lifted verbatim from the SDK README.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName

polygon = {
    "type": "Polygon",
    "coordinates": [[
        [11.570, 48.195], [11.580, 48.195],
        [11.580, 48.201], [11.570, 48.201],
        [11.570, 48.195],
    ]],
}

# api_key and base_url fall back to INFRARED_API_KEY / INFRARED_BASE_URL env vars
with InfraredClient() as client:
    # 1. Fetch buildings for the area
    area = client.buildings.get_area(polygon)

    # 2. Run a wind analysis over the polygon
    result = client.run_area_and_wait(
        WindModelRequest(
            analysis_type=AnalysesName.wind_speed,
            wind_speed=15,
            wind_direction=180,
        ),
        polygon,
        buildings=area.buildings,
    )

    # 3. Result contains a merged grid covering the polygon
    print(f"Grid shape: {result.grid_shape}")
```

## Reading the result

`result.merged_grid` is a 2-D numpy array (~1 m per cell, NaN outside the polygon). Use `result.min_legend` / `result.max_legend` as the colour-scale bounds when plotting — deriving the range from the data alone produces washed-out heatmaps for solar/daylight analyses.

## Pitfalls

- Buildings are opt-in: pass `buildings=area.buildings` explicitly. `None` or `{}` skips them.
- `wind_speed` is `int` 1–100 (m/s); `wind_direction` is `int` 0–360 (meteorological: 0 = wind from north).
- Always plot heatmaps with `zmin=result.min_legend, zmax=result.max_legend`.
- Single-tile polygons (~512 m on a side or smaller) skip tiling entirely — no special handling needed.
- The first request in a session is 2–5x slower (Lambda cold start); benchmark from the second call.

## See also

- `02-geometry.md` — polygon format and validation
- `03-time-period.md` — for analyses that need a TimePeriod
- `analyses/wind-speed.md` — full wind-speed parameter reference
