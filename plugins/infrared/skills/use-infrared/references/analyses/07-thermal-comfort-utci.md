# Thermal comfort index (`thermal-comfort-index`, UTCI)

The felt outdoor temperature in degrees C at about 1.5 m, from air temperature, humidity, wind
and radiation. The mean radiant temperature is computed inside the model from your geometry.

Use the rich path for every real result: `physics="advanced"`, your `ground_materials`, your trees
(`vegetation`) and your terrain (`ground_geometry` with `terrain_alignment="auto-align"`). The
standard tier with no materials gives about 1 K spread and flat, one-colour maps. `advanced` gives the
same grid in daylight and adds the ground and wall afterglow after sunset, at the same price.

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
        physics="advanced",                    # ground and wall afterglow after sunset
        ground_geometry=terrain,               # your terrain mesh (11-terrain-and-context.md)
        terrain_alignment="auto-align",        # seats the buildings on the terrain
        # optional comfort materials: wall_albedo=0.4, ground_albedo=0.2, canopy_transmissivity=0.03, ...
    ),
    location=Location(latitude=48.208, longitude=16.371),
    time_period=tp, weather_data=rows,
)
result = client.run_area_and_wait(request, polygon,
                                  buildings=buildings, vegetation=trees, ground_materials=ground)
utci = result.physical_grid()           # degrees C, NaN = no value
```

Minimal call (a smoke test of the plumbing, not for real results): leave out `physics`,
`ground_materials`, `vegetation` and `ground_geometry`. The map is flat. Do not show it as a result.

## Parameters

- `Location` is required. Weather: 7 columns, picked by `from_weatherfile_payload`. Do not pass an MRT array.
- Comfort materials (UTCI and TCS only): `wall_albedo`, `wall_absorptivity`, `canopy_transmissivity`,
  `ground_albedo`, `ground_dt_max`. The first match wins: entry of one building or tree, then the
  request field, then the built-in value.
- A winter window (Dec to Feb) is one `TimePeriod`.
- Trees and ground materials change the result a lot. Pass them: a run with none is not a result.
- The window may include dark hours. The `advanced` tier models the ground and wall afterglow after
  sunset: asphalt and concrete stay warm for hours, soil and grass cool fast. The standard tier
  keeps a wall afterglow of about 3 hours and a ground lag of about 43 minutes for all materials.
  Neither has memory over days. The air temperature is the weather file value.
- The stored type of the grid can change. Always read it with `physical_grid()`.
- No facade sensors and no `context_geometry` here. Terrain (`ground_geometry`) works.

## Pitfalls

- The grid is one aggregate over the window. It is not a single hour and not an annual mean.
- Material changes the value strongly: sunny asphalt and shaded grass can differ by 10 to 15 C
  three metres apart. Do not average across material classes.
- After sunset the spread between materials comes from the afterglow. Run with `physics="advanced"`,
  or the evening hours show almost no material spread.
- For the share of time in comfort, heat stress or cold stress, use the statistics analysis.

Read the result: [../interpretation/thermal-results.md](../interpretation/thermal-results.md)
