# Daylight Availability (daylight-availability)

Fraction of the requested time window for which a ground cell receives sufficient daylight, accounting for building shadowing. No weather data needed — sun position is computed from lat/lon + time period.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import SolarModelRequest, AnalysesName
from infrared_sdk.models import TimePeriod

payload = SolarModelRequest(
    analysis_type=AnalysesName.daylight_availability,
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

`result.merged_grid` is a 2D `float` array of cumulative **hours of usable daylight** per cell over the requested `TimePeriod` (range: 0 to the period length in hours). Use `min_legend` / `max_legend` for plotting — most cells cluster near the upper bound, so deriving bounds from the grid alone produces washed-out heatmaps.

## Pitfalls

- The request class is `SolarModelRequest` (NOT `SolarRadiationModelRequest`). Same class is shared with Direct Sun Hours; only the `analysis_type` enum differs.
- `latitude` / `longitude` are REQUIRED here — they drive the solar position, unlike SVF/Wind where they are optional.
- A short `time_period` (a single day) is valid but rarely informative; pick a representative season window.
- This is daylight, not direct sun hours — for raw sunlit duration use `04-direct-sun-hours.md`.
- Always plot with `min_legend` / `max_legend`.

## See also

- For result interpretation -> `interpretation/solar-results.md`
- For direct sun hours -> `04-direct-sun-hours.md`
- For time periods -> `03-time-period.md`
