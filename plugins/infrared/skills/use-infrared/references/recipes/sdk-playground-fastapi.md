# Recipe: SDK Playground — FastAPI + Vite + DeckGL

A PRD for an AI coding agent: build one production-quality climate-analysis playground on top of the Infrared SDK. A user searches for any location, the app fetches buildings / vegetation / ground materials for that spot via the SDK, picks an analysis (wind, daylight, solar, UTCI, etc.), tweaks parameters, and renders a heatmap over a 3D scene with a copy-pasteable Python snippet.

The architecture is deliberately small and extensible — the same shell drops in scenario comparison (A vs B vs C) and a tree-placement before/after tool with surgical changes.

## How to use this recipe

> **Read the whole file once, end-to-end, before writing any code.** This recipe is dense on purpose. A first-pass read gives you the shape of the contract, where the data flows, and where the silent failure modes live. After that, re-read the section that matches the phase you're in (the map is in **Implementation phases** below).

This recipe is one document in a larger skill (`use-infrared`). When you need deeper SDK detail than the recipe provides, route to:

- `../00-setup.md` — install + auth.
- `../02-geometry.md` — polygon / coords / `[lon, lat]` order.
- `../03-time-period.md` — `TimePeriod` semantics, single-month windows.
- `../04-weather-data.md` — TMY stations, `filter_weather_data`, `extract_weather_fields`.
- `../05-area-api.md` — area-API, tiling, `AreaResult`, the polygon-bbox-SW frame.
- `../byo-inputs.md` — `buildings=`, `vegetation=`, `ground_materials=` payload shapes.
- `../analyses/0N-*.md` — per-analysis payload + interpretation references (consult the matching one before writing each dispatch builder).
- `../interpretation/grid-conventions.md` — NaN clipping, cell-row-major order, `min_legend` / `max_legend`.

The parent `SKILL.md` indexes the rest.

## Building blocks (and how they fit our stack)

Each piece below is a generic tool you'll meet in other projects. Then the **App-specific** line says how *this* playground uses it. Knowing which half is the framework convention and which half is the playground flavour makes it easier to vary things later.

| Building block | What it is | App-specific role |
|---|---|---|
| **Vite + React 19 + TypeScript** | Modern frontend toolchain with HMR and a type system. | TypeScript is the schema authority — the `AnalysisId` union + `ANALYSES` registry are read by every UI component and define the wire-format contract. No runtime validation needed because the types match the FastAPI response Pydantic models. |
| **DeckGL** (`@deck.gl/core` + `layers` + `geo-layers` + `react`) | WebGL renderer of composable map / 3D-scene layers. `TileLayer`, `BitmapLayer`, `PolygonLayer`, `ColumnLayer`, controlled `MapView`. | One full-bleed canvas per Scene. Layer order: basemap → ground → heatmap → trees → buildings → samplers. Heatmap is a `BitmapLayer` whose image is a canvas built from the cell grid; alpha is per-pixel-masked to an inscribed circle. |
| **CARTO Voyager raster tiles** | Free OSM-attributed tiles via deck.gl `TileLayer`. No API key. | The only basemap. Attribution overlay (`© OpenStreetMap contributors · © CARTO`) is required at `absolute right-2 bottom-2`. Swap to vector tiles only if/when you start needing styling control. |
| **Tailwind v4** (`@tailwindcss/vite`) | CSS-first utility framework with `@theme` design tokens. | Single teal accent on near-white background. The palette lives in `globals.css` `@theme`; no `tailwind.config.js`. Card recipe `rounded-lg bg-background/95 p-4 shadow-xl ring-1 ring-border backdrop-blur-md` is reused for every floating panel. |
| **Zustand** (`+ subscribeWithSelector`, optionally `+ immer`) | Tiny store; selector-subscriptions; serialisable. | One store. **Scenarios** are first-class — runs and tree overlays are keyed per scenario so A/B/C compare and tree-placement before/after fall out for free. `centroid` / `areaSize` / `geometry` are shared across scenarios; `params` / `trees` / `runs` are per-scenario. |
| **Nominatim** | Public OSM geocoder. 1 req/s, no auth, ToS-bound. | Powers the `LocationPicker` search box. Debounced 300 ms client-side. For volume, proxy through the FastAPI backend with a custom `User-Agent`, or swap for a managed geocoder. |
| **FastAPI + uvicorn + Pydantic v2** | Async Python web framework + ASGI server + typed request/response models. | Three endpoints: `/fetch_geometry`, `/run_analysis`, optional `/preview`. CORS open in dev, locked to the frontend origin in prod. Caching is plain in-memory dicts + a disk sidecar; promote to Redis when you go multi-worker. |
| **`infrared-sdk`** | The reason any of this exists. Public Python SDK over the Infrared simulation API. | Wrapped behind the dispatch table. The dispatch table is the **only** place SDK request classes appear — every other backend module talks to it through the wire-format `analysis_type` string. |
| **`numpy`** | Grid math. | Computes KPIs and the histogram on the raw `result.merged_grid`. Critical: walk NaN cells to `None` before JSON serialisation. |

The **patterns** here are general (driven-UI registry, scenario-keyed state, dynamic geometry fetch with cache-by-key, BitmapLayer-from-canvas heatmaps, circle-clipped masks for round demo aesthetics). The **app-specific flavours** are: the 7-analysis set, the 5-stop jet palette, the inscribed-circle clip radius from the SDK polygon, the `TreeAdd` shape matching OSM property names, and the kebab-string enum values across the SDK.

## Implementation phases

A suggested running order. Each phase has a re-read trigger — open those sections again right before you start the phase, because the prose density per topic is high.

| Phase | Build | Re-read before starting | Done-when |
|---|---|---|---|
| **0** Skim | Read this entire file. Open `00-setup.md` + `05-area-api.md` from the parent skill. | — | You can sketch the wire contract from memory. |
| **1** Backend skeleton | `main.py` (FastAPI app + `/health`), `dispatch.py` (builders for all 8 wire-format analyses), `kpis.py`, `snippets.py`, the shared helpers. Hard-code a Vienna centroid for now. | "Wire contract", "Backend patterns", "Dispatch table", "Shared helpers". Pull `../analyses/0N-*.md` per builder. | `curl /run_analysis` for `wind-speed` at `(16.37, 48.1985)` returns a sane grid + KPIs + histogram. |
| **2** Dynamic geometry | `/fetch_geometry` with `geometry_id` caching. **DotBim → footprint GeoJSON** for buildings. Lightweight conversions for vegetation and ground. | "DotBim → footprint GeoJSON", "Shared helpers", "Caching layers", `../byo-inputs.md`. | A second `curl` for a different centroid (e.g. Berlin Alexanderplatz `(13.4128, 52.5219)`) returns geometry + the run still works against the cached payload. |
| **3** Frontend scaffold | Vite + Tailwind v4 + `analysis-registry.ts` + `api.ts` + the Zustand store. No DeckGL yet. | "Analysis registry — single source of truth", "Zustand store shape", "Scenario management". | Buttons in a list switch the `active` analysis; the store reflects centroid + scenario lifecycle. |
| **4** Scene | `Scene.tsx` with the full layer stack. `useDeckLayers` + `useViewState` extracted to keep the file inside the soft-limit. | "Scene composition (DeckGL)", "UI / UX guidelines". | A heatmap renders over the basemap, building footprints align, fly-in transitions on centroid change. |
| **5** Controls | `LocationPicker`, `AnalysisTab` (Inputs + Results card), `ParamControls`, `ModelSwitcher`, `Histogram` (with hover cursor), `KpiStrip`. | "Inputs + Results side rail", "Location picker pattern", "UI / UX guidelines". | Users can search, pick, run all 7 analyses, and read the KPI + histogram against the heatmap they're hovering. |
| **6** Scenarios + trees | Tab strip for scenarios, fork / rename / delete, the tree-drawing tool, `runAll`, optional diff layer. | "Scenario management", "Extensions / Tree-placement before / after", pitfalls #22 + #23. | Forking baseline → "+ trees" → placing trees → running all → diff renders show before/after. |
| **7** Polish + deploy | Attribution overlay, CORS lock-down, error toasts, Dockerfile, environment variables. | "Deployment", "Things to watch out for" (skim again — the pitfalls land differently once code exists). | Acceptance checklist passes. |

**Re-read triggers across phases** — if you're about to do any of these, pull the matching section back up first:

- About to write a new SDK call → "Dispatch table" + the matching `../analyses/0N-*.md`.
- About to serialise the grid → pitfalls #1 (bounds describe grid) + #2 (NaN → `null`).
- About to splice a tree into the vegetation dict → pitfall #5 (OSM property names) + "Tree-placement before / after".
- About to render a layer → pitfall #14 (`pickable: true` on heatmap) + pitfall #19 (memoise DeckGL layers).
- About to deploy → "Deployment" + pitfall #18 (CORS lock-down).

## Code budget

