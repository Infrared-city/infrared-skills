# Thermal comfort index (`thermal-comfort-index`, UTCI)

The felt outdoor temperature in degrees C at about 1.5 m, from air temperature, humidity, wind
and radiation. The mean radiant temperature is computed inside the model from your geometry.

```python
from infrared_sdk import UtciModelRequest
from infrared_sdk.analyses.types import AnalysesName, UtciModelBaseRequest
from infrared_sdk.models import Location, TimePeriod

tp = TimePeriod(start_month=7, start_day=15, start_hour=12,
                end_month=7, end_day=15, end_hour=16)
rows = client.weather.filter_weather_data(identifier=station_uuid, time_period=tp)

request = UtciModelRequest.from_weatherfile_payload(
    payload=UtciModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_index,
        # optional comfort materials: wall_albedo=0.4, ground_albedo=0.2, canopy_transmissivity=0.03, ...
    ),
    location=Location(latitude=48.208, longitude=16.371),
    time_period=tp, weather_data=rows,
)
result = client.run_area_and_wait(request, polygon,
                                  buildings=buildings, vegetation=trees, ground_materials=ground)
utci = result.physical_grid()           # degrees C, NaN = no value
```

## Parameters

- `Location` is required. Weather: 7 columns, picked by `from_weatherfile_payload`. Do not pass an MRT array.
- Comfort materials (UTCI and TCS only): `wall_albedo`, `wall_absorptivity`, `canopy_transmissivity`,
  `ground_albedo`, `ground_dt_max`. The first match wins: entry of one building or tree, then the
  request field, then the built-in value.
- A winter window (Dec to Feb) is one `TimePeriod`.
- Trees and ground materials change the result a lot. Pass them when you have them.
- The default model has a wall afterglow of about 3 hours and a ground lag of about 43 minutes.
  The air temperature is the weather file value.
- Rain (mm/h) comes from the weather file. The SDK also sends `soil-moisture-init`, the wet-ground
  start state, from the rain of the 336 hours before the window. This holds for an EPW and for
  catalog weather. One missing rain hour inside the window drops the rain and the start state, with a
  warning. A gap in the 14 days before drops only the start state, with a warning. Own rain or own
  `soil_moisture_init`: the SDK does not compute it. `include_precipitation=False` turns rain off.
- Facade `material` per building (optional): `{"version": 1, "preset": "brick"}` on the entry in
  `buildings`. See [../byo-inputs.md](../byo-inputs.md). The `standard` model reads it.
- `physics`: leave it unset for `standard`. `"advanced"` gives the same results today. A retired
  name (`v1`, `detail`) runs as `standard` with a warning.
- The server and the SDK warn about an input that they ignore or change. Read
  `result.warnings` ([../python/errors-and-retries.md](../python/errors-and-retries.md)).
- The stored type of the grid can change. Always read it with `physical_grid()`.
- No facade sensors and no `context_geometry` here. Terrain (`ground_geometry`) works.

## Pitfalls

- The grid is one aggregate over the window. It is not a single hour and not an annual mean.
- Material changes the value strongly: sunny asphalt and shaded grass can differ by 10 to 15 C
  three metres apart. Do not average across material classes.
- Do not call night values validated.
- A light facade shows only its cooler wall today. The standard model does not yet add the shortwave
  that the wall reflects, and a warning says so.
- For the share of time in comfort, heat stress or cold stress, use the statistics analysis.

Read the result: [../interpretation/thermal-results.md](../interpretation/thermal-results.md)
