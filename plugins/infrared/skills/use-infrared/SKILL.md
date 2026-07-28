---
name: use-infrared
description: Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate simulations — wind, pedestrian wind comfort (PWC), solar radiation, daylight, sun hours, sky view factor (SVF), thermal comfort (UTCI), thermal comfort statistics (TCS) — and interpret results. Activate when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / PWC / Lawson, solar / daylight / sun hours / SVF, UTCI / thermal comfort, or asks to run an outdoor environmental simulation on a polygon.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

## MANDATORY: Read before writing any code

> **Do NOT write SDK calls from memory or training data.** Payload shapes, enum values, and method signatures change between SDK versions. Guessing produces silent wrong results or cryptic 422 errors.

**Before writing the first SDK code block in this conversation, in order:**

1. Read **[00-setup.md](references/00-setup.md)** — install, auth, client init, Python 3.9+ requirement
2. Identify the analysis type → read its reference file from the table in *Choosing an analysis* below
3. If the user brings their own geometry/buildings → **pick the right path first, they are different things:**
   - Data goes into **SDK calls** (in-memory payloads, your own Python) → **[byo-inputs.md](references/byo-inputs.md)**
   - Data goes into the **platform** as **files** (platform.infrared.city — "Bring your own data" at project creation, or the Data-layers panel) → **[platform-byo-upload.md](references/platform-byo-upload.md)**
   - If the user just says "get my data into Infrared" without saying which, **ask** — the file contracts are not interchangeable.
4. If async, webhooks, or multi-tile → also read **[async-and-jobs.md](references/async-and-jobs.md)**

Do not skip step 2. The analysis file is the authoritative payload shape — not your training data.

## Silently wrong — read before you trust a number

The section above is *which file to read*. This is *what will bite you anyway*. Everything below
returns a **plausible number with a 200**, not an error: nothing here raises, several are billed,
and a reviewer reading your output cannot tell. One pass and you are immune.

