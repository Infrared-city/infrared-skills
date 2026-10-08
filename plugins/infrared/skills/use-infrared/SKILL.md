---
name: use-infrared
description: Run Infrared urban microclimate simulations (wind, pedestrian wind comfort, solar radiation, sun hours, daylight, sky view factor, UTCI thermal comfort, comfort statistics, interior daylight factor and energy balance) from Python (`pip install infrared-sdk`) or TypeScript (`npm install @infrared-city/infrared-sdk-ts`), in scripts, web apps, Grasshopper or Rhino, and read the results. Also covers files in and out of the Infrared platform. Use when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / Lawson / PWC, solar / daylight / sun hours / SVF, UTCI / thermal comfort, facade or roof analysis, a map or 3D app that shows results, Grasshopper or Rhino with Infrared, or uploads, imports or exports GeoJSON, OBJ, EPW, GeoTIFF or ZIP.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(npm:*), Bash(node:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

Do not write SDK calls from memory. Read the page for your language, or fetch the docs (below).

## What do you want to build?

| Goal | SDK | Go to |
|---|---|---|
| Grasshopper or Rhino component | Python in Rhino 8 | [grasshopper](references/recipes/grasshopper.md), [geometry and drawing](references/recipes/grasshopper-geometry-and-drawing.md), [pitfalls](references/recipes/grasshopper-pitfalls.md) |
| Analysis, study or notebook for yourself | Python | [python/quickstart](references/python/quickstart.md), `cookbook/notebooks/00_quickstart.ipynb` |
| Web app for yourself (browser, map, 3D facades) | TypeScript in the browser | [typescript/quickstart](references/typescript/quickstart.md), [map-grid](references/typescript/map-grid.md), [facades-3d](references/typescript/facades-3d.md), `cookbook/apps/map-grid`, `cookbook/apps/facades-3d` |
| Web app for many users (sign-in, secret key) | TypeScript front end + Cloudflare Worker proxy | [cloudflare-proxy](references/typescript/cloudflare-proxy.md), `cookbook/apps/cloudflare-proxy`, [persistence-and-users](references/recipes/persistence-and-users.md) |
| High-throughput backend (many sites, queue, cache) | Python service | [python-fastapi-app](references/recipes/python-fastapi-app.md), `cookbook/apps/python-fastapi` |
| SketchUp or other CAD plugin | Ruby or Python, same API | [sketchup-plugin](references/recipes/sketchup-plugin.md) |
| Upload your own data to the platform (no code) | none | [platform-byo-upload](references/platform-byo-upload.md) |

Every row: read [building-fast-apps](references/building-fast-apps.md) for speed.
## Concepts and guidance

### What each analysis answers

| Question | Analysis (unit) | Page |
|---|---|---|
| How fast is the wind? Is it comfortable for people? | `wind-speed` (m/s), `pedestrian-wind-comfort` (class) | [01](references/analyses/01-wind-speed.md), [02](references/analyses/02-pedestrian-wind-comfort.md) |
| How much daylight? How many hours of direct sun? | `daylight-availability` (% of window), `direct-sun-hours` (h) | [03](references/analyses/03-daylight-availability.md), [04](references/analyses/04-direct-sun-hours.md) |
| How open is the sky? How much solar energy? | `sky-view-factors` (%), `solar-radiation` (kWh/m2) | [05](references/analyses/05-sky-view-factors.md), [06](references/analyses/06-solar-radiation.md) |
| What does it feel like outside? For how long is it comfortable, hot, cold? | `thermal-comfort-index` UTCI (degrees C), `thermal-comfort-statistics` (% of window) | [07](references/analyses/07-thermal-comfort-utci.md), [08](references/analyses/08-thermal-comfort-statistics.md) |
| Daylight in a room? Heating and cooling need? (Beta) | `daylight-factor` (%), `energy-balance` (kWh/m2 a) | [10](references/analyses/10-interior-daylight-factor.md), [12](references/analyses/12-interior-energy-balance.md) |

Reading results: [interpretation/](references/interpretation/grid-conventions.md).

### Inputs: your data first

- Your own buildings, trees and ground are the main path ([byo-inputs](references/byo-inputs.md)). Ask what the user has
  (BIM, Rhino, IFC, GeoJSON). Public data (Overture, city data) is a fallback. Its source and heights vary: say so.
- Frames: the area is a lon/lat polygon (`[lon, lat]`). Meshes are metres from the polygon's south-west corner, z up
  ([crs](references/geospatial-crs.md)). Sensors: ground, facades and roofs, or own points ([09](references/analyses/09-facade-terrain.md)).
  Terrain and far shade (128 m reach in 1.0): [11](references/analyses/11-terrain-and-context.md). Time: [03](references/03-time-period.md).

### Area runs and results

The SDK cuts the area into 512 m tiles, uploads the geometry once, sends one job for each tile and
analysis, polls, and merges. A failed tile raises (no map with holes). A resend never bills twice.
- Always read values with the helper: `result.physical_grid()` (Python), `areaGridValuesF32(result)` (TypeScript).
  Never read the raw array: its stored type differs by analysis. NaN means no value. A facade at 0.0 is real.
- Row 0 is south. Place an overlay with `result.bounds`. Use a fixed colour scale for each analysis:
  [grid-conventions](references/interpretation/grid-conventions.md), [rendering-results-well](references/recipes/rendering-results-well.md).
- Cost: preview first (free, local). Price from `would_bill_jobs`: one job is one tile for one analysis.

## Python

```bash
pip install infrared-sdk    # "[geodata]" adds public buildings, trees, ground. Set INFRARED_API_KEY; never put it in code.
```

```python
from infrared_sdk import InfraredClient, SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

lon, lat = 16.371, 48.208                                  # [lon, lat], WGS84
polygon = {"type": "Polygon", "coordinates": [[[lon, lat], [lon + 0.004, lat],
           [lon + 0.004, lat + 0.003], [lon, lat + 0.003], [lon, lat]]]}
# Your own meshes: {id: {"coordinates": [x, y, z, ...], "indices": [...]}} in metres from the
# polygon's south-west corner. See references/python/own-data.md. Stand-in: one 20 x 20 x 30 m box.
buildings = my_buildings

client = InfraredClient()                                  # reads INFRARED_API_KEY
request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)
print(client.preview_area(polygon, payload=request).would_bill_jobs, "job(s)")   # free
result = client.run_area_and_wait(request, polygon, buildings=buildings)
grid = result.physical_grid()                              # real values, NaN = no value
```

More in `references/python/`: [own-data](references/python/own-data.md), [weather-and-time](references/python/weather-and-time.md),
[surfaces-and-sensors](references/python/surfaces-and-sensors.md), [interior](references/python/interior.md),
[errors-and-retries](references/python/errors-and-retries.md).

## TypeScript

```bash
npm install @infrared-city/infrared-sdk-ts   # Node 18+, from npmjs.org, no token
```

An `.npmrc` that maps `@infrared-city` to GitHub Packages keeps you on an old version: remove that line.
```ts
import { InfraredClient, initializeCore, areaGridValuesF32, type AreaResult } from "@infrared-city/infrared-sdk-ts";

await initializeCore();                                    // once, before any area run
const client = new InfraredClient({ apiKey: process.env.INFRARED_API_KEY });
const polygon = { type: "Polygon", coordinates: [[[16.371, 48.208], [16.375, 48.208], [16.375, 48.211], [16.371, 48.211], [16.371, 48.208]]] };
const buildings = { tower: { coordinates, indices } };     // your meshes in metres (see references/typescript/quickstart.md)

const plan = await client.previewAreaBatches({ analysisType: "sky-view-factors" }, polygon, { buildings });
console.log(plan.plannedJobCount);                         // free
const result = await client.runAreaAndWait({ analysisType: "sky-view-factors" }, polygon, { buildings });
const grid = areaGridValuesF32(result as AreaResult);      // Float32Array, NaN = no value
```
TypeScript pages and apps: see the table above.

Ground grid row 0 is south: flip the rows for an image. Facades and roofs: `surfaceRenderBuffers(columns)`.

## Docs for agents

- Guide: <https://infrared.city/docs/sdk/>. The whole guide as one file: <https://infrared.city/docs/sdk/sdk.md>
- Page index: <https://infrared.city/docs/sdk/llms.txt> and <https://infrared.city/docs/sdk/1.0/llms.txt>
- Each page is Markdown too: add `index.md` (for example <https://infrared.city/docs/sdk/1.0/python/sdk/index.md>)

## Other topics
- Cookbook notebooks in [`cookbook/`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook): `00_quickstart`,
  `01_design_variants`, `02_summer_heat`, `03_wind_comfort`, `04_solar_facades_3d`, `05_sensors_3d`,
  `06_interior`, `07_terrain_and_context`, `08_scale_and_cost`.
- Platform files: [upload](references/platform-byo-upload.md), [export](references/platform-export.md) (ask: SDK data or platform files?).
- [Facade results on your model](references/surface-results-integration.md), [jobs](references/async-and-jobs.md), [recipes](references/recipes/hackathon-tools.md).

## Silent traps
None of these raise an error.
- Lat and lon swapped, Y-up, centimetres, origin not at the south-west corner, an open mesh.
- Weather left out of a thermal or solar request: billed, then fails. Use `from_weatherfile_payload`.
- No `ground_geometry` means a flat plane. Terrain in `buildings` gives a shattered mesh.
- Night hours in a `direct-sun-hours` window count as sun. Shade beyond 128 m past a tile is missing.
- Interior entities must be nested. `preview_area` without `payload=` prices the wind grid.
- Do not call UTCI night values validated.
End of task: read [references/reflection-and-feedback.md](references/reflection-and-feedback.md) once.
