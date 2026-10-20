# Design variants: buildings, trees, ground, installations

Complete, copy-paste examples. Each block runs after the one before it (one site, one
courtyard). All were run with SDK 1.1.4.dev2 on 2026-10-20.
Read [run-model](run-model.md) first: base URL, payload vs call, cache.

![Installations in a street section and which models see them](images/installations-section.svg)

## 0. The site (shared setup)

A 140 x 120 m site in Vienna, UTCI on 15 July, 12 to 16 h. `utci_request(**fields)` puts each
field **on the payload**.

```python
import math
from infrared_sdk import InfraredClient, UtciModelRequest
from infrared_sdk.analyses.types import AnalysesName, UtciModelBaseRequest
from infrared_sdk.models import Location, TimePeriod

client = InfraredClient()                            # production unless INFRARED_BASE_URL is set
lon0, lat0 = 16.3700, 48.2100                       # south-west corner of the site
M_LON, M_LAT = 111320 * math.cos(math.radians(lat0)), 111320


def ll(x, y):                                       # metres from the SW corner -> [lon, lat]
    return [lon0 + x / M_LON, lat0 + y / M_LAT]


def rect_ll(x0, y0, x1, y1):                        # GeoJSON polygon in lon/lat
    return {"type": "Polygon", "coordinates": [[ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1), ll(x0, y0)]]}


def box(x0, y0, x1, y1, h):                         # closed box mesh, metres
    xy = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {"coordinates": [v for z in (0, h) for x, y in xy for v in (x, y, z)],
            "indices": [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
                        1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]}


polygon = rect_ll(0, 0, 140, 120)
tp = TimePeriod(start_month=7, start_day=15, start_hour=12, end_month=7, end_day=15, end_hour=16)
station = client.weather.get_weather_file_from_location(lat=lat0, lon=lon0)[0]
rows = client.weather.filter_weather_data(identifier=station["uuid"], time_period=tp)


def utci_request(**fields):                         # fields go ON THE PAYLOAD (installations, physics, ...)
    return UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index, **fields),
        location=Location(latitude=lat0, longitude=lon0), time_period=tp, weather_data=rows)
```

## 1. Buildings with facade and roof material

```python
# Four blocks around a 60 x 50 m courtyard (x 40-100, y 35-85).
buildings = {
    "south": box(10, 5, 130, 35, 18),
    "north": box(10, 85, 130, 115, 18),
    "west": box(10, 35, 40, 85, 16),
    "east": box(100, 35, 130, 85, 16),
}
# Facade material: one object per building. A field beats the preset.
buildings["south"]["material"] = {"version": 1, "preset": "brick"}
buildings["east"]["material"] = {"version": 1, "preset": "light-paint", "rho-solar": 0.7}
# Roof material: "roof-material" (else the roof takes "material").
buildings["north"]["roof-material"] = {"version": 1, "preset": "green-roof-extensive"}
```

- Facade presets: `default`, `masonry`, `brick`, `concrete`, `light-paint`, `dark-paint`,
  `metal`, `wood`, `glass`, `green-climbing`, `green-modular`, `green-living-wall`, `pv`,
  `shade-sail-light`, `shade-sail-dark`, `shade-mesh`. Roof-only presets: `light-roof`,
  `green-roof-extensive`, `green-roof-intensive`.
- Fields (kebab-case, also in TypeScript): `rho-solar`, `emissivity`, `transmittance`
  (installations only), `pv-efficiency` (0 to 0.4). An unknown preset becomes `default`
  (`MATERIAL_PRESET_UNKNOWN`); an invalid field is removed (`MATERIAL_FIELD_INVALID`).
- UTCI reads the facade `material`. It reads `roof-material` only with `physics="advanced"`;
  with `standard` you get `ROOF_MATERIAL_ADVANCED_ONLY`. A roof has no effect at street level.
- A light facade makes the street **warmer** in the afternoon in reality (reflected sun on
  people). The model does not yet add that reflected sun, so it shows only the cooler wall,
  and today there is **no warning**. Do not offer light paint as a cooling measure.

## 2. Trees

```python
# Trees: {id: GeoJSON Feature with a Point in [lon, lat]}. Height and crown in metres.
spots = [(50, 45), (50, 75), (90, 45), (90, 75)]
trees = {
    f"tree{i}": {"type": "Feature",
                 "geometry": {"type": "Point", "coordinates": ll(x, y)},
                 "properties": {"genus": "Platanus", "height": 10, "crownDiameter": 8}}
    for i, (x, y) in enumerate(spots)
}
```

- `genus` sets the crown shape; an unknown genus is a broadleaf tree. No `height` and no
  `crownDiameter` gives 6 m and 4 m, with no warning: always give both.