- **Polygon CRS is never validated** — a projected or `[lat, lon]` polygon that still lands inside `[-180,180]×[-90,90]` runs, on the wrong patch of the planet. → [geospatial-crs.md](references/geospatial-crs.md)
- **Two metre frames, and no error between them** — `buildings` / `context_geometry` / `ground_geometry` you pass to `run_area*` are **polygon-bbox-SW**; per-tile payloads and `sensor_points` are **tile-local**. Mix them and the geometry lands a tile away, silently. → [geospatial-crs.md#the-frames-end-to-end](references/geospatial-crs.md#the-frames-end-to-end)
- **`min_legend` / `max_legend` are `None` on every area run** — so the usual `... if not None else np.nanmin(grid)` guard takes the fallback *every* time and auto-scales each render to its own data. Populated on **surface** results only. → [recipes/rendering-results-well.md](references/recipes/rendering-results-well.md)
- **Masked cells are `None`, never `0`** — map to `NaN` before any mean. Separately, a surface at exactly `0.0` is real data (party walls, light wells) — 32% of facades on one Munich run. Two different things. → [surface-results-integration.md](references/surface-results-integration.md)
- **No `ground_geometry` means a flat plane at z = 0** — not an error, and the result looks entirely normal. There is no terrain client; terrain is bring-your-own, every time. → [analyses/09-facade-terrain.md](references/analyses/09-facade-terrain.md)
- **Switching `terrain_alignment` barely moves the scene mean** while rewriting individual surfaces — measured: mean +0.03 kWh/m², 44% of facades moved by more than 1. A before/after on averages passes straight through it. → [analyses/09-facade-terrain.md](references/analyses/09-facade-terrain.md)
- **Terrain is sliced per tile as of 0.5.1** — distant relief no longer shades unless you pass it as `context_geometry`. → [analyses/09-facade-terrain.md](references/analyses/09-facade-terrain.md)
- **Interior entities are nested; `ground_geometry` and `vegetation` are flat** — the wrong shape is not a server error: the entity is skipped and you get a confident field over an empty occluder. → [analyses/10-interior-daylight-factor.md](references/analyses/10-interior-daylight-factor.md)
- **Interior tier dispatch takes the first key present** (`sensor_points` → `sensor_surfaces` → `buildings` → `floors`) — the losers are dropped, not rejected: a one-storey request billed as every storey. → same file
- **`openingFactor` is read by that exact spelling, no alias** — `opening_factor` is ignored and the window silently becomes clear glass. → same file
- **Daylight factor sits on a ~2% floor** — the same number as the "daylit" 2% planning convention, so a per-sensor comparison against 2% does not discriminate. Read glazing changes *above* the floor. → same file
- **`preview_area` without `analysis_type` prices the wind grid** — ~4× the tiles for a solar/thermal run (verified: 36 vs 9 on one polygon). It warns; the number it hands back is still wrong. → [05-area-api.md](references/05-area-api.md)
- **Each facade sub-batch is billed separately** — a request over the server's 262,144-sensor cap is split transparently, and every sub-job charges. → [analyses/09-facade-terrain.md](references/analyses/09-facade-terrain.md)

## Default workflow

Most users bring their own data (BIM/Rhino/IFC/GeoJSON footprints, custom landscapes, proposed-scenario ground). Ask before falling back to the SDK fetch path.
→ **BYO via SDK (default):** [byo-inputs.md](references/byo-inputs.md) — **BYO as files into the platform:** [platform-byo-upload.md](references/platform-byo-upload.md) — **Prototype with fetched data:** [01-quickstart.md](references/01-quickstart.md)

## Setup and basics

| Topic | Reference |
|---|---|
| Install + auth | [00-setup.md](references/00-setup.md) |
| End-to-end quickstart | [01-quickstart.md](references/01-quickstart.md) |
| Polygon / GeoJSON / coords | [02-geometry.md](references/02-geometry.md) |
| **Coordinate systems** — every frame in one place (WGS84 in, polygon-bbox-SW, tile-local, surface UV, vertical datum), reprojection recipes, wrong-place diagnostic | [geospatial-crs.md](references/geospatial-crs.md) |
| Time period / weather window | [03-time-period.md](references/03-time-period.md) |
| Weather data / EPW | [04-weather-data.md](references/04-weather-data.md) |
| Bring your own buildings / trees / ground | [byo-inputs.md](references/byo-inputs.md) |
| Platform FILE upload (GeoJSON/.obj/.epw formats, projections, caps) | [platform-byo-upload.md](references/platform-byo-upload.md) |

## Execution styles

Pick the entry point first — it shapes blocking, webhooks, and persistence. Full rule: [async-and-jobs.md](references/async-and-jobs.md).

| When | Entry point |
|---|---|
| Sync, blocks until result | `client.run_area_and_wait()` → `AreaResult` |
| Async, returns `AreaSchedule` (use webhook or `check_area_state`); land via `client.merge_area_jobs(schedule)` once terminal | `client.run_area()` → `AreaSchedule` |
| Single tile, custom polling | `client.analyses.execute()` + `client.jobs.*` → `Job` |

## Choosing an analysis

**READ the linked reference file before writing any code for that analysis.** The payload shape, required fields, and enum values are defined there — not in this table.

| User wants to know… | Analysis | Weather? | READ this reference | Result interpretation |
|---|---|---|---|---|
| Is it windy at street level? | `wind-speed` | no | [analyses/01-wind-speed.md](references/analyses/01-wind-speed.md) | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Is wind comfortable for pedestrians? | `pedestrian-wind-comfort` | **REQUIRED** | [analyses/02-pedestrian-wind-comfort.md](references/analyses/02-pedestrian-wind-comfort.md) | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Enough daylight at street level? | `daylight-availability` | no | [analyses/03-daylight-availability.md](references/analyses/03-daylight-availability.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Sun-hour exposure? | `direct-sun-hours` | no | [analyses/04-direct-sun-hours.md](references/analyses/04-direct-sun-hours.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| How open is the sky? | `sky-view-factors` | no | [analyses/05-sky-view-factors.md](references/analyses/05-sky-view-factors.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Solar energy on a surface? | `solar-radiation` | **REQUIRED** | [analyses/06-solar-radiation.md](references/analyses/06-solar-radiation.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Outdoor thermal comfort? | `thermal-comfort-index` (UTCI) | **REQUIRED** | [analyses/07-thermal-comfort-utci.md](references/analyses/07-thermal-comfort-utci.md) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |
| % of time uncomfortable per year? | `thermal-comfort-statistics` (TCS) | **REQUIRED** | [analyses/08-thermal-comfort-statistics.md](references/analyses/08-thermal-comfort-statistics.md) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |
| Daylight **inside** a room? | `daylight-factor` | no | [analyses/10-interior-daylight-factor.md](references/analyses/10-interior-daylight-factor.md) | same reference |

### `daylight-factor` is an INTERIOR model

No polygon, no Area API — `run_area()` rejects it — and its entities use a **nested** mesh shape
where the flat outdoor shape silently yields an empty occluder. Read
[analyses/10-interior-daylight-factor.md](references/analyses/10-interior-daylight-factor.md) first.

### Weather is not optional for the four marked REQUIRED

Those payloads carry weather **arrays**, not a weather file id. Build them with the SDK — never by hand:

```python
stations = client.weather.get_weather_file_from_location(lat=lat, lon=lon)  # nearest stations
weather_data = client.weather.filter_weather_data(
    identifier=stations[0]["uuid"], time_period=tp)                         # one point per hour in tp
payload = SolarRadiationModelRequest.from_weatherfile_payload(..., weather_data=weather_data)
```

Omitting them does **not** produce a clean validation error. The request is accepted (`202`), **the job is
billed**, and it fails in the worker with a message that names an internal array, not the missing input:
`DNI length 0 != sun_vectors 240`, `missing array 'horizontal-infrared-radiation-intensity'`.
If you see either, you omitted weather data — add it via the snippet above and resubmit. Full API:
[04-weather-data.md](references/04-weather-data.md).

## Cross-cutting topics

| Topic | Reference |
|---|---|
| Area API / tiling / AreaResult / cost preview | [05-area-api.md](references/05-area-api.md) |
| Facade / roof / BYO-sensor analysis + terrain draping | [analyses/09-facade-terrain.md](references/analyses/09-facade-terrain.md) |
| Interior geometry preparation (rooms, windows, per-window glazing, sensor grids) | [analyses/10-interior-daylight-factor.md](references/analyses/10-interior-daylight-factor.md) |
| Async runs / `AreaSchedule` / single-tile primitives | [async-and-jobs.md](references/async-and-jobs.md) |
| Webhooks / Standard Webhooks v1 / verification | [06-webhooks.md](references/06-webhooks.md) |
| Image generation (PNG output) | [07-images.md](references/07-images.md) |
| Errors / exception hierarchy | [08-error-handling.md](references/08-error-handling.md) |
| Plotting / compare scenarios (baseline vs proposed) / GeoTIFF export | [interpretation/grid-conventions.md](references/interpretation/grid-conventions.md) |
| Gradio area explorer app recipe | [recipes/gradio-area-explorer.md](references/recipes/gradio-area-explorer.md) |
| Making a render read correctly (legend bounds, masked cells, categorical output, colormaps) | [recipes/rendering-results-well.md](references/recipes/rendering-results-well.md) |

## Recipes

Use the `references/recipes/` folder for UI/app implementation recipes that combine SDK usage with product-level UX guidance.

- Start with [recipes/gradio-area-explorer.md](references/recipes/gradio-area-explorer.md) to build a compact Gradio app using the Infrared SDK.
- For a richer 3D playground (Vite + React + DeckGL frontend, FastAPI backend, Zustand state, location picker that dynamically fetches buildings / vegetation / ground materials from the SDK), see [recipes/sdk-playground-fastapi.md](references/recipes/sdk-playground-fastapi.md).
- To build a **SketchUp Ruby extension** that submits simulations directly from a 3D model and renders heatmap results as coloured faces in the viewport — including a post-run KPI panel with stats and charts — see [recipes/sketchup-plugin.md](references/recipes/sketchup-plugin.md). Note: this recipe uses Ruby (not Python); the Infrared API contract (auth headers, payload shapes, async job lifecycle) is identical.
- To call the SDK from **Rhino 8 Grasshopper** Python 3 Script components, see [recipes/grasshopper.md](references/recipes/grasshopper.md) — a flat list of small patterns: SDK install via `# r:`, auto-registering outputs (`ScriptVariableParam` + `BeforeRunScript`), sticky state, off-UI-thread work with `threading` + `ExpireSolution(True)`, browser-based AOI picker, DotBim ↔ Rhino Mesh, locating the .gh file, saving PNG / GeoTIFF, heatmap mesh from a numpy grid, and visible logging.
- For **hackathon/demo stacks** (TypeScript direct API, FastAPI + Railway, React frontends, persistence, billing): see [recipes/hackathon-tools.md](references/recipes/hackathon-tools.md).
- **Before your first render**, read [recipes/rendering-results-well.md](references/recipes/rendering-results-well.md) — the traps that make correct results *look* wrong (per-run auto-scaling, masked cells painted as zero, facades on their own scale, continuous ramps on categorical output, rainbow colormaps, flipped north), and what ForgeKit does instead. Tool-agnostic: applies to matplotlib, Three.js, DeckGL, or a BIM viewport.

## Invariants

- **Python 3.9+** required.
- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env. Never `Authorization: Bearer`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946), **WGS84 / EPSG:4326** assumed (never validated — reproject before calling; see [geospatial-crs.md](references/geospatial-crs.md)).
- Imports: `from infrared_sdk import InfraredClient`; `from infrared_sdk.analyses.types import AnalysesName, ...`; `from infrared_sdk.models import TimePeriod, Location` (only for analyses that take them — wind does not).
- Enum **values** are kebab-case (`"wind-speed"`); enum **member names** are snake_case (`AnalysesName.wind_speed`, `PwcCriteria.lawson_lddc`, `TcsSubtype.heat_stress`).
- `wind_direction=270` means wind **from** the west (meteorological convention).
- For most uses: `client.run_area_and_wait(request, polygon, buildings=...)` (sync). Single-tile polygons skip tiling automatically. **Exception:** multi-tile **`wind-speed`** runs should use the two-step path with `merge_area_jobs(strategy="directional_blend", wind_direction_deg=...)` to eliminate seam artefacts — see [05-area-api.md#merging-strategies](references/05-area-api.md#merging-strategies). For async / long-running, see [async-and-jobs.md](references/async-and-jobs.md).
- Single tile is **512 m × 512 m**. Cell pitch is **1 m × 1 m**. Polygon larger than that auto-tiles. Solar/UTCI/TCS tiles carry a **128 m context margin** per side for distant-shadow buildings.
- `wind_speed` is a **`float`** in m/s, `0 ≤ v ≤ 100` (SDK 0.5.1+). Do **not** round an EPW mean to satisfy a type — truncating 3.9 to 3 shifts every cell by −23 %.
- `wind_direction` is a **whole-degree `int`**, `0 ≤ d ≤ 360`. A fractional bearing (e.g. `22.5`) is rejected at construction — round it deliberately before passing.
- Plotting bounds: distributions are heavy-tailed, so never scale to the grid's own min/max. Carry a fixed per-analysis domain — SVF/DA `[0,100]`, DSH `[0,12]`, solar `[0,1000]`, wind `[0,15]`, UTCI `[-40,46]` — and hold it constant across runs you compare. (`min_legend` / `max_legend` serve this on **surface** results only; see *Silently wrong* above.) Details: [recipes/rendering-results-well.md](references/recipes/rendering-results-well.md).
- Coordinate frames: WGS84 lon/lat in, polygon-bbox-SW metres for caller geometry, tile-local metres inside a tile, surface UV out. Full map: [geospatial-crs.md#the-frames-end-to-end](references/geospatial-crs.md#the-frames-end-to-end).
- Use `result.bounds` (added 0.4.4) — not `polygon.bounds` — to place the bitmap in a map viewer. `result.bounds` reflects the real NE-padded grid extent.

## Pitfalls

- **Writing SDK code from training-data memory without reading the analysis reference** — payload shapes and enum values change between versions. Always read the reference first.
- **Skipping 00-setup.md** and guessing the import path or client constructor signature.
- `[lat, lon]` instead of `[lon, lat]` in GeoJSON (most common bug).
- `AnalysesName.WIND_SPEED` → `AnalysesName.wind_speed` (StrEnum members are snake_case).
- **Submitting `pedestrian-wind-comfort` / `solar-radiation` / `thermal-comfort-index` / `thermal-comfort-statistics` without weather arrays** — accepted and billed, then fails in the worker. See *Weather is not optional* above.
- Skipping vegetation/ground for thermal or solar runs — they materially affect MRT and surface heat. See [byo-inputs.md](references/byo-inputs.md).
- Verifying webhooks against re-encoded JSON instead of raw bytes (see [06-webhooks.md](references/06-webhooks.md)).

**End of task** — always read [references/reflection-and-feedback.md](references/reflection-and-feedback.md) once. Runnable recipes live at [`cookbook/`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook).