**Target ≤ 1000 lines of code total** across backend + frontend (excluding generated `package-lock.json` / `requirements.txt` and the project's two Tailwind / Vite config files). A rough split that holds in practice:

| Area | Lines |
|---|---|
| Backend (`main.py`, `dispatch.py`, `kpis.py`, `snippets.py`, `geometry.py`) | ≤ 450 |
| Frontend Zustand store + analysis registry + API client | ≤ 250 |
| Frontend Scene + LocationPicker + AnalysisTab + ParamControls + ModelSwitcher + Histogram | ≤ 300 |
| `App.tsx` + glue | ≤ 80 |

**Per-component soft-limit: 150 lines.** If a component creeps past it, push primitives down (helper hooks for hover / sampler / layer assembly) or up (state into the Zustand store). `Scene.tsx` is the usual offender; extract `useDeckLayers()` and `useViewState()` into `playground/hooks/` to keep it shapely. The recipe ships a *minimal* climate playground — production polish (mobile shell, embed handshake, async runs, line-profile sampler, rich snippet popover) is deliberately deferred.

## Mission

One-shot a fullstack climate-analysis playground:

- **Frontend** — Vite + React + DeckGL + Zustand. Search-driven location picker, 3D scene with extruded buildings + ground polygons + trees + heatmap, registry-driven parameter UI, KPI strip with a hover-cursor histogram.
- **Backend** — FastAPI wrapping the `infrared-sdk`. Two endpoints — one fetches geometry for a centroid, one runs an analysis against the cached geometry. Geometry and weather are cached server-side.
- **Deployment** — `uvicorn` for local dev; Docker / Fly / Railway / Modal for prod. No vendor lock-in; the only external dependency is the Infrared API.

## What the user gets

- One location picker (text search + map double-click + lat/lon inputs).
- Seven analyses out of the box, driven from a single TypeScript registry: `wind-speed`, `pedestrian-wind-comfort`, `daylight-availability`, `sky-view-factors`, `solar-radiation`, `thermal-comfort-index` (UTCI), `thermal-comfort-statistics` (TCS). Adding `direct-sun-hours` is one registry entry — the backend already dispatches it.
- Two area sizes — concrete `half_side_m` values **must** match these or the cache keys diverge:
  - `small` → `half_side_m = 256` (≈ 500 m square — note: NOT single-tile for wind; auto-tiles to a 768-wide merged grid, see pitfall #1)
  - `medium` → `half_side_m = 500` (≈ 1 km square, ~3 tiles per side)

  ```python
  def half_side_for(area_size: str) -> float:
      return 256.0 if area_size == "small" else 500.0
  ```
- A primary KPI per analysis, a coloured histogram of cell values with a vertical cursor that follows pointer hover on the map.
- A short one-line description per analysis under the model label, so users know what they're running.

## Tech stack

**Backend (Python 3.11+)**

- `infrared-sdk >= 0.4.8` — the public SDK. Use `client.run_area_and_wait` for synchronous runs; switch to `client.run_area` + `merge_area_jobs` (or webhooks) only if you start running 1.5 km+ polygons or want `directional_blend` for multi-tile wind.
- `scipy >= 1.10` — for `ConvexHull` over building footprints. See "DotBim → footprint" below for why this is mandatory, not optional.
- `fastapi >= 0.110`, `uvicorn[standard]`, `python-dotenv`, `pydantic >= 2`, `numpy`.

**Frontend (Node 20+)**

- Vite 7, React 19, TypeScript 5.
- `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/geo-layers`, `@deck.gl/react` (≥ 9).
- `zustand >= 4.5` with `subscribeWithSelector`.
- Tailwind v4 (`@tailwindcss/vite` plugin), `lucide-react` for icons.
- Basemap: **CARTO Voyager raster tiles** via deck.gl `TileLayer`. No Mapbox token required.
- Geocoding: **Nominatim** (free, OSM-attributed). Swap for a managed geocoder if you outgrow its 1 r/s rate limit.

**Deliberately not used**

- TanStack Query — the Zustand store owns the run cache.
- Mapbox / Maplibre — CARTO raster is enough for the demo and removes an API-key surface.
- Plotly / Chart.js — a Tailwind flexbox histogram with coloured bars beats either on perf and matches the heatmap colour scale.
- Any websocket / SSE layer — synchronous `/run_analysis` works for ≤ 1 km polygons in ~5–60 s.

## Project structure

```
sdk-playground/
├── backend/
│   ├── main.py                # FastAPI app: /health, /fetch_geometry, /run_analysis, /preview
│   ├── dispatch.py            # Per-analysis SDK request builders (centroid is a parameter)
│   ├── kpis.py                # KPI specs + histogram computation
│   ├── snippets.py            # Python-snippet templates rendered into the info popover
│   ├── geometry.py            # DotBim → footprint GeoJSON helpers for the Scene
│   ├── cache/                 # Disk-backed geometry cache: {geometry_id}.json
│   ├── requirements.txt
│   ├── .env.example           # INFRARED_API_KEY=
│   └── Dockerfile             # Single-image deploy
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── catalog/
    │   │   └── analysis-registry.ts   # Single source of truth: param specs, colour ranges
    │   ├── playground/
    │   │   ├── api.ts                 # Thin fetch wrapper over the backend
    │   │   ├── store.ts               # Zustand: active, areaSize, centroid, runs, trees, …
    │   │   ├── hooks/useAnalysisHover.ts
    │   │   ├── components/
    │   │   │   ├── Scene.tsx          # DeckGL composition: basemap + ground + heatmap + trees + buildings
    │   │   │   ├── LocationPicker.tsx # Search box + lat/lon inputs + status pill
    │   │   │   ├── AnalysisTab.tsx    # Inputs card + Results card (side rail)
    │   │   │   ├── ParamControls.tsx  # Registry-driven sliders/selects/ranges
    │   │   │   ├── AreaSizeSelector.tsx
    │   │   │   ├── ModelSwitcher.tsx  # Bottom chip bar — one button per analysis
    │   │   │   ├── Histogram.tsx      # Coloured bars + hover cursor
    │   │   │   └── KpiStrip.tsx
    │   │   └── tabs/ResultsCard.tsx
    │   └── styles/globals.css         # Tailwind v4 @theme
    ├── public/
    │   └── (preloads, if any — optional)
    ├── vite.config.ts
    └── package.json
```

Keep modules under 400 lines. Each frontend component owns one responsibility; the Zustand store owns all cross-component state.

## Wire contract

The agent must implement these payloads byte-for-byte — the FE and BE both read the same TypeScript-shaped JSON.

```ts
// POST /fetch_geometry
Request:  { centroid: [lon, lat], area_size: 'small' | 'medium' }
Response: {
  geometry_id: string                  // sha256(round(lon, 6), round(lat, 6), size)[:16]
  centroid: [lon, lat]
  half_side_m: number
  building_count: number
  vegetation_count: number
  ground_layer_count: number
  buildings_geojson: FeatureCollection // { centroid, half_side_m, features: [{geometry, properties: { height_m }}] }
  vegetation_geojson: FeatureCollection
  ground_geojson: FeatureCollection    // properties.material ∈ {asphalt|concrete|soil|vegetation|water|building}
}

// POST /run_analysis
Request:  {
  analysis_type: AnalysisId
  area_size: 'small' | 'medium'
  centroid: [lon, lat]
  params: Record<string, number | string>
  trees_added?:   Array<{ id, lon, lat, height_m, crown_diameter_m, species? }>
  trees_removed?: string[]             // OSM ids to omit from the SDK call
}
Response: {
  ok: boolean
  analysis_type: AnalysisId
  area_size: 'small' | 'medium'
  grid: (number | null)[][]            // NaN cells → null (JSON has no NaN)
  bounds: [west, south, east, north]   // Covers the merged GRID, not the polygon
  min: number; max: number             // Data min/max
  min_legend: number | null            // Often null; frontend ignores it
  max_legend: number | null
  unit: string
  kpis: {
    primary:   { label: string; unit: string; value: number }
    secondary: { label: string; unit: string; value: number }
  }
  histogram: { edges: number[]; counts: number[] }   // 20 equal-width bins
  snippet: string                       // Copy-pasteable Python for current centroid + params
  timings?: Record<string, number>
  error?: string
}

// POST /preview (optional — cheap pre-flight)
Request:  { centroid, area_size, analysis_type: AnalysisId }
Response: { tile_count: number, estimated_time_s: number, estimated_cost_tokens: number }
// NOTE: the SDK's preview_area returns one AreaPreview per call, scoped to one
// analysis_type. The backend MUST forward analysis_type:
//     client.preview_area(polygon, analysis_type=req.analysis_type)
// Without the kwarg the SDK silently returns wind-grid tile counts (256 m step,
// 50% overlap) for every analysis, over-counting solar/daylight by ~4×. Call
// /preview twice if you want both a wind and a solar estimate.
```

## Backend patterns

### `/fetch_geometry` — dynamic SDK lookup

For a user-picked + **explicitly-confirmed** centroid (see "State machine" below — never auto-fetch on a centroid keystroke), build a square polygon (`half_side_m` from the `area_size` table), then call three SDK utilities in sequence:

- `client.buildings.get_area(polygon)` → `area.buildings` (a `dict[str, DotBimMesh]` in polygon-bbox-SW frame).
- `client.vegetation.get_area(polygon)` → `area_veg.features` (a `dict[str, Feature]` keyed by OSM id).
- `client.ground_materials.get_area(polygon)` → `area_gm.layers` (a `dict[material_name, FeatureCollection]`).

Cache the combined payload to `cache/{geometry_id}.json` and to an in-memory dict keyed by `geometry_id = sha256(round(lon,6), round(lat,6), size)[:16]`. Rounding the centroid before hashing avoids cache churn when the geocoder returns slightly-different decimals on repeat queries.

> **DotBim serialisation gotcha.** `client.buildings.get_area(polygon).buildings` is `dict[str, DotBimMesh]` where `DotBimMesh` is a Pydantic v2 model. Raw `json.dumps(area.buildings)` raises `TypeError`. Call `.model_dump()` on each mesh (or `.to_dict()` for older SDKs) before writing the disk cache:
>
> ```python
> def _to_plain(m): return m.model_dump() if hasattr(m, "model_dump") else m
> serialisable = {bid: _to_plain(mesh) for bid, mesh in area.buildings.items()}
> ```

The endpoint also returns lightweight footprint GeoJSON the Scene can render directly — convert DotBim meshes to convex-hull polygons (NOT bbox — see DotBim section below) + max-z height; convert vegetation Features to Point Features; flatten ground-material FeatureCollections into one with `material` on each Feature.

> **Re-derive footprints on cache read.** The disk cache stores raw DotBim meshes; recompute `buildings_geojson` from those on every cache hit, not from a stored `buildings_geojson` field. That way changing the projection algorithm (bbox → hull) takes effect immediately without re-paying the 15-30 s SDK fetch. Costs a few ms per request; saves cold-start latency on every redeploy.

> **Watch out**: `area.buildings` is a **dict**, not a list. Iterate values when projecting to GeoJSON. Pass the dict itself (not a list of values) to `run_area_and_wait(buildings=...)` — the SDK keys per-tile transforms by id.

### `/run_analysis` — dispatch + cache + SDK call

- Validate `analysis_type` against the `BUILDERS` table. Reject unknown strings before any SDK work.
- Look up cached geometry by `(centroid, area_size)`. If absent, auto-fetch via `/fetch_geometry` internally — never fail with "geometry not loaded".
- If the analysis needs weather (`NEEDS_WEATHER = { pedestrian-wind-comfort, solar-radiation, thermal-comfort-index, thermal-comfort-statistics }`), fetch the closest TMY station (`client.weather.get_weather_file_from_location`) and filter to the requested `TimePeriod`. Cache per `(lon4, lat4, month, hour_start, hour_end)`.
- Apply the tree overlay: pop `trees_removed` from the cached vegetation dict, splice in `trees_added` as Point Features. Pass the resulting dict via the SDK's `vegetation=` keyword.
- Call `client.run_area_and_wait(request, polygon, buildings=..., vegetation=..., ground_materials=...)`.
- Convert the merged grid: `np.nan → None` per cell, derive `bounds` from polygon SW corner + grid shape × 1 m (the SDK ceil-rounds tiles, so the grid is usually larger than the polygon — using polygon corners offsets the heatmap by tens of metres).
- Compute KPIs + histogram + snippet, return the response.

### Single AnalysisSpec registry (`analyses_registry.py`)

Don't ship four parallel string-keyed tables (`BUILDERS`, `NEEDS_WEATHER`, `KPIS`, `UNIT_BY_TYPE`, `_BODIES`, `_IMPORTS`) — they drift the moment you add an analysis. One `AnalysisSpec` dataclass binds everything:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class AnalysisSpec:
    id: str
    builder: Callable                # (centroid, params, weather) -> SDK request
    kpis: Callable                   # (valid_grid, params) -> dict
    snippet_body: str                # template
    snippet_imports: str
    unit: str                        # SI / display unit for the cell value
    needs_weather: bool
    notes: str = ""

ANALYSES: dict[str, AnalysisSpec] = {
    "wind-speed": AnalysisSpec(id="wind-speed", builder=_wind_speed, kpis=_wind_kpis,
        snippet_body=_WIND, snippet_imports=_IMPORTS["wind-speed"],
        unit="m/s", needs_weather=False, ...),
    ...
}

def get(analysis_type: str) -> AnalysisSpec:
    if analysis_type not in ANALYSES:
        raise KeyError(f"unknown analysis_type: {analysis_type}")
    return ANALYSES[analysis_type]
```

`main.py` then does `spec = get(req.analysis_type)` and reads `spec.builder`, `spec.kpis`, `spec.unit`, `spec.needs_weather`. Adding a new analysis end-to-end is **one entry + four functions** — not six table edits. Expose `/analyses` for introspection:

```python
@app.get("/analyses")
def list_analyses() -> dict:
    return {"analyses": [
        {"id": s.id, "unit": s.unit, "needs_weather": s.needs_weather, "notes": s.notes}
        for s in ANALYSES.values()
    ]}
```

### Per-analysis builder signatures

Pattern: one builder per analysis, each `(centroid: tuple[float, float], params: dict, weather_or_None) -> InfraredRequest`. Required kwargs by analysis:

| analysis_type | SDK class | Required kwargs | Needs weather? |
|---|---|---|---|
| `wind-speed` | `WindModelRequest` | `analysis_type=AnalysesName.wind_speed`, `wind_speed: int`, `wind_direction: int` | No |
| `pedestrian-wind-comfort` | `PwcModelRequest` | `analysis_type`, `criteria: PwcCriteria("kebab-string")`, `**extract_weather_fields(data, ["windSpeed", "windDirection"])` | Yes |
| `daylight-availability` | `SolarModelRequest` | `analysis_type=AnalysesName.daylight_availability`, `latitude`, `longitude`, `time_period: TimePeriod` | No |
| `direct-sun-hours` | `SolarModelRequest` | same as above with `AnalysesName.direct_sun_hours` | No |
| `sky-view-factors` | `SvfModelRequest` | `analysis_type`, `latitude`, `longitude` (both optional in the SDK — only consulted by the vegetation validator. Send them if you ever pass `vegetation=...`; harmless if you don't) | No |
| `solar-radiation` | `SolarRadiationModelRequest.from_weatherfile_payload` | `payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation)`, `location=Location(...)`, `time_period`, `weather_data` | Yes |
| `thermal-comfort-index` | `UtciModelRequest.from_weatherfile_payload` | `payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index)`, `location`, `time_period`, `weather_data` | Yes |
| `thermal-comfort-statistics` | `TcsModelRequest.from_weatherfile_payload` | `payload=TcsModelBaseRequest(analysis_type=..., subtype=TcsSubtype("kebab-string"))`, `location`, `time_period`, `weather_data` | Yes |

> **Watch out (single-month is required for SIX analyses, not four)**: `daylight-availability`, `direct-sun-hours`, `pedestrian-wind-comfort`, `solar-radiation`, `thermal-comfort-index`, and `thermal-comfort-statistics` all reject multi-month `TimePeriod`s server-side. Both the sibling docs (`../03-time-period.md` line 45, `../interpretation/solar-results.md` lines 22 + 37, `../analyses/03-daylight-availability.md`, `../analyses/04-direct-sun-hours.md`) and the SDK README make this explicit. Always pass `start_month == end_month`. Only `wind-speed` and `sky-view-factors` (which take no `TimePeriod` at all) are exempt. Inline the constraint:
>
> ```python
> tp = TimePeriod(start_month=m, end_month=m,
>                 start_day=ds, end_day=de,
>                 start_hour=hs, end_hour=he)
> ```
>
> **Watch out (enum convention)**: `PwcCriteria` and `TcsSubtype` are `StrEnum`s — `PwcCriteria("lawson-2001")` and `PwcCriteria.lawson_2001` both resolve to the same wire string. Pick one form and stay consistent so the rendered Python snippets are readable. The dispatch builders here use the value-from-string form (`PwcCriteria(params["criteria"])`) because `params` arrives as a kebab string from the frontend registry — the round-trip is `"lawson-2001" → PwcCriteria("lawson-2001") → "lawson-2001"`.

### KPI + histogram

Per-analysis primary KPI (mean for most, mode-of-integer-class for PWC) and a secondary scalar (percentage of valid cells past a threshold, total over polygon, or band-share). Histogram: 20 equal-width bins over the valid data range — the frontend colours each bar by its bin midpoint through the same colour scale as the heatmap.

### Snippet rendering

Per-analysis Python templates, formatted with the live centroid + params. The rendered snippet must be **self-contained and copy-runnable**: `from infrared_sdk import InfraredClient` only, no internal helpers, no admin tokens.

A template that says `result = client.run_area_and_wait(req, polygon, ...)` without first showing how `polygon` was built is dead code on paste. Always prepend the polygon construction inside the snippet:

```python
# Template (every analysis)
polygon = {
    "type": "Polygon",
    "coordinates": [[
        [{lon_w}, {lat_s}], [{lon_e}, {lat_s}],
        [{lon_e}, {lat_n}], [{lon_w}, {lat_n}], [{lon_w}, {lat_s}],
    ]],
}
```

Compute `lon_w`, `lat_s`, `lon_e`, `lat_n` server-side from `(centroid, half_side_m)` using the same metres-to-degrees formula the polygon builder uses, then `format(**bbox, **params)` into the template. After this block, the snippet does `client.buildings.get_area(polygon)` and the rest of the SDK call works.

### Caching layers

| Layer | Storage | Key | Lifetime |
|---|---|---|---|
| Geometry (hot) | In-memory dict | `geometry_id` | Process lifetime |
| Geometry (warm) | `cache/{geometry_id}.json` | `geometry_id` | Manual `rm` |
| Weather TMY | In-memory dict | `(lon4, lat4, month, hour_start, hour_end)` | Process lifetime |
| Frontend geometry | Zustand `geometry` field | implicit via centroid | Cleared on `setCentroid` |

For a multi-worker deployment, promote the in-memory dicts to Redis. A medium-size geometry payload is typically 5–25 MB JSON (DotBim building meshes dominate); fits inside Redis's 512 MB value cap with room to spare. Create the disk cache directory at startup (`Path("cache").mkdir(exist_ok=True)`) — without it the first write raises `FileNotFoundError`.

### Shared helpers (define once, use everywhere)

Three small helpers prevent the "lon-by-cosine drift" most agents introduce:

```python
def meters_to_deg(lat: float, m: float) -> tuple[float, float]:
    """Returns (delta_lon, delta_lat) for `m` metres at `lat` degrees."""
    return (m / (111_320.0 * math.cos(math.radians(lat))),
            m / 111_320.0)

