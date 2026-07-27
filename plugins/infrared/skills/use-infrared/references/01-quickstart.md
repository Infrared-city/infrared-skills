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

# api_key falls back to INFRARED_API_KEY env var; base URL ships with the SDK
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

`result.merged_grid` is a 2-D numpy array (~1 m per cell, NaN outside the polygon). Deriving the colour range from the data alone produces washed-out heatmaps for solar/daylight analyses — and a different scale on every run. On an `AreaResult`, `min_legend` / `max_legend` are **`None`**, so fix a per-analysis domain yourself (`recipes/rendering-results-well.md`); they are populated only on `SurfaceAnalysisResult`.

## Pitfalls

- Buildings are opt-in: pass `buildings=area.buildings` explicitly. `None` or `{}` skips them.
- `wind_speed` is a **`float`** in m/s (0 accepted) — do not round an EPW mean like `3.9`.
  `wind_direction` is `int` 0–360 (meteorological: 0 = wind from north), deliberately whole.
- Plot heatmaps on a fixed per-analysis domain. `zmin=result.min_legend` is `None` on an area run, so this is not the shortcut it looks like.
- Single-tile polygons (~512 m on a side or smaller) skip tiling entirely — no special handling needed.
- The first request in a session may be slower while the backend warms up; benchmark from the second call.

## See also

- `02-geometry.md` — polygon format and validation
- `03-time-period.md` — for analyses that need a TimePeriod
- `analyses/01-wind-speed.md` — full wind-speed parameter reference
