# Python: rooms (daylight factor and energy balance)

Two models run on one building and not on an area. Both are Beta.
They do not use `run_area_and_wait`. Use `client.analyses.run_and_wait(request)`.

- **Daylight factor**: the daylight at points in a room, in %, under a CIE overcast sky.
  It needs no weather and no time.
- **Energy balance**: the monthly heating and cooling energy need of each zone.
  Keep one building whole in one request.

Docs: [Interior (Beta)](https://infrared.city/docs/sdk/1.0/sdk.md) (chapter "Interior"),
[Interior helpers](https://infrared.city/docs/sdk/1.0/python/interior/index.md),
[Analyses](https://infrared.city/docs/sdk/1.0/python/analyses/index.md).
Details of the daylight inputs: [../analyses/10-interior-daylight-factor.md](../analyses/10-interior-daylight-factor.md).

## The one trap: nested entities

Interior models take **nested** entities: `{"geometry": {"payload": {"coordinates", "indices"}}}`.
The flat mesh of the outdoor models is not an error here. The server reads it as "no geometry",
skips it, and returns a confident wrong answer. Always wrap meshes with `to_interior_entity`
(one mesh) or `interior_entities` (a dict of meshes).

## Daylight factor: a room

```python
import numpy as np
from infrared_sdk import InfraredClient, interior_entities, to_interior_entity
from infrared_sdk.analyses.types import AnalysesName, DaylightFactorModelRequest

client = InfraredClient()

def quad(p0, p1, p2, p3):
    """One flat rectangle as a mesh. Corners in order around the rectangle."""
    return {"coordinates": [c for p in (p0, p1, p2, p3) for c in p],
            "indices": [0, 1, 2, 0, 2, 3]}

W, D, H = 6.0, 6.0, 3.0       # a 6 m x 6 m room, 3 m high. Metres, nothing converts them.

# Enclose the room. A missing wall is a hole that the sky pours through.
barriers = {
    "floor":   to_interior_entity(quad((0, 0, 0), (W, 0, 0), (W, D, 0), (0, D, 0)), category="floor"),
    "ceiling": to_interior_entity(quad((0, 0, H), (W, 0, H), (W, D, H), (0, D, H)), category="floor"),
    "wall-s":  to_interior_entity(quad((0, 0, 0), (W, 0, 0), (W, 0, H), (0, 0, H)), category="wall"),
    "wall-n":  to_interior_entity(quad((0, D, 0), (W, D, 0), (W, D, H), (0, D, H)), category="wall"),
    "wall-w":  to_interior_entity(quad((0, 0, 0), (0, D, 0), (0, D, H), (0, 0, H)), category="wall"),
    "wall-e":  to_interior_entity(quad((W, 0, 0), (W, D, 0), (W, D, H), (W, 0, H)), category="wall"),
}

# A window is an opening, not a hole. Keep the wall. Put the opening in the wall plane,
# 1 cm inside. opening_factor is the light transmittance, 0 to 1.
windows = {"window-s": to_interior_entity(
    quad((2, 0.01, 0.9), (4, 0.01, 0.9), (4, 0.01, 2.9), (2, 0.01, 2.9)),
    category="window", opening_factor=0.7)}

# Sensors: a regular grid on the work plane (0.8 m), at cell centres.
# Cover the whole floor with one pitch. Keep every point inside the room:
# stray points change the result of ALL points.
pitch = 0.5
sensors = [[x * pitch + pitch / 2, y * pitch + pitch / 2, 0.8]
           for x in range(int(W / pitch)) for y in range(int(D / pitch))]

request = DaylightFactorModelRequest(
    analysis_type=AnalysesName.daylight_factor,
    barriers=barriers, openings=windows, sensor_points=sensors,
    window_area=4.0,          # the real glass area in m2; it feeds the reflected-light term
)

parts = client.analyses.preview_parts(request)       # free: parts, sensors, cost
print(parts.part_count, "part(s)", parts.estimated_cost_tokens, "tokens")

result = client.analyses.run_and_wait(request)       # a DaylightFactorResult
df = np.asarray(result.columns.values)               # one value (%) per sensor
print(df.shape, float(df.min()), float(df.max()))
assert len(set(df.tolist())) > 1, "uniform field: the geometry did not reach the model"
```

Reading the field: below about 1 % is dim, 1.5 to 4 % is normal for a daylit room,
above 4 to 5 % is generous. Values must fall off away from the window.
A uniform non-zero field means something did not reach the model.

Neighbours cast shade through `context_geometry=interior_entities(neighbour_meshes)`.
Without them the room reads too bright.

## Large floors run in parts

The SDK counts sensors and packs floors into parts of about 300,000 points. Each part is one billed job.
If one part fails, `PartsRunError` carries no result. Send only the failed parts again:

```python
from infrared_sdk import PartsRunError

try:
    result = client.analyses.run_and_wait(request)
except PartsRunError as exc:
    result = client.analyses.run_and_wait(request, retry_from=exc.schedule)
```

## Energy balance: a zone

Energy balance needs closed volumes (`spatial_volumes`, category `"space"`), the walls and every slab
(the roof too), and one year of hourly weather. The default `solar_model` is `"legacy-flat"`:
two weather series and no shade. `"irradiance"` uses the shade geometry and needs latitude,
longitude and four series.

```python
from infrared_sdk import EnergyBalanceModelRequest
from infrared_sdk.models import TimePeriod

lat, lon = 48.208, 16.371
stations = client.weather.get_weather_file_from_location(lat=lat, lon=lon)
year = TimePeriod(start_month=1, start_day=1, start_hour=0,
                  end_month=12, end_day=31, end_hour=23)
weather = client.weather.filter_weather_data(identifier=stations[0]["uuid"], time_period=year)
# With your own file use: weather = parse_epw("site.epw")

def box(w, d, h):
    """A closed box as a mesh: 8 corners, 12 triangles."""
    xy = [(0, 0), (w, 0), (w, d), (0, d)]
    coords = [c for z in (0, h) for x, y in xy for c in (x, y, z)]
    idx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
    return {"coordinates": coords, "indices": idx}

zones = interior_entities({"room": box(W, D, H)}, category="space")

eb = EnergyBalanceModelRequest.from_weather(
    weather, solar_model="irradiance", latitude=lat, longitude=lon,
    spatial_volumes=zones, barriers=barriers, openings=windows,
)
energy = client.analyses.run_and_wait(eb)           # one job: a dict
zone = energy["output"][0]
print(zone["zone_name"], zone["annual"]["EUI_heat"], "kWh/m2 a heating need")
print(len(zone["monthly"]), "monthly values")
```

The result is the energy **need** in kWh/m2 a (`EUI_heat`, `EUI_cool`) and 12 monthly values.
It is not delivered energy: no boiler, heat pump or chiller efficiency applies.
U-values, glazing, set-points, gains, infiltration and thermal mass are optional
(`energy_settings=EnergySettings(...)`, `operation=Operation.intermittent(...)`).
The guide chapter "Configuration and limits" lists all names and defaults.