def build_square_polygon(centroid: tuple[float, float], half_m: float) -> dict:
    lon, lat = centroid
    dlon, dlat = meters_to_deg(lat, half_m)
    return {"type": "Polygon", "coordinates": [[
        [lon-dlon, lat-dlat], [lon+dlon, lat-dlat],
        [lon+dlon, lat+dlat], [lon-dlon, lat+dlat], [lon-dlon, lat-dlat],
    ]]}

def grid_bounds_from(polygon: dict, grid_shape: tuple[int, int],
                     cell_size_m: float = 1.0) -> list[float]:
    """Bounds describe the merged GRID (which ceil-rounds tile counts),
    not the polygon. Use polygon SW + grid shape × cell size."""
    ring = polygon["coordinates"][0]
    sw_lon = min(v[0] for v in ring[:-1])
    sw_lat = min(v[1] for v in ring[:-1])
    h, w = grid_shape
    center_lat = (sw_lat + max(v[1] for v in ring[:-1])) / 2.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(center_lat))
    return [sw_lon, sw_lat,
            sw_lon + (w * cell_size_m / m_per_deg_lng),
            sw_lat + (h * cell_size_m / 111_320.0)]
```

These keep the polygon, the snippet template's bbox, and `bounds` computation consistent — getting any one of them wrong by a cosine factor misaligns the heatmap by tens of metres at European latitudes.

**Imports** to surface in `main.py` / `dispatch.py`: `from infrared_sdk import InfraredClient`, `from infrared_sdk.models import TimePeriod, Location, extract_weather_fields`, `from infrared_sdk.analyses.types import ...` (the request classes, `AnalysesName`, `PwcCriteria`, `TcsSubtype`, `BaseAnalysisPayload`, `UtciModelBaseRequest`, `TcsModelBaseRequest`). `Location` lives under `infrared_sdk.models`, NOT the top-level `infrared_sdk` package.

### DotBim → footprint GeoJSON (the building outline trap)

`client.buildings.get_area(polygon).buildings` returns `dict[str, DotBimMesh]`. Each mesh's `coordinates` is a flat `[x, y, z, x, y, z, ...]` array in **polygon-bbox-SW local metres** — the origin `(0, 0)` is the SW corner of the polygon's bounding box, x points east, y points north, z is height. The frontend Scene needs WGS84 lon/lat polygons, so the back-projection is:

```python
import math
from scipy.spatial import ConvexHull, QhullError

def _hull_ring_xy(xs, ys):
    """Convex hull ring over (x, y); returns None on degenerate input."""
    pts = list({(round(x, 3), round(y, 3)) for x, y in zip(xs, ys)})
    if len(pts) < 3:
        return None
    try:
        hull = ConvexHull(pts)
    except QhullError:
        return None
    ring = [pts[i] for i in hull.vertices]
    ring.append(ring[0])
    return ring


def _bbox_ring_xy(xs, ys):
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max), (x_min, y_min)]


def building_footprint_geojson(mesh: dict, polygon: dict) -> tuple[dict, float] | None:
    """Returns (GeoJSON Polygon ring in WGS84, roof height in metres) or None
    for degenerate input. Convex hull by default; AABB fallback when scipy
    is missing or the hull degenerates (< 3 unique vertices / collinear)."""
    coords = mesh.get("coordinates") or []
    if not coords or len(coords) % 3 != 0:
        return None
    xs = coords[0::3]; ys = coords[1::3]; zs = coords[2::3]
    roof_m = float(max(zs)) if zs else 0.0
    # Some meshes only carry ground vertices (z ≈ 0). Floor at 3 m so DeckGL
    # extrudes them visibly instead of rendering a flat coloured pad.
    if roof_m < 0.5:
        roof_m = 3.0

    ring_xy = _hull_ring_xy(xs, ys) or _bbox_ring_xy(xs, ys)

    ring = polygon["coordinates"][0]
    sw_lon = min(v[0] for v in ring[:-1])
    sw_lat = min(v[1] for v in ring[:-1])
    center_lat = (sw_lat + max(v[1] for v in ring[:-1])) / 2.0   # match grid_bounds_from
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(center_lat))
    def m2ll(x_m: float, y_m: float) -> list[float]:
        return [sw_lon + x_m / m_per_deg_lng, sw_lat + y_m / 111_320.0]

    return ({
        "type": "Polygon",
        "coordinates": [[m2ll(x, y) for (x, y) in ring_xy]],
    }, roof_m)
