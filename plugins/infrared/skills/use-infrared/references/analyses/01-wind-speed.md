# Wind speed (`wind-speed`)

Wind speed near pedestrian height, for one speed and one direction. Cells are m/s.
Use it for the flow field. For comfort over a year, use pedestrian wind comfort.

Run: shape of the call is in [../python/weather-and-time.md](../python/weather-and-time.md#wind).
Doc: <https://infrared.city/docs/sdk/1.0/python/analyses/index.md>

```python
import time

from infrared_sdk import WindModelRequest
from infrared_sdk.analyses.types import AnalysesName

# Pass every input wind reads: buildings and trees (no ground materials, terrain or installations).
buildings = client.buildings.get_area(polygon)
trees = client.vegetation.get_area(polygon).features

request = WindModelRequest(
    analysis_type=AnalysesName.wind_speed,
    wind_speed=4.5,         # float, m/s, 0 or more. Do not round an EPW mean.
    wind_direction=270,     # whole degrees (int), wind FROM this bearing (270 = from the west)
)
# Wind speed: ALWAYS merge with the directional blend. The default merge shows seams.
schedule = client.run_area(request, polygon, buildings=buildings, vegetation=trees)
known = {}                                   # job states, reused between checks
while not client.check_area_state(schedule, known=known).is_complete:
    time.sleep(1)
result = client.merge_area_jobs(schedule, strategy="directional_blend",
                                wind_direction_deg=request.wind_direction)
speed = result.physical_grid()          # m/s, NaN = no value
```

## Parameters

| Field | Type | Note |
|---|---|---|
| `wind_speed` | float | 0 or more (m/s). Rounding 3.9 to 3 shifts every cell by -23 % |
| `wind_direction` | int | Meteorological: 0 = from north, 90 = from east. Values outside 0-360 wrap. A fraction is refused |
| `latitude`, `longitude` | optional | Ignored by wind |

Wind takes buildings and trees: pass both. It reads no ground materials, no installations and no `ground_geometry` (use `terrain_alignment` for terrain), and it takes no `context_geometry` and no facade sensors.

## Tiles

Wind tiles are 512 m with a step of 256 m, so they overlap. Always merge wind speed with
`strategy="directional_blend"` (Python `merge_area_jobs`, TypeScript `mergeAreaJobs`): it
blends the overlaps along the wind direction. The default merge keeps the centre of each tile
and leaves visible seams. `run_area_and_wait` uses the default merge, so use the three steps
above for wind speed. Pedestrian wind comfort is a class map and uses the default merge.

## Pitfalls

- One snapshot only. Run several directions for a yearly picture, or use pedestrian wind comfort.
- 270 means from the west. This is easy to invert.
- Plot with a fixed scale (0 to 15 m/s, open top bin), not the grid min and max.

Read the result: [../interpretation/wind-results.md](../interpretation/wind-results.md)
