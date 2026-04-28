# Solar Radiation (solar-radiation)

Incident solar radiation per ground cell over a weather-driven time window, in W/m^2 (or cumulative energy depending on aggregation). Uses both direct-normal and diffuse-horizontal components from the weather file.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import (
    SolarRadiationModelRequest, BaseAnalysisPayload, AnalysesName,
)
from infrared_sdk.models import TimePeriod, Location

tp = TimePeriod(
    start_month=6, start_day=1, start_hour=9,
    end_month=6, end_day=30, end_hour=17,
)

weather_data = client.weather.filter_weather_data(
    identifier="your-weather-file-id",
    time_period=tp,
)

payload = SolarRadiationModelRequest.from_weatherfile_payload(
    payload=BaseAnalysisPayload(
        analysis_type=AnalysesName.solar_radiation,
    ),
    location=Location(latitude=48.1983, longitude=11.575),
    time_period=tp,
    weather_data=weather_data,
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array of solar radiation per cell aggregated over the window. `min_legend` / `max_legend` give the canonical color-scale bounds.

## Pitfalls

- Required weather arrays: `direct_normal_radiation` and `diffuse_horizontal_radiation`. The `from_weatherfile_payload` classmethod extracts both for you — don't pass them manually.
- Pass the SAME `TimePeriod` to `filter_weather_data` AND `from_weatherfile_payload`. Misalignment silently produces wrong results — the model assumes the arrays match the simulation window 1:1.
- If you bring your own weather arrays, their length MUST equal what `filter_weather_data` returns for the same window.
- `Location` is required — drives sun position.
- This is RADIATION (W/m^2), not direct-sun DURATION. For hours sunlit use Direct Sun Hours.

## See also

- For result interpretation -> `interpretation/solar-results.md`
- For direct sun hours -> `04-direct-sun-hours.md`
- For weather file fetch -> `04-weather-data.md`
- For time periods -> `03-time-period.md`