- A tree is a Point in `[lon, lat]`, not metres.

## 3. Ground materials, with irrigated grass

```python
# Ground: one FeatureCollection per layer, lon/lat. Layers must NOT overlap:
# cut the asphalt around the lawn, else the result can ignore the lawn with no warning.
def layer(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def feature(geometry, **props):
    return {"type": "Feature", "geometry": geometry, "properties": props}


ground = {
    "asphalt": layer(feature(rect_ll(0, 0, 140, 35)), feature(rect_ll(0, 85, 140, 120)),
                     feature(rect_ll(0, 35, 40, 85)), feature(rect_ll(100, 35, 140, 85))),
    "concrete": layer(feature(rect_ll(40, 35, 100, 55))),                      # paved half
    "vegetation": layer(feature(rect_ll(40, 55, 100, 85), irrigated=True)),    # watered lawn
}
```

- Layers: `asphalt`, `concrete`, `soil`, `vegetation`, `water`. An unknown layer name is an
  error. Ground with no polygon is `concrete`.
- Properties: `albedo` (0 to 1), `dt-max` (0 to 50 K, UTCI/TCS), `irrigated: true` (soil stays
  at field capacity) or `soil-moisture` (0 to 1). UTCI, TCS and solar radiation read them.
- **Do not overlap layers.** One tester put asphalt over the whole site and an irrigated lawn on
  top: the result was bit-identical to "no lawn", with no warning. Cut holes.

## 4. Installations: sail, PV canopy, green layer, louvres

Installations are thin, two-sided pieces: `{id: {coordinates, indices, material}}` in metres,
the frame of the buildings. They shade; they get no sensors. Give **both faces** (the second
triangle pair below), and give each piece its own height (it is not put on the terrain).

```python
def quad(corners, material):                         # one flat piece, BOTH faces
    return {"coordinates": [v for p in corners for v in p],
            "indices": [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2], "material": material}


def flat(x0, y0, x1, y1, z, material):              # horizontal piece at height z
    return quad([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], material)


def wall(x0, y0, x1, y1, z0, z1, material):         # vertical piece from (x0,y0) to (x1,y1)
    return quad([(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)], material)


installations = {
    # Shade sail: lets 20 % of the light through.
    "sail": flat(45, 40, 65, 55, 5, {"version": 1, "preset": "shade-sail-light", "transmittance": 0.2}),
    # PV canopy: opaque, 20 % module efficiency.
    "pv-canopy": flat(70, 40, 95, 55, 4.5, {"version": 1, "preset": "pv", "pv-efficiency": 0.20}),
    # Green climbing layer 1 m in front of the west wall of the "east" block (x = 100).
    "green-screen": wall(99, 40, 99, 80, 0, 8, {"version": 1, "preset": "green-climbing"}),
}
# Louvres: 6 opaque vertical fins, 0.6 m deep, every 1.5 m, in front of the "north" block.
for i in range(6):
    x = 50 + 1.5 * i
    installations[f"fin{i}"] = wall(x, 84, x, 83.4, 0, 10, {"version": 1, "preset": "metal"})

request = utci_request(installations=installations)      # on the payload, not a run_area kwarg
result = client.run_area_and_wait(request, polygon, buildings=buildings,
                                  vegetation=trees, ground_materials=ground)
print(result.warnings)                                  # e.g. INSTALLATIONS_WIND_NOT_MODELLED
```

| Piece | Preset and fields | Effect (UTCI) |
|---|---|---|
| Shade sail | `shade-sail-light` or `shade-sail-dark`, `transmittance` 0 to 1 | Shade; light passes by `transmittance` |
| Shade mesh | `shade-mesh`, `transmittance` | As a sail |
| PV canopy | `pv`, `pv-efficiency` 0 to 0.4 | Opaque shade; `pv_yield` in solar radiation |
| Green layer in front of a facade | `green-climbing`, `green-modular`, `green-living-wall` | Shade on the wall and the street |
| Louvres, fins | `metal`, `wood`, `concrete` (opaque) | Shade |
| Glass canopy | `glass` + `transmittance` | **Coming**, see below |

Result in this example (courtyard 60 x 50 m, against the same site without installations):
mean UTCI -1.0 K, best cell -4.9 K, area above 32 C from 650 m2 to 200 m2. The server warns
`INSTALLATIONS_WIND_NOT_MODELLED`: the wind under a sail is the wind of the weather file.

### Glass canopy (coming)

The glass presets for installations (`glass`, `glass-reflective`) wait for a server deploy.
The server accepts `glass` with `transmittance` today (run on 2026-10-20), but the values can
change. Say "preliminary" when you report a glass result. `glass-reflective` is not a preset
yet: it becomes `default`, with `MATERIAL_PRESET_UNKNOWN`.