```

Wrap into a `FeatureCollection` with `properties = { "height_m": h }` for the frontend's `PolygonLayer`. **Do not** ship raw DotBim coordinates to the browser — they're in local metres, not lon/lat, and DeckGL will render at the equator instead of the chosen centroid. A wrong back-projection (skipping the cosine factor or using polygon centre instead of SW corner) is the single most common silent failure mode, and the buildings will render visibly misaligned with the basemap.

**Why convex hull, not AABB.** AABB bleeds into adjacent courtyards / roads on every L-shaped / curved / rotated building (Burgtheater, Karlskirche, anything pre-1900). Server-side analysis clipping uses the real 3D mesh and KPIs aren't affected, but the *rendered* scene reads as "Lego brick city" — a recurring complaint we trace to this single choice. The function above already uses hull; this block is kept only for reference. `_hull_ring_xy` returns `None` on degenerate input (< 3 unique vertices, collinear), which is when the function silently falls back to AABB.

```python
# Reference only — already inlined above.
def _hull_ring_xy(xs, ys):
    pts = list({(round(x, 3), round(y, 3)) for x, y in zip(xs, ys)})
    if len(pts) < 3:
        return None
    try:
        hull = ConvexHull(pts)
    except QhullError:
        return None
    ring = [pts[i] for i in hull.vertices]
    ring.append(ring[0])
    return ring

ring_xy = _hull_ring_xy(xs, ys) or _bbox_ring_xy(xs, ys)
ring_lonlat = [m2ll(x, y) for x, y in ring_xy]
```

Smoke-tested in Vienna 1st: 91 % of meshes produce hull rings (avg 8.8 verts, max 29); the remaining 9 % are meshes where the hull legitimately equals a rectangle. Recompute footprints from the cached DotBim payload on every read (see "Caching layers" below) so swapping the projection algorithm doesn't bust the SDK cache.

Vegetation features arrive already in lon/lat (GeoJSON `Point` features keyed by OSM id) — no back-projection. Ground material features are lon/lat too. Only the DotBim building meshes need this conversion.

## Frontend patterns

### Zustand store shape

The store is built around two ideas:

1. **An explicit `flowState` state machine** for the location → load → run lifecycle. Every UI affordance gates on it; no implicit "did the network finish" derivation.
2. **Scenarios** as design variants. The user might start with a baseline (OSM-fetched buildings + trees + ground), fork it to "+10 trees on Maria-Theresien-Platz", then fork that to "remove the parking lot trees". Each variant owns its own tree overlay and its own per-analysis × per-area-size run cache. Three scenarios × seven analyses × two area sizes → 42 result slots, all independently cached and surviving area-size flips.

#### State machine

```
idle
   └ proposeCentroid()       → centroid_pending

centroid_pending
   ├ proposeCentroid()       → centroid_pending  (overwrite pending; abort in-flight fetch)
   ├ confirmAndLoad()        → loading_geometry
   └ discardProposal()       → idle | geometry_ready (whichever was prior)

loading_geometry
   ├ fetch success           → geometry_ready
   ├ fetch failure           → error
   └ proposeCentroid()       → centroid_pending  (abort current fetch)

geometry_ready
   ├ proposeCentroid()       → centroid_pending
   ├ areaSize flip (cached)  → geometry_ready    (silent; result slot exists)
   ├ areaSize flip (miss)    → loading_geometry  (no re-approval — centroid already confirmed)
   └ run()                   → running_analysis

running_analysis
   ├ run success             → analysis_ready
   └ run failure             → error (or geometry_ready if recoverable)

analysis_ready
   ├ proposeCentroid()       → centroid_pending
   ├ areaSize flip           → as per geometry_ready
   ├ setActive(id)           → analysis_ready (if cached) | geometry_ready
   └ run()                   → running_analysis

error
   ├ retryLoad()             → loading_geometry
   └ proposeCentroid()       → centroid_pending
```

Three centroid actions instead of `setCentroid`:

- `proposeCentroid(c)` — writes `pendingCentroid`, sets `flowState = 'centroid_pending'`, aborts any in-flight fetch. Does NOT touch `centroid` or caches.
- `confirmAndLoad()` — commits `pendingCentroid → centroid`, wipes `geometryBySize` + all `runs[]` (new polygon), starts the fetch.
- `discardProposal()` — clears `pendingCentroid`, returns to prior stable state.

Mid-flight cancellation uses a **module-level `AbortController`** (not in the store — AbortController isn't JSON-serialisable):

```ts
// playground/geometry-fetch.ts
let inFlightGeometryAbort: AbortController | null = null

export function abortInFlightGeometry() {
  if (inFlightGeometryAbort) { inFlightGeometryAbort.abort(); inFlightGeometryAbort = null }
}
```

```ts
type AnalysisId = '...'         // 7 entries from the registry
type AreaSize = 'small' | 'medium'
type ScenarioId = string        // generated UUID or human-readable slug
type FlowState =
  | 'idle' | 'centroid_pending' | 'loading_geometry'
  | 'geometry_ready' | 'running_analysis' | 'analysis_ready' | 'error'

/** Cache key. Use this everywhere — never index runs[] by analysisId alone. */
const runKey = (id: AnalysisId, size: AreaSize) => `${id}::${size}`

interface AnalysisEntry {
  params: Record<string, number | string>       // drives the next run
  resultParams: Record<string, number | string> // snapshot at submit time
  data: RunAnalysisResponse | null
  loading: boolean
  elapsed: number                               // seconds since loading→true (for progress bar)
  err: string | null
  stale: boolean                                // tree edit invalidated this entry
}

interface TreeAdd {
  id: string                                    // generated UUID (NOT an OSM id)
  lon: number
  lat: number
  height: string                                // string to match OSM convention ("12")
  diameter_crown: number                        // metres
  species?: string
  leaf_type?: 'broadleaved' | 'needleleaved'
}

interface Scenario {
  id: ScenarioId
  name: string                                  // user-editable: "Baseline", "+ trees, square"
  color: string                                 // hex — diff palette tag + UI chip
  trees: { added: TreeAdd[]; removed: string[] }  // removed = OSM ids to omit
  // Future overlay kinds — typed for forward compatibility. Add the editor
  // component + backend injection when wanted; the wire format already accepts
  // unknown keys (Pydantic v2 extra="ignore").
  buildings?: { overlays: BuildingOverlay[] }
  ground?: { overrides: GroundOverride[] }
  // Run cache keyed by `${analysisId}::${areaSize}` so flipping size doesn't
  // wipe results from the other size. setAreaSize → silent transition if
  // cached, else loading_geometry without re-approval.
  runs: Partial<Record<string, AnalysisEntry>>
}

interface GeometryBundle {
  geometry_id: string
  centroid: [number, number]
  half_side_m: number
  buildings: FeatureCollection
  vegetation: FeatureCollection
  ground: FeatureCollection
}

interface State {
  // ---- Centroid: confirmed (loaded) vs pending (awaiting Load click).
  //      Camera + preview ring follow `pendingCentroid ?? centroid`.
  centroid: [number, number] | null
  pendingCentroid: [number, number] | null
  areaSize: AreaSize
  active: AnalysisId
  flowState: FlowState

  // ---- Server-fetched geometry — cached per area size so flipping back
  //      to a previously-loaded size is instant (no refetch).
  geometryBySize: Partial<Record<AreaSize, GeometryBundle>>
  geometryLoading: boolean
  geometryErr: string | null

  // ---- Design variants
  scenarios: Record<ScenarioId, Scenario>
  scenarioOrder: ScenarioId[]                   // for the UI tab strip
  activeScenarioId: ScenarioId                  // the one currently in view
  compareWithId: ScenarioId | null              // when non-null: render diff or side-by-side
  editingScenarioId: ScenarioId                 // tree-tool writes go here (usually === active)

  // ---- Selection-level actions
  setActive: (id: AnalysisId) => void
  setAreaSize: (s: AreaSize) => Promise<void>   // auto-loads if not cached
  proposeCentroid: (c: [number, number]) => void
  confirmAndLoad: () => Promise<void>           // commits pending → fetch
  discardProposal: () => void                   // back to prior stable state
  retryLoad: () => Promise<void>                // error → loading_geometry
  run: () => Promise<void>                      // running_analysis → analysis_ready

  // ---- Scenario lifecycle
  createScenario: (name?: string) => ScenarioId
  forkScenario: (fromId: ScenarioId, name?: string) => ScenarioId
  deleteScenario: (id: ScenarioId) => void
  renameScenario: (id: ScenarioId, name: string) => void
  setActiveScenario: (id: ScenarioId) => void
  setCompareWith: (id: ScenarioId | null) => void
  setEditingScenario: (id: ScenarioId) => void

