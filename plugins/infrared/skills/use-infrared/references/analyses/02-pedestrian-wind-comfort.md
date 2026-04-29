# Pedestrian Wind Comfort (pedestrian-wind-comfort)

Wind comfort classification across a full weather time series using a chosen standard. Output cells are categorical comfort/safety classes per the selected criterion.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import PwcModelRequest, PwcCriteria, AnalysesName
from infrared_sdk.models import TimePeriod, extract_weather_fields

weather_data = client.weather.filter_weather_data(
    identifier="your-weather-file-id",
    time_period=TimePeriod(
        start_month=6, start_day=1, start_hour=9,
        end_month=6, end_day=30, end_hour=17,
    ),
)
# Single-month window required. Multi-month runs currently fail server-side — split into
# separate TimePeriods and run each sequentially if you need a longer period.
wind_fields = extract_weather_fields(weather_data, ["windSpeed", "windDirection"])

payload = PwcModelRequest(
    analysis_type=AnalysesName.pedestrian_wind_comfort,
    criteria=PwcCriteria.lawson_2001,
    **wind_fields,
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D categorical array — integer class indices per the selected criterion. `min_legend` / `max_legend` cover the class range used by the criterion. The interpretation file describes how indices map to comfort labels.

## Pitfalls

- Seven criteria available via `PwcCriteria`: `vdi_387`, `lawson_1970`, `lawson_2001`, `lawson_lddc`, `davenport`, `nen_8100_comfort`, `nen_8100_safety`. Pick one matching your jurisdiction or client convention.
- `wind_speed` and `wind_direction` here are LISTS of floats from a weather file — not single ints like `WindModelRequest`. Don't mix them up.
- The two arrays must have equal length and align element-wise (each pair = one hourly observation).
- Pass the same `TimePeriod` to `filter_weather_data` and reuse it; mismatched windows silently produce wrong stats.
- `nen_8100_safety` is a SAFETY criterion (storm risk), not a comfort one — different question, different output.

## See also

- For result interpretation -> `interpretation/wind-results.md`
- For raw wind field -> `01-wind-speed.md`
- For weather file fetch -> `04-weather-data.md`
- For time periods -> `03-time-period.md`
