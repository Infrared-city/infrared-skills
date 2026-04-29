# Wind Speed (wind-speed)

Steady-state CFD-style wind magnitude near pedestrian height for a single inflow condition. Output cells are wind speed in m/s. Use when you need the raw flow field, not a comfort classification.

## Request

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
