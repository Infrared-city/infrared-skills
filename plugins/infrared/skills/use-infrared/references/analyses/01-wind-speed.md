# Wind Speed (wind-speed)

Steady-state CFD-style wind magnitude near pedestrian height for a single inflow condition. Output cells are wind speed in m/s. Use when you need the raw flow field, not a comfort classification.

## Request

### Single-tile or quick sanity check — one-shot

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName

payload = WindModelRequest(
    analysis_type=AnalysesName.wind_speed,
    wind_speed=15,
    wind_direction=180,
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

`run_area_and_wait` always merges with the default centre-crop strategy. For single-tile polygons that's optimal; for multi-tile runs it produces visible seam artefacts at tile boundaries.

### Recommended for multi-tile runs — two-step with `directional_blend`

```python
import time

schedule = client.run_area(payload, polygon, buildings=area.buildings)

time.sleep(4)  # let API register jobs before first poll
while True:
    state = client.check_area_state(schedule)
    if state.running == 0 and (state.succeeded + state.failed) >= len(schedule.jobs):
        break
    time.sleep(8)

result = client.merge_area_jobs(
    schedule,
    strategy="directional_blend",
    wind_direction_deg=180.0,    # match payload.wind_direction
)
```

`wind_direction_deg` is required for `directional_blend` (and `directional`) — meteorological convention (0=N, 90=E, 180=S, 270=W). Match the value in the payload, or the blend weights point upwind in the wrong direction. See `../05-area-api.md#merging-strategies` for the full strategy table and `cookbook/notebooks/08_wind_merge_strategies.ipynb` for a side-by-side comparison.

## Response

`result.merged_grid` is a 2D `float` numpy array of wind speed in m/s at pedestrian height. `result.min_legend` / `max_legend` give the canonical color-scale bounds for plotting. `succeeded` / `failed` describe per-tile execution.

## Pitfalls

- `wind_speed` is an `int` in 1-100 m/s; floats and zero are rejected by the Pydantic validator.
- `wind_direction` follows the meteorological convention: 0 = wind FROM north, 90 = FROM east. Easy to invert.
- This is a single-direction snapshot — for comfort over a year of weather, use Pedestrian Wind Comfort instead.
- Leave `latitude` / `longitude` unset — they are optional and ignored by the wind model. (They become required only if you inject vegetation, since the validator needs a reference point. See [byo-inputs.md](../byo-inputs.md).)
- Always use `min_legend` / `max_legend` as your heatmap bounds, not the grid min/max.

## See also

- For result interpretation -> `interpretation/wind-results.md`
- For comfort classification -> `02-pedestrian-wind-comfort.md`
- For polygon/buildings setup -> `02-geometry.md`