  // ---- Per-scenario actions
  setParam: (key: string, value: number | string) => void   // writes to active scenario
  addTree: (t: TreeAdd) => void                             // writes to editing scenario
  removeOsmTree: (osmId: string) => void
  unaddTree: (treeId: string) => void                       // undo a placed tree
  fetchGeometry: () => Promise<void>
  run: () => Promise<void>                                  // runs the active scenario × active analysis
  runAll: (scenarioId: ScenarioId) => Promise<void>         // re-run every cached analysis for a scenario
}
```

**State partition invariants** (an agent must enforce these or the model rots):

- `centroid`, `areaSize`, `active`, `geometry` are **shared** across all scenarios. Compare only makes sense on the same polygon × same analysis.
- `params`, `trees`, `runs` are **per-scenario**. Live in `Scenario`, never at the top level.
- `editingScenarioId` is usually equal to `activeScenarioId`, but can decouple when you want to "view A, edit B" (e.g. eye-dropper a value from one variant while pencilling another).

**Selectors** — colocate near the store and use narrow signatures so components re-render only when their slice changes:

```ts
const selectActiveScenario = (s: State) => s.scenarios[s.activeScenarioId]
const selectActiveEntry    = (s: State) => selectActiveScenario(s).runs[s.active]
const selectIsLoading      = (s: State) => !!selectActiveEntry(s)?.loading
const selectParams         = (s: State) => selectActiveEntry(s)?.params ?? {}
```

For multi-value selectors prefer `useShallow` from `zustand/react/shallow`. For nested updates (`scenarios[id].runs[analysis].data = ...`) the `immer` middleware is worth the extra import — without it the boilerplate dominates.

### Scenario management

Lifecycle the agent must wire up:

| Action | What it does |
|---|---|
| `createScenario(name?)` | Generates a new id (uuid), seeds with empty trees + empty runs, appends to `scenarioOrder`, doesn't switch focus |
| `forkScenario(fromId, name?)` | Deep-copies `trees` and `runs` from `fromId`, generates a new id, appends to `scenarioOrder`. Run caches stay valid as long as the trees and params match |
| `deleteScenario(id)` | Removes from `scenarios` and `scenarioOrder`; if it was active, falls back to the first remaining; refuse to delete the last scenario |
| `renameScenario(id, name)` | Inline-edit on the tab; persists; never touches data |
| `setActiveScenario(id)` | Switches the heatmap + the side-rail Inputs to that scenario. `editingScenarioId` follows unless the user has manually decoupled it |
| `setCompareWith(id \| null)` | Turns on side-by-side or diff rendering against scenario `id` |

**UI for scenarios** — a horizontal tab strip across the top (between the header and the canvas), one tab per scenario with the scenario name + a coloured dot + a small `×` to delete. A trailing `+ New variant` button calls `createScenario()`. Forking is reached via a contextual `⋯` on the active tab: "Fork from this".

**Tree drawing tool** — when the user enables tree mode, single-click on the map dispatches `addTree({ id: uuid(), lon, lat, height: '10', diameter_crown: 6, leaf_type: 'broadleaved' })`. Clicking on an existing OSM tree dispatches `removeOsmTree(osmId)`. Visual feedback: highlight `editingScenarioId`'s tabs while drawing so the user always knows which variant they're modifying.

**Run all scenarios** — for a fair "before/after" comparison you want the same analysis under every variant with consistent params. `runAll(scenarioId)` walks each cached analysis on a scenario and re-submits with that scenario's tree overlay. Throttle to one request in flight at a time; show a small progress badge per scenario tab.

**Save/share** — the store is JSON-serialisable (no `Set`, no `Map`, no class instances). Serialise `{ centroid, areaSize, active, scenarios, scenarioOrder, activeScenarioId }` to a URL fragment or a backend row. `geometry`, `data` (per-entry), and loading/error transients are session-only and **must be omitted** from the share blob — they're re-derivable from the centroid and re-runnable from the params.

### Invalidation rules (the part that catches every agent)

- `proposeCentroid(c)` → writes `pendingCentroid`, sets `flowState = 'centroid_pending'`, aborts any in-flight fetch via the module-level `AbortController`. **Does NOT touch** `centroid`, `geometryBySize`, or `runs`. Cheap; only the preview ring moves.
- `confirmAndLoad()` → copies `pendingCentroid → centroid`, clears `geometryBySize` and every `scenarios[*].runs[*]` (different polygon ⇒ everything stale), starts the fetch. Sets `flowState` accordingly.
- `setAreaSize(s)` → **does NOT wipe runs**. If `geometryBySize[s]` already exists, silently transitions `flowState`. If not, loads geometry for size `s` against the already-confirmed centroid (no re-approval — the centroid is unchanged, only the parameter changed).
- `setParam` → only mutates `runs[runKey(active, areaSize)].params`. Does NOT invalidate `data` — the displayed result reflects `resultParams`, not `params`.
- `addTree` / `removeOsmTree` / `unaddTree` → mutate the **editing** scenario's `trees`. Mark every entry in that scenario's `runs` as `stale: true` so the UI offers a "Re-run with new trees" affordance.
- In-flight cancellation: the module-level `inFlightGeometryAbort` controller is aborted on every new `proposeCentroid`. The `run()` action can hold a per-key controller in addition.

> **Watch out**: snapshot params at submit time into `resultParams`. Without this, the colour scale of the displayed result shifts the moment the user nudges a slider for the next run — visually jarring.
>
> **Watch out**: `useEffect(() => fetchGeometry(), [centroid])` is the old auto-fetch pattern — **don't do this**. It fires a 15-30 s SDK call on every keystroke into the lat/lon input. Use the explicit `proposeCentroid` → banner → `confirmAndLoad` flow instead.

### Analysis registry — single source of truth

Define one `AnalysisSpec` per analysis: `id`, `label`, `short`, `unit`, ordered `params[]`, and `infoMd`. The backend dispatches by string only — never duplicate the param specs in Python. Three param types are enough:

- `int-slider` — single integer, with `min/max/step/default/unit`.
- `int-range` — two thumbs sharing a row, writing to `key` and `endKey` with the constraint `end >= start + 1`.
- `select` — `<select>` with `{label, value}[]`.

A `resolveColorRange(id, params)` function returns the active `[min, max]` per analysis. Most analyses use a static range; daylight-availability resolves dynamically from `(days_in_month × hour_window_length)` or — preferred — the run's actual `dataMax`. **Ignore `min_legend`/`max_legend` from the SDK response** — they're often `null` or too tight, producing washed-out plots.

A `getColorScale(id, { params })` returns a function `(value) => [r, g, b, a]` over a 5-stop jet so the heatmap and the histogram share a palette. Anchor stops (RGB 0–255):

| t | colour | RGB |
|---|---|---|
| 0.00 | deep blue | `33, 102, 172` |
| 0.25 | cyan | `67, 162, 202` |
| 0.50 | green | `120, 198, 121` |
| 0.75 | yellow | `254, 224, 88` |
| 1.00 | red | `215, 48, 39` |

Lerp between adjacent stops. `null` / `NaN` cells return `[0, 0, 0, 0]` so the BitmapLayer renders them transparent (a grey "no data" fill makes the polygon edge read as a colour rather than a mask).

`ColorRangeParams` carries `{ month?, hour_start?, hour_end?, dataMin?, dataMax? }`. Only daylight currently consumes `dataMax`; the other fields exist to keep the type closed for future analyses (e.g. a per-run dynamic `dataMin` for divergent palettes in scenario-diff mode).

**`min_legend` / `max_legend` from the SDK** — the SDK README's recommendation is to use these as `zmin`/`zmax` when present (and fall back to `np.nanmin`/`np.nanmax` when `None`) — that's the right call for ad-hoc scripts plotting a single result in isolation. The playground deliberately **diverges** from this and uses static per-analysis ranges so the colour scale is stable across runs: switching from one wind run to another shouldn't recolour both, because the user is comparing against a fixed scale rather than against the previous run. This is a UX-driven choice for the playground, not a claim that the SDK's legend bounds are wrong — for one-off scripting use the SDK's bounds as the README recommends.

### Location picker pattern

A small `<aside>` floating top-right:

1. Search input wired to a 300 ms-debounced call to `https://nominatim.openstreetmap.org/search?q=...&format=json&limit=5`. List up to five hits as buttons; on click, call `setCentroid([parseFloat(lon), parseFloat(lat)])`.
2. Lat / Lon number inputs for direct entry — sync with `centroid`.
3. Map single-click handler on the DeckGL canvas dispatches `proposeCentroid` when tree-mode is OFF (and `addTree` when ON — see "Click semantics on the map" above). Double-click is kept as a redundant proposeCentroid trigger for muscle memory. **Never** call `confirmAndLoad` from a map click — the approval banner is the only commit affordance.
4. Status pill at the bottom: `Fetching layers…` / `{n} buildings cached` / a destructive caption on error.

Respect Nominatim's policy: identify with `Accept-Language` (browsers can't set a custom `User-Agent` — CORS blocks it; if you need a project-identifying UA, add a `GET /geocode?q=...` endpoint on the FastAPI backend that proxies the call with a `User-Agent: sdk-playground/0.1 (your-email@org.tld)` header). Debounce 300 ms and don't blast the public endpoint with autocomplete-on-every-keystroke. For production, swap to a managed geocoder (Mapbox, Google Places).

### Approval banner + area preview overlay

Expensive (15-30 s, billed) SDK fetches need an explicit user commit, not an auto-fetch on every centroid change. Two coupled pieces:

**Approval banner** — bottom-centre, `max-w-lg`, appears only when `flowState ∈ {centroid_pending, loading_geometry, error}`. Three visual states:

