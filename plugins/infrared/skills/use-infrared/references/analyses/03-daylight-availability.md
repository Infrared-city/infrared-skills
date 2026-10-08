# Daylight availability (`daylight-availability`)

The share of the time window in which a cell gets enough daylight, with shade from buildings.
It needs a time period and a location. It needs no weather array.

```python
from infrared_sdk import SolarModelRequest
from infrared_sdk.analyses.types import AnalysesName
from infrared_sdk.models import TimePeriod

request = SolarModelRequest(
    analysis_type=AnalysesName.daylight_availability,
    latitude=48.208, longitude=16.371,        # required: they set the sun position
    time_period=TimePeriod(start_month=6, start_day=1, start_hour=9,
                           end_month=6, end_day=30, end_hour=17),
    accuracy="standard",                      # or "precision": finer rays, slower
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
daylight = result.physical_grid()             # see the unit note below
```

`SolarModelRequest` is shared with direct sun hours. Only `analysis_type` differs.

## Unit

The grid is the **percent of the window** with enough daylight (0 to 100). Judge it as a share of the window, never in lux.

## Pitfalls

- Not lux. Do not compare it with indoor light standards.
- Short windows (one day) are valid but rarely useful. Use a season.
- A year hides winter and summer differences. Pair it with direct sun hours.
- Daylight availability removes night hours itself. Direct sun hours does not.
- Facades, roofs, own sensor points and `context_geometry` work here
  ([../python/surfaces-and-sensors.md](../python/surfaces-and-sensors.md)). In a leaf-off season,
  trees let more light through.
- Do not confuse it with the daylight **factor** (an indoor overcast-sky model).

Read the result: [../interpretation/solar-results.md](../interpretation/solar-results.md)
