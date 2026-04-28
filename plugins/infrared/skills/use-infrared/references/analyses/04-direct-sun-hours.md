# Direct Sun Hours (direct-sun-hours)

Cumulative number of hours each ground cell receives direct sunlight over the requested time window, accounting for building shadowing. Geometry + sun-position only — no weather file needed.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import SolarModelRequest, AnalysesName
from infrared_sdk.models import TimePeriod

payload = SolarModelRequest(
    analysis_type=AnalysesName.direct_sun_hours,
    latitude=48.1983,
    longitude=11.575,
    time_period=TimePeriod(
        start_month=6, start_day=1, start_hour=9,
        end_month=6, end_day=30, end_hour=17,
    ),
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array of cumulative direct-sun hours for the window. `min_legend` / `max_legend` give canonical plot bounds — most cells cluster near the upper bound, so grid-derived bounds wash out the heatmap.

## Pitfalls

- Request class is `SolarModelRequest`, NOT `SolarRadiationModelRequest`. Identical signature to Daylight Availability — only the `analysis_type` enum changes.
- `latitude` / `longitude` are REQUIRED — they drive sun position.
- The result is HOURS over the window, not a normalised fraction. Compare runs by matching the `time_period` exactly.
- For radiation in W/m^2 (intensity, not duration) use Solar Radiation instead.
- Always plot with `min_legend` / `max_legend`, not derived from grid stats.

## See also

- For result interpretation -> `interpretation/solar-results.md`
- For daylight availability -> `03-daylight-availability.md`
- For radiation in W/m^2 -> `06-solar-radiation.md`
- For time periods -> `03-time-period.md`