- `centroid_pending`: "Load area around this location?" + `(pending_lon, pending_lat)` + area-size segmented control (`500 m` / `1 km`) inline + `[Cancel]` (only if there's prior geometry) + primary `[Load area]` button. Pressing Load dispatches `confirmAndLoad()`.
- `loading_geometry`: spinner + "Fetching {500 m | 1 km} of geometry…"
- `error`: red ring + error message + `[Retry]` button → `retryLoad()`.

Move the `area_size` toggle here too (in addition to the SideRail). Size + commit are one decision; the user should make them in one place.

**Area preview overlay** — always-on map overlay showing exactly what gets fetched. Two `PolygonLayer`s on top of the basemap:

- `preview-square` — the polygon bbox actually sent to `client.run_area_and_wait` (amber fill+ring when pending, teal when confirmed).
- `preview-circle` — the inscribed-circle clip the heatmap will use (same colours, ring only, no fill).

```ts
const flatOffset = (idx: number) => [0, -idx * 100] as [number, number]
const previewCentroid = pendingCentroid ?? confirmedCentroid ?? null
const isPending = flowState === 'centroid_pending' || flowState === 'loading_geometry' || flowState === 'error'
const fill: [number, number, number, number] = isPending
  ? [245, 158, 11, 28]    // amber/12
  : [0, 166, 166, 18]     // teal/8
const line: [number, number, number, number] = isPending
  ? [194, 120, 3, 220]
  : [0, 130, 130, 200]
// PolygonLayer(preview-square): square ring at previewCentroid ± half_m
// PolygonLayer(preview-circle): 64-segment circle of radius half_m
```

Both layers are filtered by visibility of `previewCentroid` — show whenever any centroid (pending or confirmed) exists. Update the camera viewState to keep the preview centred and zoomed appropriately:

```ts
const zoom = areaSize === 'small' ? 15.6 : 14.6
// pendingCentroid wins over confirmed — camera moves immediately on search hit
useEffect(() => { setViewState({ ...vs, longitude: flyLon, latitude: flyLat, zoom,
    transitionInterpolator: new FlyToInterpolator({ speed: 1.5, curve: 1.4 }) }) },
  [flyLon, flyLat, areaSize])
```

**Stale-data suppression.** While `flowState === 'centroid_pending'` (or `loading_geometry` / `error`), **hide** the previous run's `buildings`, `osm-trees`, `ground`, and `heatmap` layers. Otherwise the old city's render persists over the new preview ring and confuses the eye. Don't wipe state — just don't render. Once `confirmAndLoad` runs, the cache is wiped and the new geometry renders cleanly.

### Click semantics on the map

With the approval banner in place, the map can be more permissive about clicks. The default that works:

- **Single click** (tree-mode OFF) → `proposeCentroid([lon, lat])`. Cheap; only the preview ring moves. User commits with the banner.
- **Single click** (tree-mode ON) → `addTree({...})`.
- **Double click** → `proposeCentroid` (kept for muscle memory). Disable DeckGL's `doubleClickZoom` so this gesture is free.
- **Drag** → pan. **Scroll** → zoom. Bearing fixed at 0°.

Wire a `treeMode: boolean` state up in `App.tsx`, gate the click handler at the dispatch site, and pass through to Scene. Don't rely on DeckGL to decide what a click means.

### Scene composition (DeckGL)

Layer order, bottom to top: basemap → preview ring → ground polygons → heatmap → OSM trees → buildings (extruded) → added trees → sampler overlay.

**Z-fighting fix** — every "flat" layer (basemap, preview ring/square, ground, heatmap, tree dots) lives at z = 0. Without a depth bias they fight for pixels on tilted views and flicker. Use deck.gl's `getPolygonOffset` to push each flat layer slightly toward the camera in depth space by its array index:

```ts
const flatOffset = (idx: number) => [0, -idx * 100] as [number, number]
// basemap: getPolygonOffset: () => flatOffset(0)
// preview-square: getPolygonOffset: () => flatOffset(1)
// preview-circle: getPolygonOffset: () => flatOffset(2)
// ground: getPolygonOffset: () => flatOffset(3)
// heatmap: getPolygonOffset: () => flatOffset(4)
// osm-trees: getPolygonOffset: () => flatOffset(5)
// buildings (extruded) — KEEP default depth test for self-occlusion
```

- **Camera (controlled, NOT `initialViewState`).** This is the most-broken pattern in DeckGL recipes. `initialViewState` is set once at mount and IGNORED on every subsequent change. Memoising it with `useMemo(() => ({...}), [])` freezes the camera at the first centroid forever — the user picks a new location, geometry loads off-screen, and it looks like "buildings missing." **Use `viewState` + `onViewStateChange` + a `useEffect` keyed on the centroid to drive a `FlyToInterpolator` transition.** Import: `import { FlyToInterpolator, MapView } from '@deck.gl/core'`. The interpolator instance is passed inside the `viewState` object (`transitionInterpolator`), not as a top-level DeckGL prop.
- **Basemap** — `TileLayer` over `https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png`, `tileSize: 256`, `renderSubLayers` returns a `BitmapLayer`. **Attribution is required**: render a `text-[9px] text-muted-foreground` overlay at `absolute right-2 bottom-2` reading `© OpenStreetMap contributors · © CARTO`. Without this, the deployment violates CARTO's free-tier terms and OSM's licence.
- **Preview ring/square** — see "Approval banner + area preview overlay" above.
- **Ground** — `PolygonLayer` with low-saturation per-material tints (`vegetation` → light green, `water` → light blue, `asphalt` → grey, `concrete` → off-white, `soil` → tan).
- **Heatmap** — `BitmapLayer({ pickable: true, opacity: 0.85, … })`. Image is a canvas built from the grid by walking `(value → colorScale(value))` into ImageData. **`pickable: true` is mandatory** — without it `info.bitmap.pixel` is `undefined` in `onHover` and the histogram cursor never lights up. Mask the alpha to an inscribed circle around the centroid with radius `half_side_m`.
- **Trees** — single `PolygonLayer` over a pre-baked canopy footprint for OSM trees + a second `PolygonLayer` (or `ColumnLayer` for 3D) tinted with the active scenario's colour for added trees.
- **Buildings (extruded)** — `PolygonLayer` with `extruded: true`, `getElevation: (f) => f.properties.height_m`, plus an inside-circle vs outside-circle filter so the focus matches the heatmap clip mask:

```ts
const r2 = half * half
const mPerDegLng = 111_320 * Math.cos(centroid[1] * Math.PI / 180)
const inside = (f: any) => {
  const [x, y] = f.geometry.coordinates[0][0]
  const dx = (x - centroid[0]) * mPerDegLng
  const dy = (y - centroid[1]) * 111_320
  return dx * dx + dy * dy <= r2
}
const heightRamp = (h: number) => {           // darker = taller
  const v = Math.max(190, Math.min(240, 240 - (h - 3) * 0.4))
  return [v, v, v - 4, 235] as [number, number, number, number]
}
// getFillColor: f => inside(f) ? heightRamp(f.properties.height_m) : [200, 200, 200, 80]
// updateTriggers: { getFillColor: [centroid[0], centroid[1], half] }
```

Inside-circle buildings render at full contrast with a height-keyed grey ramp; outside-circle buildings fade to ~30 % alpha for context only. This is the difference between "city dashboard" and "Lego prototype".

- **Scene lighting** — add a `LightingEffect` with an `AmbientLight` + a `_SunLight` for the architectural look. Without lighting every face of every building reads as the same RGB and the 45° pitch is wasted:

```ts
import { LightingEffect, AmbientLight, _SunLight } from '@deck.gl/core'
const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.0 }),
  sun: new _SunLight({
    timestamp: Date.UTC(2024, 5, 21, 12, 0),
    color: [255, 255, 255], intensity: 1.4,
    _shadow: true,
  }),
})
// <DeckGL effects={[lighting]} ... />
```

**Building occlusion**: cells inside building footprints come back as NaN from the SDK (cell-level point-in-polygon clipping happens server-side), so the heatmap naturally has a "hole" under every building. The 3D extruded buildings then sit in that hole — no rendering conflict, no need to special-case daylight / SVF. If you ever see heatmap colour bleeding *through* a building, the polygon filter on the building layer is off (most often: filtering by first-vertex of the ring vs. the centroid).

Pattern for the camera: controlled `viewState` driven through `onViewStateChange`, with a smooth fly-in. First mount → 2 s flight from a zoomed-out flat camera to the target zoom/pitch; subsequent area-size changes → 900 ms. Use `FlyToInterpolator({ speed: 0.6, curve: 1.4 })` for the first fly-in and `FlyToInterpolator({ speed: 1.6, curve: 1.41 })` for subsequent ones. Target zoom keyed to polygon size (`half ≤ 280 m → 16.5`, `≤ 520 m → 15.5`, else `14.8`). Gate the first fly-in on `geometry` being loaded so the centroid is stable — otherwise a fallback-bounds fly fires first and the user perceives the in-progress transition as broken. `controller: { dragPan: true, scrollZoom: true, doubleClickZoom: false }` — disabling double-click zoom frees the gesture for "pin a new location".

**Component-extraction hint**: `Scene.tsx` runs over the 150-line soft-limit fast. Extract `useDeckLayers(geometry, runData, hoverState)` returning `Layer[]`, and `useViewState(centroid, areaSize)` returning controlled-state + transitions, both into separate files (`playground/hooks/`).

### Inputs + Results side rail

A `w-64` flex column floated top-left with two cards:

**Inputs card**
- `INPUTS` caption + analysis label.
- 1-line tagline pulled from the registry (e.g. "Steady-state wind magnitude at pedestrian level").
- Area-size segmented control + Run button (swapped for an asymptotic progress bar while loading).
- A small line below: `~{N}s estimated` — set users' expectations.
- `ParamControls` renders the registry's `params[]` (driven UI; no per-analysis hard-coding).
- `<details>` for error messages — collapsed by default.

> A rich info popover (description + syntax-highlighted Python snippet + copy button) is **out of scope for v1**. The snippet endpoint still returns the code; surface it as a small "Show code" link that drops a plain `<pre>` block below the Inputs card if you want it accessible.

**Results card**
- `RESULTS` caption + area-size label.
- Primary KPI big number (`text-2xl`) with the unit small to the right.
- Distribution histogram (default) with a vertical cursor at the cell value the user is hovering on the Scene; bars coloured by midpoint through the same scale as the heatmap.
- Optional "Sample line" mode that swaps the histogram for a line-profile chart (single-click to add points, double-click / Enter to finish, Esc to cancel).

### Hover cursor pattern

A `useAnalysisHover(matrix)` hook owns `{ value, col, row } | null` and a callback wired into DeckGL's `onHover`. The handler reads `info.bitmap.pixel` for the `BitmapLayer`, converts to grid indices (`row = H - 1 - floor(py)` because y=0 is north), and reads the cell value. The hover info goes to `Histogram` as `cursorValue` — the histogram renders a 1px vertical line at `(value - rMin) / (rMax - rMin)` percent across.

### Model switcher

A horizontal chip bar at the bottom-centre, one button per `ANALYSIS_ORDER` entry. Active chip → primary fill; inactive → muted text. Pre-loaded analyses get a small dot indicator on the chip (only relevant if you implement the optional preload feature).

## UI / UX guidelines

The fastest way to a polished-feeling demo is restraint. Most "this looks AI-generated" failure modes come from too many borders, too much spacing, the wrong typography choice, or a palette mismatch between the heatmap and the chrome. Follow these.

### Palette

A muted teal accent on a near-white background reads as professional climate-analysis tooling. The default theme:

| Token | Value | Use |
|---|---|---|
| `background` | `#f7fafa` | Page background |
| `foreground` | `#092f32` | Body text — very dark teal |
| `card` | `#ffffff` | Inputs / Results / Picker cards |
| `border` | `rgba(0, 96, 101, 0.18)` | Card outlines + slider thumbs |
| `primary` | `#00a6a6` | Run button, active chip, slider track fill |
| `primary-foreground` | `#ffffff` | Text on primary |
| `muted` | `#e8f0f0` | Hover backgrounds |
| `muted-foreground` | `#355a5e` | Captions, slider min/max labels |
| `destructive` | `#b91c1c` | Error caption colour |

Configure in Tailwind v4 via `@theme` block in `globals.css`. Don't introduce a second accent colour — the heatmap already paints with five hues; the chrome stays monochrome teal.

### Typography

- One typeface: the system stack (`ui-sans-serif, system-ui, sans-serif`). Don't pull a web font.
- Tabular numerals on numeric KPIs (`font-mono tabular-nums`) so the large KPI value doesn't reflow when digits change.
- Three sizes inside the cards: caption (`text-[11px] uppercase tracking-wider font-semibold`), body (`text-sm`), KPI (`text-3xl font-semibold tabular-nums`). The earlier rule (caption `text-[10px]`, body `text-xs`, KPI `text-2xl`) is wrong at this card width — cards look toy-sized. Avoid `text-base` body — it tips into "form", not "tool".

### Spacing & containers

- Card padding: `p-5`. Internal sections separated by `border-t border-border/50 pt-3`, not by extra margin.
- Card outline: `rounded-lg ring-1 ring-border shadow-xl bg-background/95 backdrop-blur-md`. The semi-transparent background + backdrop-blur is the single most important visual trick — it makes the cards feel like they float over the 3D scene instead of sitting on top of it.
- Card widths: side rail is `w-80` (320 px). LocationPicker is the same. The earlier guideline of `w-64` was too tight — captions wrap, sliders feel cramped, the Run button is fingernail-sized. `w-80` is the new default; don't go wider — the scene is the point.
- Card padding: `p-5`. Internal sections separated by `border-t border-border/50 pt-3`.
- No nested borders. One ring per card, no inner ruled-off boxes.

### Sliders

The default `<input type="range">` looks like a 2008 form. Three rules:

1. Set `appearance: none; -webkit-appearance: none; background: transparent;` on the `<input>` itself. Without it Firefox renders the browser default and ignores the pseudo-elements.
2. Style WebKit (`::-webkit-slider-runnable-track` + `::-webkit-slider-thumb`) and Mozilla (`::-moz-range-track` + `::-moz-range-thumb`) in **separate** selectors. Browsers ignore combined pseudo-element rules.
3. Drive the track fill from a CSS variable so the component just sets `style={{ '--slider-fill': `${pct}%` }}`.

```css
/* globals.css */
input[type="range"].infrared-slider {
  -webkit-appearance: none; appearance: none;
  background: transparent;
  height: 1rem;
}
input[type="range"].infrared-slider::-webkit-slider-runnable-track,
input[type="range"].infrared-slider::-moz-range-track {
  height: 6px; border-radius: 9999px;
  background: linear-gradient(
    to right,
    var(--color-primary) 0%,
    var(--color-primary) var(--slider-fill, 0%),
    var(--color-muted) var(--slider-fill, 0%),
    var(--color-muted) 100%
  );
}
input[type="range"].infrared-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px; border-radius: 9999px;
  background: var(--color-card);
  box-shadow: 0 0 0 1px var(--color-primary), 0 1px 2px rgba(0,0,0,0.15);
  margin-top: -4px;
}
input[type="range"].infrared-slider::-moz-range-thumb {
  width: 14px; height: 14px; border-radius: 9999px;
  background: var(--color-card);
  box-shadow: 0 0 0 1px var(--color-primary), 0 1px 2px rgba(0,0,0,0.15);
  border: none;
}
```

The component computes `pct = ((value - min) / (max - min)) * 100` and clamps to `[0, 100]`.

### Buttons

- Run button: `bg-primary text-primary-foreground rounded-md px-4 h-8 text-sm font-medium`. Add a subtle glow ring on hover (`hover:shadow-[0_0_0_3px_rgba(0,166,166,0.18)]`) — sells the "primary action" feel without resorting to a saturated colour. The earlier `px-3 h-7 text-xs` looked toy at full card width.
- Secondary action chips (ModelSwitcher): `py-1.5 text-sm` (was `py-1 text-[11px]`). Inactive is `text-foreground hover:bg-muted`, active is `bg-primary text-primary-foreground`. No outline; no shadow.
- Icon-only buttons (eraser, sampler-toggle): `inline-flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground`.

### Heatmap rendering

- Always render the heatmap inside the inscribed circle around the polygon centroid. A square heatmap on a round scene looks unfinished.
- BitmapLayer opacity `0.85` (not 1.0). The basemap underneath shines through just enough for the user to ground themselves in the city.
- Drop opacity to `0.18` when a line-profile sampler is active so the line-and-bars overlay reads cleanly.
- NaN cells must be fully transparent (alpha 0), not a neutral grey. A grey fill makes the polygon edge look like a colour rather than a mask.

### Scene "feel"

- First-mount fly-in: ~2 s from a flat, zoomed-out camera to the target zoom + 45° pitch. `FlyToInterpolator({ speed: 0.6, curve: 1.4 })`. Subsequent area-size changes: 900 ms.
- Bearing fixed at 0°. Free rotation makes urban diagnostics hard to compare.
- Disable double-click zoom (`doubleClickZoom: false`) — double-click is the location-picker pin-drop. Keep `dragPan` and `scrollZoom`.

### Histogram

- Bars sit on a `flex items-end` row with `gap-px` between them. 20 bins.
- Bar colour: pass the bin midpoint through the same colour scale as the heatmap. **Critical** — a histogram with rainbow bars matching the heatmap reads as one composition; a histogram with grey bars reads as a separate chart that happens to be there.
- Show the resolved `[min, max]` and unit underneath in `text-[9px] text-muted-foreground`. Skip a y-axis label; the bar height is self-explanatory.
- Cursor: a 1px vertical line at `(cellValue - rMin) / (rMax - rMin)` across the bar area. `bg-foreground/60`. Snap to `null` when the pointer leaves the heatmap.

### KPI strip

- Caption (`text-[9px] font-semibold uppercase tracking-wider text-muted-foreground`).
- Value (`text-2xl font-semibold leading-tight text-foreground tabular-nums`).
- Unit immediately to the right of the value, `text-xs font-normal text-muted-foreground`.
- For PWC, display the mode class as an integer (0–4); for solar-radiation total kWh, comma-group with `toLocaleString`. Two decimals max for everything else.

### LocationPicker

- Search input: `<Search>` icon absolute-positioned inside, `pl-7 pr-2 py-1.5 text-xs`.
- Suggestion dropdown: `text-xs`, max 5 hits, truncate long display names.
- Status pill bottom-right of the picker card: spinner + "Fetching layers…" while loading, "{n} buildings cached" on success, destructive caption on error. Always present so users know what state they're in.

### Loading + error states

- No layout shift between "loading" and "loaded" — reserve space for the Run button / progress bar.
- Errors collapse into `<details>` with the human-readable summary visible and the raw error in a `<pre>` underneath. Never show a stack trace at the top level.
- A first-paint state where geometry hasn't loaded yet: show the basemap + a faint dashed circle where the polygon will be once geometry arrives. Don't show an empty grey card.

### Anti-patterns

- ❌ Multiple accent colours (a red Run button next to a blue Save button next to a green Done).
- ❌ Drop shadows on every element. One shadow per card is enough.
- ❌ `border` + `ring` on the same element (`ring` is implemented as a box-shadow — pairing it with a hard `border` creates two outlines). The recommended `shadow-xl ring-1` combo is fine — those are layered box-shadows that read as one elevation.
- ❌ `text-base` body text. Reads as "form" rather than "tool".
- ❌ Auto-rotating camera. Confuses urban diagnostics.
- ❌ A square heatmap on a round scene.
- ❌ A grey "no data" fill for masked cells.
- ❌ Toast notifications for routine SDK responses. The KPI strip is already feedback.
- ❌ Histogram bars sized in pixels. Use `height: calc(count / maxCount * 100%)` inside a fixed-height container; pixel heights overflow on high counts and disappear on low ones.

## Things to watch out for

0. **SDK version pin** — `infrared-sdk >= 0.4.8`. Older pins miss the big-payload envelope, ground-materials name validation, `AreaResult.bounds`, and `directional_blend` merge.
0a. **SVF returns 0–100** — colour-scale range must be `[0, 100]`; `[0, 1]` paints solid red. Treat the unit as `%`.
0b. **Always pass `preview_area(polygon, analysis_type=...)`** — omitting `analysis_type` defaults to the wind grid (256 m step) and under-counts solar/UTCI/TCS tiles by ~4×. Required since 0.4.3.
0c. **`area.buildings` items are Pydantic models** (`DotBimMesh`). Naive `json.dumps` on the disk cache raises `TypeError: Object of type DotBimMesh is not JSON serializable`. Call `.model_dump()` before writing.
0d. **`uvicorn` only loads `.env` when launched from `backend/`** — `dotenv.load_dotenv()` resolves the file relative to cwd. Either run from `backend/` or pass `--env-file backend/.env`.

1. **`bounds` describe the merged grid, not the polygon.** SDK ceil-rounds tile counts; merged grid is larger. Use `grid_bounds_from(...)`. Polygon corners off-set the heatmap by tens of metres.
2. **NaN → `null` on the wire.** `JSON.stringify(NaN)` is non-portable. Walk the grid in Python; frontend treats `null` as masked.
3. **Multi-month TimePeriod is rejected server-side** for SIX analyses (everything that takes a TimePeriod): PWC, solar-radiation, UTCI, TCS, daylight-availability, direct-sun-hours. The constraint is documented in `../03-time-period.md`, `../interpretation/solar-results.md`, and the per-analysis files. Always `end_month == start_month`. Only `wind-speed` and `sky-view-factors` are exempt (they take no TimePeriod).
4. **Hour window monotonicity**: `hour_start < hour_end`. Enforce in the `int-range` slider and at the backend.
5. **Tree property names follow OSM**: `properties.height` (string!), `diameter_crown`, `species`, `leaf_type`, `leaf_cycle`, `natural`. User-added trees **must** use the same keys — `height_m` will be silently dropped by the inference layer. Parse `height` with `parseFloat` when reading from the frontend.
6. **Enum convention is kebab-case values.** `PwcCriteria("lawson-2001")`, `TcsSubtype("thermal-comfort")`. Snippet templates must use the same form — mixing enum names and values produces unrunnable snippets.
7. **Snippets must be copy-runnable.** Templates include polygon construction inline; otherwise `client.run_area_and_wait(req, polygon, ...)` raises `NameError` on paste.
8. **Snapshot params at submit time** (`resultParams`). The displayed result's colour scale must reflect the request that produced it.
9. **`area.buildings` is a `dict`, not a list.** Iterate `.values()` when projecting to GeoJSON; pass the dict itself to `run_area_and_wait(buildings=...)`.
10. **`vegetation` and `ground_materials` are opt-in.** Pass `{}` or omit to skip. Thermal and solar runs are materially more accurate with both; wind and SVF generally don't need them.
11. **PWC needs `extract_weather_fields(...)`** and `**wind_fields` splat. UTCI / TCS / solar-radiation use `from_weatherfile_payload(...)` instead — it extracts internally.
12. **`wind_speed: int 1–100`** — Pydantic rejects floats; cast before constructing the request.
13. **Heatmap circle clip uses the polygon centroid + `half_side_m`**, not the grid bounds centre. Grid extent ≠ polygon extent.
14. **`pickable: true` on the heatmap `BitmapLayer`** — without it `info.bitmap.pixel` is `undefined` in `onHover` and the histogram cursor never lights up.
15. **Histogram cursor position** uses the `edges[0]..edges[-1]` range, not `resolveColorRange`. For daylight, the dynamic ceiling can differ from the bar edges — keep the two formulas separate.
16. **Cold-start latency** adds 2–5 s on first request. Realistic wall-clock: 15–30 s for cold `small` wind-speed, 5–15 s warm. Hide behind a "Fetching layers…" pill.
17. **Centroid rounding before cache hashing.** Round to 6 decimals before hashing the geometry-id and the weather-cache key.
18. **CORS in production**: `allow_origins=[os.getenv("FRONTEND_ORIGIN")]`. Hard-coded `*` breaks the moment the frontend deploys.
19. **Stable references for DeckGL layers.** `useMemo` keyed on the inputs that actually changed. Without memoisation DeckGL rebuilds the WebGL pipeline every render.
20. **Zustand middleware setup**: `create<State>()(subscribeWithSelector((set, get) => ({...})))` — note the double-paren curry. With `immer`: `create<State>()(subscribeWithSelector(immer((set) => ({...}))))`.
21. **First fly-in waits for geometry.** Gating the camera animation on `geometry !== null` prevents the fallback-bounds flight from interrupting the real one.
22. **In-flight cancellation.** Hold an `AbortController` per `(scenarioId, analysisId)` in the store. `setCentroid` aborts the current `/fetch_geometry`; a new `run()` aborts its predecessor. The `runId` counter is the cheap fallback.
23. **Scenario diff invariants.** `bounds_A == bounds_B`, `gridA.shape == gridB.shape`, same `analysis_type`. NaN on either side → `null` in the diff. Range symmetric around 0 (`±max(|d|)`).

## Extensions

The store and wire format are designed so these additions land in a handful of files.

### Side-by-side / diff rendering between scenarios

The store already keys runs and trees per scenario (`scenarios[id].runs[analysis]`, `scenarios[id].trees`). Two presentations are useful:

- **Side-by-side** — render two `<Scene>`s in a 1fr/1fr grid, both driven by the same `centroid`, `areaSize`, and `active` analysis but reading from different `scenarios[id]`. Use the scenario's `color` as a top-of-canvas tag chip.
- **Diff layer** — compute `gridA - gridB` on the client, send through a divergent palette (blue → white → red) with a range symmetric around 0 (`±max(|d|)`). Replace the heatmap BitmapLayer with the diff layer when `compareWithId !== null`. Refuse to render unless the invariants in pitfall #23 hold.

A small "Run all" affordance on each scenario tab calls `runAll(scenarioId)` so the user can iterate on tree placement without manually re-running each analysis under each variant.

### Tree-placement before / after

The Zustand store ships with the bookkeeping. The wiring:

1. **UI** — a "Place tree" toggle in the side rail. While active, single map-click dispatches `addTree({ id: uuid(), lon, lat, height: '10', diameter_crown: 6, leaf_type: 'broadleaved' })`. Click on an existing OSM tree dispatches `removeOsmTree(osmId)`. Visual feedback: outline the `editingScenarioId` tab while drawing.
2. **Wire** — `/run_analysis` payload carries `trees_added` and `trees_removed` arrays alongside `params`.
3. **Backend** — fold the overlay into the cached vegetation dict before the SDK call:

   ```python
   veg = {**cached_geometry["vegetation"]}            # shallow copy
   for osm_id in req.trees_removed:
       veg.pop(osm_id, None)
   for t in req.trees_added:
       veg[t.id] = {
           "type": "Feature",
           "geometry": {"type": "Point", "coordinates": [t.lon, t.lat]},
           "properties": {
               "natural": "tree",
               "height": str(t.height_m),              # OSM string convention
               "diameter_crown": t.crown_diameter_m,
               "species": t.species,
               "leaf_type": "broadleaved",
           },
       }
   # Pass `veg` directly to the SDK call:
   result = client.run_area_and_wait(
       sdk_request, polygon,
       buildings=buildings, vegetation=veg or {}, ground_materials=ground or {},
   )
   ```

4. **Workflow** — fork the baseline scenario into "+ trees", place trees in the new one, hit `runAll` on both, render the diff. The diff layer answers "where did the trees reduce UTCI / wind / direct sun?".

### Add an eighth analysis surface (`direct-sun-hours`)

The backend already dispatches it. To surface in the UI: add `'direct-sun-hours'` to the `AnalysisId` union, the `ANALYSES` record, `ANALYSIS_ORDER`, and `STATIC_RANGE`. The driven-UI machinery picks it up automatically.

### Async runs + webhooks

For 1.5 km+ polygons the synchronous `run_area_and_wait` runs 30–60 s. Switch to `client.run_area(...)` returning an `AreaSchedule`, persist the schedule, and stream per-tile completions back over SSE / WebSocket so the user sees the heatmap fill in tile-by-tile.

### Save / share a scenario

The store is JSON-serialisable. Encode `{ centroid, areaSize, active, scenarios, scenarioOrder, activeScenarioId }` into a URL fragment or a backend row. `geometry`, `data` (per-entry), and loading transients are session-only — drop them from the share blob. On load, re-fetch geometry from the centroid and let the user re-run any analyses they want fresh.

## Out of scope (deliberately)

- **Custom interpolation / smart-blend wind merger.** Experimental, unvalidated against measurements, not part of the public SDK. Use the standard SDK merger.
- **Iframe embed handshake.** Only relevant for embedding the playground inside a marketing page. Skip for v1.
- **Async + webhook delivery.** Only worth the engineering when polygons exceed ~1 km.
- **Mobile-first stacked layout.** v1 targets desktop; `useMediaQuery('(min-width: 768px)')` to gate is a one-evening add later.
- **Server-side multi-month aggregation.** Server rejects multi-month windows; loop on the client if you really need it.

## Deployment

- **Local dev** — `uvicorn main:app --reload --port 8000`, `npm run dev` on the frontend.
- **Docker** — single image: copy backend, `pip install`, `CMD uvicorn main:app --host 0.0.0.0 --port 8000`. Pass `INFRARED_API_KEY` at runtime.
- **Fly.io / Railway / Render** — point at the Dockerfile, set `INFRARED_API_KEY` as a secret.
- **Modal** — wrap the FastAPI app with `@modal.asgi_app()`; mount `INFRARED_API_KEY` via `modal.Secret.from_name(...)`.
- **Cloudflare Pages** for the frontend bundle + any of the above for the backend; set `VITE_API_URL` at build time.

CORS: open during dev; locked to the deployed frontend origin in prod.

## Acceptance checklist

Before declaring the app done:

- The user can type a city into the search box, pick a hit, and watch a 3D scene of buildings + trees + ground render in ≤ 30 s for a fresh location.
- The user can double-click anywhere on the map to re-centre the playground and re-fetch geometry.
- All seven analyses run successfully against at least three different European cities at `small` size.
- The heatmap aligns visually with the buildings — the round clip mask, the BitmapLayer bounds, and the inscribed circle around the polygon centroid all agree.
- The histogram cursor follows pointer hover on the Scene.
- The InfoPopover snippet, when copied into a fresh Python environment with `INFRARED_API_KEY` set, reproduces the run without modification.
- A 1 km daylight-availability run renders a gradient (not a flat colour) — confirms the dynamic colour-range resolver is wired.
- Switching analyses preserves each analysis's cached result; switching back is instant.
- Network errors surface in a collapsible `<details>` rather than a full-screen overlay.

## Final functional checklist — verify before declaring done

Answer each as **yes / no / N/A** by **inspecting the running app** (or the code if there's no doubt). Don't tick from intent. A "no" anywhere here is a regression an end-user will hit.

### State machine + flow

1. **Is `flowState` an explicit enum** (`idle | centroid_pending | loading_geometry | geometry_ready | running_analysis | analysis_ready | error`) — and not an implicit derivation from "is `geometry` non-null"?
2. **Does the Run button gate on `flowState ∈ {geometry_ready, analysis_ready}`** — i.e. is it disabled while geometry is loading, missing, or errored?
3. **Does every centroid input** (Nominatim hit click, Lon/Lat number input, single map click) **call `proposeCentroid` and NOT auto-fetch?** Type two digits in the Lat field and confirm no network request fires.
4. **Does the approval banner appear** at the bottom of the viewport in `centroid_pending`, and disappear after `confirmAndLoad`?
5. **Is there a module-level `AbortController`** that aborts the in-flight fetch when a new `proposeCentroid` arrives mid-flight? (Test: click Load, then immediately propose a different city — first fetch should cancel, second should run.)

### Caching

6. **Are analysis results cached per `(scenario × analysis × area_size)`?** Run SVF at 500 m → flip to 1 km → flip back to 500 m → does the original SVF result reappear instantly with no refetch?
7. **Is geometry cached per `(centroid × area_size)`?** Load 500 m → flip to 1 km (auto-load) → flip back to 500 m → no refetch?
8. **Does the backend re-derive building footprints from the cached DotBim payload on every read?** Toggle bbox → hull in `geometry.py` and confirm the change applies without re-paying the SDK fetch.
9. **Does `proposeCentroid → confirmAndLoad` (a new polygon) wipe every cached run?** No stale Vienna SVF in the Berlin scenario after relocation?
10. **Is the centroid rounded to 6 decimals before hashing the geometry_id?** Otherwise the geocoder's last-digit jitter blows the cache on repeat queries.

### Visual / map

11. **Is the area preview overlay (square + circle) visible at the active centroid before fetch?** Amber while pending, teal once confirmed?
12. **Does the area-size selector live inside the approval banner** (in addition to the SideRail) so the user picks size + commit in one place?
13. **Are building footprints rendered as 2D convex hulls** (not AABBs)? Verify by checking ring lengths server-side: > 5 vertices for non-rectangular blocks, or visually — Rathauspark / Volksgarten read as park, not grey rectangles.
14. **Are buildings inside the inscribed circle full-contrast** (height-tinted opaque), **outside the circle faded** to ~30 % alpha for context?
15. **Is the camera controlled** via `viewState` + `onViewStateChange` + `FlyToInterpolator` — **NOT `initialViewState`** with empty-deps `useMemo`? (The latter is the most common camera-freeze bug.)
16. **Does every centroid change trigger a fly-in animation** (≥ ~900 ms), with zoom keyed to area size (≈ 15.6 for 500 m, ≈ 14.6 for 1 km) so the preview ring fits the viewport?
17. **Are flat layers z-biased via `getPolygonOffset`** to prevent flicker on tilted views?
18. **Is the heatmap masked to an inscribed circle around the centroid** (alpha 0 outside), and is `pickable: true` set on the BitmapLayer?
19. **Is stale geometry suppressed during `centroid_pending`?** Pick a new city — old buildings/heatmap should hide; only the basemap + new preview ring should remain.
20. **Is scene lighting wired** (`LightingEffect` + `AmbientLight` + `_SunLight`)? Faces of buildings should differ in shade.

### Registry / extensibility

21. **Is there a single backend `AnalysisSpec` registry** binding builder + kpis + snippet + unit + needs_weather — and NOT six parallel string-keyed tables?
22. **Is there a single frontend `ANALYSES: Record<AnalysisId, AnalysisSpec>` registry** that drives ParamControls, ModelSwitcher, ColorScale, KPI labels — nothing duplicates analysis metadata across components?
23. **Can you add a new analysis end-to-end with ≤ 6 touchpoints?** (1 BE registry entry + builder/kpis/snippet/imports fns + 1 FE registry entry).
24. **Is there a `/analyses` introspection endpoint** that returns the catalogue?
25. **Are wire-format strings consistent** between the FE `AnalysisId` union and the BE `ANALYSES` keys? (No silent 400s when clicking an analysis whose key has a typo on one side.)
26. **Does `ParamSpec` cover the param kinds you actually need today** (at least `int-slider`, `int-range`, `select`)? Forward-declared `float-slider` / `boolean` / `multi-select` / `text` are fine if you don't use them yet.

### Forward compatibility / scenarios

27. **Does the Scenario type include optional `buildings.overlays` and `ground.overrides` slots** even if there's no UI yet? Adding the editor later should not require schema changes.
28. **Does scenario fork deep-copy `trees` and `runs`** without sharing references? Modifying the fork's tree array must not mutate the parent's.

### Error handling + snippets

29. **Does the error state surface in the banner with a Retry button**, not a full-screen overlay or alert?
30. **Are network errors collapsed into `<details>`** in the SideRail (not always-visible stack traces)?
31. **Does the per-analysis Python snippet include the polygon construction inline** so it pastes-and-runs in a fresh Python with only `INFRARED_API_KEY` set? (Test: copy the snippet, save as `/tmp/snippet.py`, run with the venv — should print `result.grid_shape`.)

### Misc

32. **Does the SideRail step-line read** `Step 1 / 3 → Step 2 / 3 → Step 3 / 3` matching `flowState` transitions, so the user always knows what's next?
33. **Are card / type sizes legible?** `w-80` not `w-64`; `text-sm` body not `text-[10px]`; `text-3xl` KPI not `text-2xl`; Run button `h-8` not `h-7`.

If you scored 100 %, ship it. If you scored 80 %+, the gaps are probably documented or out-of-scope — flag them in your handover. Below 80 %, the build is regressing one of the patterns the recipe spent pages establishing.

## Related references

- [`../00-setup.md`](../00-setup.md) — install + auth.
- [`../05-area-api.md`](../05-area-api.md) — Area API, tiling, AreaResult.
- [`../byo-inputs.md`](../byo-inputs.md) — buildings / vegetation / ground_materials payload shapes.
- [`../03-time-period.md`](../03-time-period.md) — TimePeriod semantics + single-month constraint.
- [`../analyses/`](../analyses/) — per-analysis payload + interpretation references.
- [`gradio-area-explorer.md`](./gradio-area-explorer.md) — simpler Gradio counterpart (single-process Python).
