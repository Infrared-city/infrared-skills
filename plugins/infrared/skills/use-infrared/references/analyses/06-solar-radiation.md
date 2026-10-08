# Solar radiation (`solar-radiation`)

The solar energy that reaches each cell over the time window, in kWh/m2.
It uses direct and diffuse radiation from a weather file.

```python
from infrared_sdk import SolarRadiationModelRequest
from infrared_sdk.analyses.types import AnalysesName, BaseAnalysisPayload
from infrared_sdk.models import Location, TimePeriod

tp = TimePeriod(start_month=6, start_day=1, start_hour=9,
                end_month=6, end_day=30, end_hour=17)
rows = client.weather.filter_weather_data(identifier=station_uuid, time_period=tp)

request = SolarRadiationModelRequest.from_weatherfile_payload(
    payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
    location=Location(latitude=48.208, longitude=16.371),
    time_period=tp, weather_data=rows,
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
energy = result.physical_grid()         # kWh/m2 over the window
```

Weather setup: [../python/weather-and-time.md](../python/weather-and-time.md).

## Pitfalls

- Use the same `TimePeriod` for the weather and the request.
- It is energy (kWh/m2), not power (W/m2) and not hours of sun.
- The season matters: 60 kWh/m2 in January is normal. In July it signals shade.
- Facades and roofs: set `analysis_surfaces`. The class builder has no pass-through for it,
  so build the request directly with `extract_weather_fields(rows, ["diffuseHorizontalRadiation", "directNormalRadiation"])`
  and the facade fields together
  ([../python/surfaces-and-sensors.md](../python/surfaces-and-sensors.md)).
- Shade from objects farther than 128 m past a tile is missing in 1.0. See direct sun hours.
- Leaf-off trees: from November to March (north of 23.5 N) the trees let more sun through.

Read the result: [../interpretation/solar-results.md](../interpretation/solar-results.md)
