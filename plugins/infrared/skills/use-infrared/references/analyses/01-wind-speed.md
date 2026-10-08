# Wind speed (`wind-speed`)

Wind speed near pedestrian height, for one speed and one direction. Cells are m/s.
Use it for the flow field. For comfort over a year, use pedestrian wind comfort.

Run: shape of the call is in [../python/weather-and-time.md](../python/weather-and-time.md#wind).
Doc: <https://infrared.city/docs/sdk/1.0/python/analyses/index.md>

```python
from infrared_sdk import WindModelRequest
from infrared_sdk.analyses.types import AnalysesName

request = WindModelRequest(
    analysis_type=AnalysesName.wind_speed,
    wind_speed=4.5,         # float, m/s, 0 or more. Do not round an EPW mean.
    wind_direction=270,     # whole degrees (int), wind FROM this bearing (270 = from the west)
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
speed = result.physical_grid()          # m/s, NaN = no value
```

## Parameters

| Field | Type | Note |
|---|---|---|
| `wind_speed` | float | 0 or more (m/s). Rounding 3.9 to 3 shifts every cell by -23 % |
| `wind_direction` | int | Meteorological: 0 = from north, 90 = from east. Values outside 0-360 wrap. A fraction is refused |
| `latitude`, `longitude` | optional | Ignored by wind |

Wind takes buildings, trees and ground. It has no `ground_geometry` (so `terrain_alignment` has no use), no `context_geometry` and no facade sensors.

## Tiles

Wind tiles are 512 m with a step of 256 m, so they overlap. The default merge keeps the centre of
each tile. On a multi-tile area, `directional_blend` removes seams. It needs two steps:

```python
schedule = client.run_area(request, polygon, buildings=buildings)
# ... wait until all jobs end (client.check_area_state(schedule)) ...
result = client.merge_area_jobs(schedule, strategy="directional_blend",
                                wind_direction_deg=270.0)   # same value as the request
```

## Pitfalls

- One snapshot only. Run several directions for a yearly picture, or use pedestrian wind comfort.
- 270 means from the west. This is easy to invert.
- Plot with a fixed scale (0 to 15 m/s, open top bin), not the grid min and max.

Read the result: [../interpretation/wind-results.md](../interpretation/wind-results.md)
