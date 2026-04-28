# Weather Data

Find a nearby EPW weather station, filter its hourly data by `TimePeriod`, then extract the fields each analysis payload needs.

## Lookup + filter

```python
from infrared_sdk.models import TimePeriod, extract_weather_fields

# 1. Find stations near a location (radius in km)
locations = client.weather.get_weather_file_from_location(
    lat=48.1983, lon=11.575, radius=50
)
# [{"identifier": "DEU_BY_Munich.AP.108660_TMYx.2007-2021", "name": "Munich AP", ...}, ...]

# 2. Filter hourly data by TimePeriod
weather_data = client.weather.filter_weather_data(
    identifier=locations[0]["identifier"],
    time_period=TimePeriod(
        start_month=6, start_day=1, start_hour=9,
        end_month=8, end_day=31, end_hour=17,
    ),
)
# list[WeatherDataPoint]

# 3. Extract the fields a payload needs (camelCase in -> snake_case out)
wind_fields = extract_weather_fields(weather_data, ["windSpeed", "windDirection"])
# {"wind_speed": [3.2, 4.1, ...], "wind_direction": [180, 195, ...]}
```

## Field-to-analysis map

`WeatherDataPoint` (see `infrared_sdk/models.py`) carries all EPW columns. Pass the camelCase attribute names to `extract_weather_fields`; the returned dict uses snake_case keys that match payload fields.

| Analysis              | Required fields                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------- |
| Pedestrian Wind Comfort | `windSpeed`, `windDirection`                                                                  |
| Solar Radiation       | `diffuseHorizontalRadiation`, `directNormalRadiation`                                           |
| UTCI                  | `dryBulbTemperature`, `relativeHumidity`, `windSpeed`, `diffuseHorizontalRadiation`, `directNormalRadiation` |
| Thermal Comfort Stats | same as UTCI                                                                                    |

For UTCI / TCS / Solar Radiation, prefer `<Request>.from_weatherfile_payload(...)` — it pulls the right fields automatically from the `weather_data` list.

## Pitfalls

- Pass the **same `TimePeriod`** to `filter_weather_data()` and the analysis payload, otherwise the weather arrays won't align with the simulation window and the model rejects the request.
- Field names go in as **camelCase** (`windSpeed`); they come out **snake_case** (`wind_speed`).
- `WeatherDataPoint` has `extra="ignore"` and coerces numeric strings → floats; empty / `na` / `null` cells become `None` and `extract_weather_fields` silently skips them, so output arrays for sparse fields can be shorter than the input list.
- BYO weather: array lengths must match what `filter_weather_data` would have returned for the same `TimePeriod`.
- Identifiers like `"DEU_BY_Munich.AP.108660_TMYx.2007-2021"` are opaque — always fetch them via `get_weather_file_from_location`.

## See also

- `03-time-period.md` — cascade-filter behaviour
- `analyses/pwc.md` — PWC uses wind arrays
- `analyses/utci.md` — UTCI uses the full weather bundle
