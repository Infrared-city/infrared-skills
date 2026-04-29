# Thermal Comfort Index (thermal-comfort-index)

Universal Thermal Climate Index (UTCI) per ground cell — an outdoor "feels-like" temperature in degrees C combining air temperature, humidity, wind, and radiation. Mean radiant temperature (MRT) is computed internally from the geometry and weather.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import UtciModelRequest, UtciModelBaseRequest, AnalysesName
from infrared_sdk.models import TimePeriod, Location

tp = TimePeriod(
    start_month=6, start_day=1, start_hour=9,
    end_month=6, end_day=30, end_hour=17,
)
# Single-month window required. Multi-month runs currently fail server-side — split into
# separate TimePeriods and run each sequentially if you need a longer period.

weather_data = client.weather.filter_weather_data(
    identifier="your-weather-file-id",
    time_period=tp,
)

payload = UtciModelRequest.from_weatherfile_payload(
    payload=UtciModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_index,
    ),
    location=Location(latitude=48.1983, longitude=11.575),
    time_period=tp,
    weather_data=weather_data,
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array of UTCI in degrees C aggregated over the window. `min_legend` / `max_legend` are the canonical color-scale bounds — use them for plotting.

## Pitfalls

- `Location` is REQUIRED — drives sun position and weather model.
- Use the `from_weatherfile_payload` classmethod — it pulls all 7 weather fields (DBT, RH, wind speed, the three radiation components, horizontal infrared) automatically. Don't pass them manually unless you know the schema.
- MRT is computed INTERNALLY from geometry + radiation arrays — do NOT try to pass an mrt array.
- Pass the SAME `TimePeriod` to `filter_weather_data` and `from_weatherfile_payload`. Mismatch corrupts the result silently.
- UTCI gives a single aggregated map. For per-class hour counts (% comfort / heat-stress / cold-stress) use Thermal Comfort Statistics.

## See also

- For result interpretation -> `interpretation/thermal-results.md`
- For per-class statistics -> `08-thermal-comfort-statistics.md`
- For weather file fetch -> `04-weather-data.md`
- For time periods -> `03-time-period.md`