```python
glass = {"glass-canopy": flat(45, 60, 65, 75, 4, {"version": 1, "preset": "glass", "transmittance": 0.6})}
request = utci_request(installations={**installations, **glass})
```

## 5. PV yield of a canopy (solar radiation)

`BaseAnalysisPayload` takes no `installations` and no `analysis_surfaces`. Build the request,
then add them with `model_copy`.

```python
from infrared_sdk.analyses.types import BaseAnalysisPayload, SolarRadiationModelRequest

year = TimePeriod(start_month=1, start_day=1, start_hour=0, end_month=12, end_day=31, end_hour=23)
year_rows = client.weather.filter_weather_data(identifier=station["uuid"], time_period=year)
solar = SolarRadiationModelRequest.from_weatherfile_payload(
    payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
    location=Location(latitude=lat0, longitude=lon0), time_period=year, weather_data=year_rows)
# BaseAnalysisPayload takes no installations or surfaces: add them to the built request.
solar = solar.model_copy(update={"installations": {"pv-canopy": installations["pv-canopy"]},
                                 "analysis_surfaces": "all", "surface_grid_size": 2.0})
solar_result = client.run_area_and_wait(solar, polygon, buildings=buildings)
for pid, e in solar_result.pv_yield["entries"].items():   # one entry per "pv" piece
    print(pid, e["front"]["mean-irradiation"], "kWh/m2 on top,", e["yield-kwh"], "kWh (front + back)")
```

`yield-kwh` adds the front and the back (bifacial). It is gross: no inverter or temperature
loss. For net energy use the PV recipe in [recipes/compare-and-derive](recipes/compare-and-derive.md).

## 6. The same in TypeScript

```ts
import { InfraredClient, initializeCore, areaGridValuesF32, type AreaResult } from "@infrared-city/infrared-sdk";

await initializeCore();
const client = new InfraredClient({
  apiKey: process.env.INFRARED_API_KEY,
});
const [lon0, lat0] = [16.37, 48.21];
const ll = (x: number, y: number) => [lon0 + x / (111320 * Math.cos(lat0 * Math.PI / 180)), lat0 + y / 111320];
const polygon = { type: "Polygon", coordinates: [[ll(0, 0), ll(140, 0), ll(140, 120), ll(0, 120), ll(0, 0)]] };
const box = (x0: number, y0: number, x1: number, y1: number, h: number) => ({
  coordinates: [0, h].flatMap((z) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].flatMap(([x, y]) => [x, y, z])),
  indices: [0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7],
});
const flat = (x0: number, y0: number, x1: number, y1: number, z: number, material: object) => ({
  coordinates: [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z],
  indices: [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2], material,          // both faces
});
const buildings = { south: { ...box(10, 5, 130, 35, 18), material: { version: 1, preset: "brick" } },
                    north: box(10, 85, 130, 115, 18) };
const installations = {                                              // kebab-case keys in material
  sail: flat(45, 40, 65, 55, 5, { version: 1, preset: "shade-sail-light", transmittance: 0.2 }),
  pv: flat(70, 40, 95, 55, 4.5, { version: 1, preset: "pv", "pv-efficiency": 0.2 }),
};
const [station] = await client.weather.getWeatherFileFromLocation(lat0, lon0, 100);
const period = { start: { month: 7, day: 15, hour: 12 }, end: { month: 7, day: 15, hour: 16 } };
const weatherData = await client.weather.filterWeatherData(station.uuid, { period });
const request = { analysisType: "thermal-comfort-index", latitude: lat0, longitude: lon0,
                  dateFilters: { period }, weatherData, installations };   // installations: in the REQUEST
const result = await client.runAreaAndWait(request as any, polygon, { buildings });  // buildings: in the options
const grid = areaGridValuesF32(result as AreaResult);
console.log(grid.length, (result as any).warnings);
```

`installations` is a field of the request; `buildings` goes in the options. Material keys are
kebab-case (`pv-efficiency`): camelCase `pvEfficiency` is removed with `MATERIAL_FIELD_INVALID`.

## Settings with no effect (check before you report)

| You set | What happens |
|---|---|
| `transmittance` for sun hours or SVF | Removed: every piece is opaque there |
| `roof-material` with `physics="standard"` | Ignored, `ROOF_MATERIAL_ADVANCED_ONLY` |
| `physics="advanced"` in a daytime window | Almost no change at street level |
| A tree with no `height` / `crownDiameter` | 6 m / 4 m, no warning |
| Lawn on top of an asphalt layer | Can be ignored, no warning |
| `light-paint` facade | Cooler wall only; no reflected-sun penalty, no warning |
| Any `installations` for wind or PWC | Not read |
| The same request body twice in 24 h | Cache hit, identical result |
