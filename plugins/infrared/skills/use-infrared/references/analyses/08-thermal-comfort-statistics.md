# Thermal Comfort Statistics (thermal-comfort-statistics)

Per-cell aggregated thermal-comfort statistic over the requested window — fraction of hours falling in a chosen class. Subtype is selected per call: `thermal_comfort`, `heat_stress`, or `cold_stress`.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import TcsModelBaseRequest, TcsModelRequest, TcsSubtype, AnalysesName
from infrared_sdk.models import TimePeriod, Location

tp = TimePeriod(
    start_month=6, start_day=1, start_hour=9,
    end_month=8, end_day=31, end_hour=17,
)

weather_data = client.weather.filter_weather_data(
    identifier="your-weather-file-id",
    time_period=tp,
)

payload = TcsModelRequest.from_weatherfile_payload(
    payload=TcsModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_statistics,
        subtype=TcsSubtype.heat_stress,
    ),
    location=Location(latitude=48.1983, longitude=11.575),
    time_period=tp,
    weather_data=weather_data,
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array — fraction of hours in the selected class for each cell. `min_legend` / `max_legend` are the canonical bounds. The semantic meaning depends on the chosen `subtype`.

## Pitfalls

- Three subtypes via `TcsSubtype`: `thermal_comfort`, `heat_stress`, `cold_stress`. Subtype is per-call — to get all three, run three jobs (each gets its own `config_hash`).
- `Location` is REQUIRED — drives sun position and weather model.
- Use `from_weatherfile_payload` — it pulls all 7 weather fields automatically. MRT is computed internally; do not pass it.
- Pass the SAME `TimePeriod` to `filter_weather_data` and `from_weatherfile_payload`. Mismatch corrupts the result silently.
- For a single aggregated UTCI map (degrees C, no class binning) use Thermal Comfort Index.

## See also

- For result interpretation -> `interpretation/thermal-results.md`
- For aggregated UTCI -> `07-thermal-comfort-utci.md`
- For weather file fetch -> `04-weather-data.md`
- For time periods -> `03-time-period.md`
