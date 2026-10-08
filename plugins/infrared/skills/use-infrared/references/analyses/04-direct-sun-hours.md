# Direct sun hours (`direct-sun-hours`)

The hours of direct sun that a cell gets over the time window, with shade from buildings.
It needs a time period and a location. It needs no weather array. The unit is hours.

```python
from infrared_sdk import SolarModelRequest
from infrared_sdk.analyses.types import AnalysesName
from infrared_sdk.models import TimePeriod

request = SolarModelRequest(
    analysis_type=AnalysesName.direct_sun_hours,
    latitude=48.208, longitude=16.371,
    time_period=TimePeriod(start_month=6, start_day=1, start_hour=6,   # daylight only
                           end_month=6, end_day=30, end_hour=20),
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
hours = result.physical_grid()
```

## What the number is

The sum runs over months x days x hours of your window (a cascade), not over a continuous range.
June, days 1 to 30, 11:00 to 14:00 sums about 120 hours on open ground. It is astronomical:
clouds are not subtracted.

For a number that is easy to read, divide by the number of days: `hours / days_in_window` gives hours per day.
Always normalise before you compare two different windows.

## Keep the window inside daylight

On the ground grid, a below-horizon sun counts as a horizontal ray, and that ray escapes any open site.
Night hours then count as sun. A 24-hour window reads 24.0 h on open ground.

- Keep `start_hour` and `end_hour` between sunrise and sunset for your latitude and month.
  Central Europe in June: 06 to 20. In December: about 09 to 15.
- The smell: `grid.max()` equals the number of hours in the window, and the window has night hours.
- Daylight availability is not affected. Facade and roof runs are mostly not affected.

## Pitfalls

- A low sun on a multi-tile area clips long shadows at the tile edge: a tower farther than 128 m
  past a tile gives no shade in 1.0. Use `estimate_sun_context_loss(polygon, lat, lon, time_period)`
  (from `infrared_sdk`) to score the risk before you run. Avoid dawn and dusk hours in winter.
- Do not compare raw hour grids of different windows.
- A high summer value can be a heat-stress driver and not an amenity.

Read the result: [../interpretation/solar-results.md](../interpretation/solar-results.md)
