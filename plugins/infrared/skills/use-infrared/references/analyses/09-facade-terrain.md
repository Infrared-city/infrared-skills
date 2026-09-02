# Facade & Terrain Analysis (analysis-surfaces / sensor-points / ground-geometry)

Analyse **building surfaces** (facades, roofs) or **arbitrary sensor points** instead of the default 512x512 ground grid, and drape results over **terrain geometry**. Requires `infrared-sdk >= 0.4.12`.

Facade/BYO-sensor fields work on the 4 raytraced solar-family models ONLY: `sky-view-factors`, `solar-radiation`, `direct-sun-hours`, `daylight-availability`. Terrain fields additionally work on `thermal-comfort-index` / `thermal-comfort-statistics`.

## The five geometry channels

Sensors land in exactly one place per request — ground grid, `analysis_surfaces`, `sensor_points`, or the interior `daylight-factor` model; see *Where do the sensors go* in [`SKILL.md`](../../SKILL.md). Geometry gets there through five channels, and the three mesh channels are **not** interchangeable:

| Channel | Role | Put here |
|---|---|---|
| `geometries` (payload) / `buildings=` (`run_area*`) | **Analysed.** Sensors land on these in surface mode; their footprints are masked on the grid. | buildings only |
| `context_geometry` | **Occluder.** Traced for shadow, never analysed, never carries a sensor. | neighbours, distant ridges and towers, flyovers |
| `ground_geometry` | **Terrain.** Drape surface + occluder, never analysed. | the DEM / the BIM Mesh's top surface |
| `vegetation` | GeoJSON Point features, lon/lat | trees |
| `ground_materials` | GeoJSON polygons per material, lon/lat | asphalt · concrete · soil · vegetation · water |

All three mesh channels take `{id: {"coordinates": [x, y, z, …], "indices": […]}}` in metres, origin at the polygon-bbox SW corner, `+x` east, `+y` north, `z` up. `run_area*` re-frames them per tile; you never do. Per analysis: the two wind models take `geometries` only (no terrain, no occluders, no surface mode); the four raytraced solar models take everything; UTCI/TCS take `ground_geometry` but **not** `context_geometry` or `analysis_surfaces`.

**Terrain never goes in `geometries`.** It is accepted, billed, and returns a shattered mesh: surface synthesis clusters faces into flat regions (same normal within 5°, same plane within 2 cm), which a TIN fails on nearly every edge. Measured on three ArchiCAD terrains (2026-09-02): 242 / 85 / 47 up-facing triangles became **153 / 34 / 9 independent surfaces**, each gridded and clipped on its own, with the underside gridded too — seams on every edge, holes where a region keeps no cell. Put it in `ground_geometry`: the ground grid drapes onto it automatically ([*Results on the ground, with terrain*](#results-on-the-ground-with-terrain)).

## Request

```python
from infrared_sdk import InfraredClient, SurfaceAnalysisResult
from infrared_sdk.analyses.types import SvfModelRequest, AnalysesName

payload = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    analysis_surfaces="facades",   # or "roofs" / "all"
    surface_grid_size=1.0,         # sensor spacing on each surface, metres (>= 0.25)
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

**"My design, in its real neighbourhood"** — the cheap pattern for surface mode. Cost scales with the surfaces you *ask for*, not with how much city you send, so put the one building you are designing in `geometries` and everything else in `context_geometry`:

```python
payload = SolarModelRequest(
    analysis_type=AnalysesName.direct_sun_hours,
    latitude=48.195, longitude=11.570, time_period=tp,
    geometries={"my_design": design_mesh},        # analysed — this is the bill
    context_geometry=neighbour_meshes,            # {id: mesh} — shades, never analysed
    ground_geometry={"terrain": terrain_mesh},    # seats the scene, never analysed
    terrain_alignment="auto-align",
    analysis_surfaces="all", surface_grid_size=1.0,
)
result = client.run_area_and_wait(payload, polygon)   # geometries is in the payload: no buildings= kwarg
```

Measured (2026-09-02, 1 June 06:00–20:00, 1 m grid): 793 context triangles + 85 terrain triangles shading **one building → 1 664 sensors on 13 surfaces, 1 job, 2.4 s**. Result keys are your ids (`"my_design/<index>"`), so `result.surfaces` and `result.aggregates` map straight onto the element you submitted.

Bring-your-own sensors instead of surface synthesis (mutually exclusive with `analysis_surfaces`). **Single-tile only** — submit via the job primitives, NOT `run_area_and_wait` (which rejects `sensor_points` with a `ValueError`):

```python
payload = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    geometries=area.buildings,
    sensor_points=[[105.0, 99.9, 1.5], [105.0, 99.9, 4.5]],   # tile-local metres
    sensor_normals=[[0.0, -1.0, 0.0], [0.0, -1.0, 0.0]],      # optional, non-zero
)
job = client.analyses.execute(payload=payload)
completed = client.jobs.wait_for_completion(job.job_id, timeout=120)
raw = client.jobs.decompress(client.jobs.download_results(completed.job_id).content)
raw["output"]   # flat per-sensor list, one value per sensor in input order
```

Terrain draping (all six raytraced models, including UTCI/TCS).

**The SDK does not fetch terrain.** There is no terrain client and no DEM service — `ground_geometry` is bring-your-own, always. Omitting it is not an error: you get a flat plane at z = 0 and a perfectly normal-looking result.

`terrain_mesh` is one flat `{coordinates, indices}` mesh (the same shape as `buildings`, *not* the nested interior-entity shape), in **metres on the polygon-bbox-SW frame** that `area.buildings` uses: origin at the SW corner of the polygon's bounding box, `+x` east, `+y` north, `z` on the same datum as the building meshes. This turns any elevation array into it:

```python
import numpy as np

def terrain_mesh_from_grid(elevation, x0=0.0, y0=0.0, step=10.0):
    """(ny, nx) heights in metres -> one flat SDK mesh, CCW seen from above.
    elevation[j, i] is the height at (x0 + i*step, y0 + j*step)."""
    elevation = np.asarray(elevation, dtype=float)
    ny, nx = elevation.shape
    gx, gy = np.meshgrid(x0 + step * np.arange(nx), y0 + step * np.arange(ny))
    coords = np.stack([gx, gy, elevation], axis=-1).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1))
    a = (j * nx + i).ravel()
    b, c, d = a + 1, a + nx, a + nx + 1
    tris = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c], 1)])
    return {"coordinates": coords.ravel().tolist(), "indices": tris.ravel().tolist()}


payload = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    ground_geometry={"terrain": terrain_mesh_from_grid(elevation, step=10.0)},
    terrain_alignment="auto-align",              # or "assume-aligned"
)
```

A GeoTIFF DEM read with `rasterio` (`rasterio.open(path).read(1)`, then `rasterio.warp.reproject` onto the metre grid) is the usual source of `elevation`. **`rasterio` is not an SDK dependency** — install it yourself. Whatever the source, the array must be in metres on the frame above and must cover the whole polygon; objects beyond the terrain's extent are clamped to the edge height, not refused.

**A BIM "Mesh" is a solid; `ground_geometry` wants a surface.** ArchiCAD's Mesh element (and most CAD terrain solids) export watertight: the TIN on top, a flat bottom cap, and a vertical skirt. Keep only the up-facing triangles — the bottom cap would drape sensors onto the underside, the skirt would become an occluder wall:

```python
def top_surface_only(coordinates, indices):
    """Up-facing triangles (unit normal z > 0.5 — the server's own roof rule), re-indexed."""
    v = np.asarray(coordinates, dtype=float).reshape(-1, 3)
    f = np.asarray(indices, dtype=int).reshape(-1, 3)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    keep = f[n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5]
    used, new_f = np.unique(keep, return_inverse=True)
    return {"coordinates": v[used].ravel().tolist(), "indices": new_f.ravel().tolist()}
```

Measured on the ArchiCAD sample: 300 triangles in the solid, 85 kept.

### `terrain_alignment` — how your geometry meets the ground

Three server modes, case-sensitive. **None of them moves the sensors** — with `ground_geometry` present the grid always drapes onto the terrain; the modes decide only what happens to the solids in `geometries`, `context_geometry` and `vegetation` (and therefore where footprints are masked).

| Mode | What the server does | Use when |
|---|---|---|
| `"auto-align"` (default) | **Seats the scene.** Every solid is re-based to local grade before inference — each base vertex drops to the terrain beneath it, with a 0.5 m skirt so footprints stay sealed on a slope. The seated geometry is what the under-building mask, the occluder union and facade synthesis all read. | Fetched buildings (based at z = 0) with a real DEM; a BIM export that is **not** consistently seated. |
| `"assume-aligned"` | **Validates only — a validator, not a fixer.** Moves nothing. Any object whose base falls outside the seated band is a **422 for the whole job**, naming the offenders with residuals. Verbatim shape (ArchiCAD sample, 2026-09-02): *"terrain-alignment=assume-aligned but 10 object(s) are not seated on the terrain (seated band: terrain_z −1.5 m to +1.0 m) … object #4 base_z=0.316 terrain_z=−2.161 residual=2.977 m … use auto-align to seat them, or as-is to keep your geometry exactly as sent."* | You prepped geometry against this exact DEM and want a mismatch to be loud. |
| `"as-is"` | **Trusts your geometry exactly.** No seating, no band check — a tower on its own podium 50 m up stays there. | BIM/CAD exports already placed on their terrain. **SDK 0.5.2+ only:** on 0.5.1 the Python `Literal` admits the first two modes only, so `"as-is"` fails client-side before any request leaves — unreachable from Python until you upgrade. |

Rule of thumb from the ArchiCAD case: `assume-aligned` 422'd naming 10 objects floating 1.7–3.0 m above the terrain (buildings at z ≈ 0, terrain top at −1 … −2.4 m). A model like that is not seated → `auto-align`. A model that *is* seated → `as-is`.

With no `ground_geometry` all three are inert — the worker never reads the field, so `"assume-aligned"` validates nothing, and a misspelt value (`"as_is"`) passes silently until the day you add a DEM and it becomes a 422.

**Do not compare alignment modes by their means.** Buildings move vertically, so facades gain and lose exposure in roughly equal measure. On a measured facade run the mean delta was **+0.03 kWh/m²** while **44% of facades moved by more than 1 kWh/m²**, spanning −48.8 to +85.6. Compare per-surface distributions.

## Results on the ground, with terrain

The route for "sensors on the ground, on my terrain" is the **plain grid run** — no `analysis_surfaces`, no `sensor_points` — plus `ground_geometry`. Nothing to switch on: the 1 m grid drapes onto the relief automatically (`z = terrain_z + 1.5 m`), the terrain shades the sun, and building footprints are masked at local grade.

```python
payload = SolarModelRequest(
    analysis_type=AnalysesName.direct_sun_hours,
    latitude=48.195, longitude=11.570,
    time_period=TimePeriod(start_month=6, start_day=1, start_hour=6,
                           end_month=6, end_day=1, end_hour=20),   # daylight only — see 04-direct-sun-hours.md
    ground_geometry={"terrain": terrain_mesh},
    terrain_alignment="auto-align",
)
result = client.run_area_and_wait(payload, polygon, buildings=my_buildings)
grid = result.merged_grid          # (ny, nx) float raster — NO per-cell z
```

Measured (ArchiCAD sample, 1 tile, prod, 2026-09-02): 123 024 cells analysed, mean 11.93 h, max 15.00 h (all 15 samples are daylight, so open ground legitimately reaches the ceiling), 3.4 s.

**What comes back, and what does not:**

- `merged_grid` is a flat raster. **It carries no z** — the terrain height under each cell is never serialised — so to draw it on the terrain in 3D you re-sample your own terrain at every cell centre. That is the one step the API leaves to you.
- Row 0 = south, column 0 = west, 1 m pitch. Cell `(j, i)` is centred at `(i + 0.5, j + 0.5)` **in the frame you submitted** — the polygon's SW corner is submitted `(0, 0)`. Keep that corner at your model origin (or subtract it from every vertex before submitting) and no shift exists anywhere: [`../geospatial-crs.md#the-frame-rule`](../geospatial-crs.md#the-frame-rule).
- **Footprint cells are `0.0`, not `NaN`,** on this path. `NaN` means outside the polygon or off the terrain — the drape ray goes straight down, so terrain narrower than the tile masks cells rather than flattening. Exclude the zeros from any "cells in shadow" statistic (measured: 11 168 footprint zeros among 123 024 cells moved a before/after mean from −1.38 h to −1.52 h).

**Drape for display** — the server's own vertical ray, done client-side on your terrain triangles (linear interpolation on *your* triangulation, `NaN` where no triangle covers the cell):

```python
import numpy as np
from matplotlib.tri import LinearTriInterpolator, Triangulation

def drape_z(terrain_mesh, grid_shape, origin=(0.0, 0.0)):
    """Terrain height at every cell centre of a merged grid, in your model metres.
    `origin` = the model point you submitted as (0, 0); (0, 0) if the model origin was the corner."""
    v = np.asarray(terrain_mesh["coordinates"], dtype=float).reshape(-1, 3)
    f = np.asarray(terrain_mesh["indices"], dtype=int).reshape(-1, 3)
    ny, nx = grid_shape
    xs = origin[0] + np.arange(nx) + 0.5          # column 0 = west
    ys = origin[1] + np.arange(ny) + 0.5          # row 0 = south
    gx, gy = np.meshgrid(xs, ys)
    z = LinearTriInterpolator(Triangulation(v[:, 0], v[:, 1], f), v[:, 2])(gx, gy)
    return z.filled(np.nan)                       # (ny, nx); NaN off the terrain

z = drape_z(terrain_mesh, result.merged_grid.shape)
# one vertex per cell at (x, y, z + a small lift), coloured by merged_grid
```

`matplotlib.tri` interpolates on the triangles you pass (no re-triangulation); a vectorised numpy barycentric test is the dependency-free equivalent. Bucket by triangle for large inputs — an 84 050-triangle DTM × 1 048 576 cells draped in 2.6 s that way.

## Combining with weather-driven analyses (solar-radiation)

`solar-radiation` is normally built via `SolarRadiationModelRequest.from_weatherfile_payload(payload, location, time_period, weather_data)` (see `06-solar-radiation.md`). That classmethod's signature has **no passthrough** for `analysis_surfaces` / `surface_grid_size` / `ground_geometry` / `terrain_alignment` — and every payload class inherits `Payload`'s `frozen=True`, so you cannot set attributes on the object it returns. Skip the classmethod and call `extract_weather_fields` yourself, then construct the concrete request directly with both the weather fields and the facade/terrain fields in one call.

`thermal-comfort-index` / `thermal-comfort-statistics` do **not** take this path for facade fields — the server rejects `analysis_surfaces`/`surface_grid_size` on those two models (see the pitfall below); the same "skip the classmethod, construct directly" pattern still applies for combining their weather data with `ground_geometry`/`terrain_alignment` (terrain draping only), using their own 7-field extraction (`../04-weather-data.md`'s field-to-analysis table) instead of the 2 fields shown here — not verified live in this session.

```python
from infrared_sdk.analyses.types import AnalysesName, SolarRadiationModelRequest
from infrared_sdk.models import extract_weather_fields

accum = extract_weather_fields(
    weather_data, ["diffuseHorizontalRadiation", "directNormalRadiation"]
)
payload = SolarRadiationModelRequest(
    analysis_type=AnalysesName.solar_radiation,
    geometries=area.buildings,          # or omit and pass buildings= to run_area instead
    latitude=48.2038, longitude=16.3819,
    time_period=tp,                     # same TimePeriod passed to filter_weather_data
    analysis_surfaces="all",            # facades + roofs
    surface_grid_size=2.0,
    # ground_geometry={"terrain": terrain_mesh}, terrain_alignment="auto-align",  # optional
    **accum,
)
result = client.run_area_and_wait(payload, polygon, buildings=None)
```

Verified live (2026-07-24) on a 6 km², 16.8k-building, 25-tile Vienna AOI at `surface_grid_size=2.0` for both a 1-day and a full-year `TimePeriod` — `SurfaceAnalysisResult` in both cases, batching (`#batch{i}` sub-jobs) triggered on ~14 of the 25 tiles.

## Response

**An `analysis_surfaces` request returns a `SurfaceAnalysisResult`, NOT a grid result** — `run_area_and_wait` / `merge_area_jobs` are typed `Union[AreaResult, SurfaceAnalysisResult]`. There is no `merged_grid`:

- `result.surfaces` — `{"<building-id>/<surface-index>": SurfaceSensorGrid}`; each has `origin` / `u_axis` / `v_axis` (UV frame in tile metres), `nu` x `nv` grid dims, `values`, `mean`, `peak`, `area`, `cell_area`, `cell_tris`. Per-cell lists carry `None` for masked cells outside the surface footprint — map to `NaN` before numeric work.
- `result.aggregates["buildings"]` — `{building_id: BuildingAggregate}` with `area` / `mean` / `peak`.
- `result.sensor_count`, `result.min_legend`, `result.max_legend` — the legend bounds **are** populated here, unlike area results where both are `None`.
- Surfaces at exactly `mean = peak = 0.0` are real (party walls, fully occluded elevations), not gaps — see [`../surface-results-integration.md`](../surface-results-integration.md#orientation--which-way-a-surface-faces) for that and for the outward-normal / compass convention.

`sensor_points` responses are a third shape: a flat per-sensor list under `"output"` (plus `sensor-count` and legends), one value per sensor in input order.

Terrain-only requests (no facade/sensor fields) return the normal grid result — see [*Results on the ground, with terrain*](#results-on-the-ground-with-terrain) for what it carries and what it does not.

## Pitfalls

- `analysis_surfaces` and `sensor_points` are **mutually exclusive** — the SDK raises a `ValidationError` client-side before any network call.
- **`context_geometry` is not accepted alone** — it needs `sensor_points`, `analysis_surfaces` or `ground_geometry` beside it. The flat-grid path does not trace context at all, so the SDK raises `ValueError` client-side and the server would 422. Give the occluders something to shade.
- `sensor_points` through `run_area` / `run_area_and_wait` raises a `ValueError` — the flat per-sensor response can't be tile-merged; use the job primitives shown above.
- `sensor_points` cap: 100,000 entries; `sensor_normals` must match its length, entries non-zero. `surface_grid_size >= 0.25`; `surface_offset >= 0`.
- Facade fields on `thermal-comfort-index` / `thermal-comfort-statistics` are rejected by the server (and the SDK models don't expose them there).
- **Batching + billing:** a large facade request whose estimated sensor count exceeds the server's 262,144-sensor synthesis cap is transparently split into multiple sub-jobs (each seeing every other building as occluder context) and merged back into one result. **Each sub-job is billed separately.**
- Type-check the result when a workflow mixes facade and grid runs: `isinstance(result, SurfaceAnalysisResult)`.
- **Occluders (`context_geometry`) + `accuracy`.** `context_geometry` is a `{id: mesh}` map (same shape as `ground_geometry`) of extra shading geometry that is *not* itself analysed — surrounding context you don't want sensors on. `accuracy` (`"standard"` / `"precision"`) is accepted on `direct-sun-hours` / `daylight-availability` only. Supply both `context_geometry` and `ground_geometry` in the same polygon-bbox-SW frame as `buildings`. **On multi-tile runs this needs `infrared-sdk >= 0.4.13`**, which transforms them into each tile's local frame automatically; **0.4.12 copied them untransformed → terrain/occluders misplaced on every tile except the SW corner** (single-tile runs are correct on 0.4.12).
- **`ground_geometry` is SLICED per tile (SDK 0.5.1+) — and that changes results.**
  Each tile now receives only the terrain it needs to seat its own buildings and trees
  and ground its own sensors, instead of a full copy of the mesh. A 6 km² run drops from
  ~140 MB of repeated terrain to ~12 MB, and **high-resolution terrain becomes usable at
  all**: the server caps terrain at 500,000 triangles *per job*, which a 2 m mesh over a
  few km² exceeds as one blob but fits comfortably per tile. (The old advice to keep BYO
  terrain resolution modest no longer applies. Was [infrared-api-sdk#217](https://github.com/Infrared-city/infrared-api-sdk/issues/217).)

  **This is a behaviour change, not just transport.** Terrain is an occluder server-side,
  so cutting it removes long-range terrain shading. Terrain *inside* a tile's envelope
  still occludes exactly as before — a hill between two buildings shades them. What stops
  is shading from terrain the tile does not otherwise need. Nil on a flat site; not nil on
  a valley or an escarpment. Measured on staging: a 150 m escarpment 350 m west of the
  polygon costs up to **1.0 h** of direct sun (mean 0.35 h), and at the default reach it is
  invisible.

  **If distant relief matters to your result, pass it as `context_geometry`** — the
  general-purpose occluder input — rather than relying on however much DEM happened to be
  in the file you uploaded. That is geometry you choose deliberately, which is the point of
  the split.

- **`run_area(..., terrain_context_margin_m=...)`** widens how far `ground_geometry` is
  sliced beyond each tile, in metres, for sites where distant terrain genuinely shades the
  analysed area. Values **below the tile config's own context margin are floored to it**
  (128 m on solar, 0 m on wind), so the knob can never strand a building or tree on absent
  ground. `run_area(..., terrain_context_margin_m=0)` on a solar grid therefore reads back
  `128.0`, because that is what sized the slice. Payload grows roughly with the square of
  the reach.

  `AreaSchedule.terrain_context_margin_m` records the **floored reach actually used**, not
  what you passed, and a `retry_from` that resolves to a different reach is **refused** —
  mixing them would merge two terrain extents into one result. Schedules written before
  0.5.1 record nothing and are treated as unknown, so the guard never fires on old data.

- **`run_area(..., max_sensors_per_job=...)`** lowers the per-job synthesized-sensor budget
  that sizes facade sub-tile batches. On cleanly modelled geometry a latency lever, not a
  correctness one (but see the photogrammetric caveat below), and it may
  only make batches **smaller** — the ceiling is 90 % of the server's hard cap, because
  batch sizing is an estimate and the margin is what keeps it safe.

  Use it sparingly and measure: halving it on a 6 km² Vienna facade run took 39 jobs to 67
  and made the run **21 % slower**, because per-request overhead then dominates. Aggressive
  values are worse than they look — a cap of 2000 produced 1000 jobs, and a 0.3 % download
  failure rate was then enough to abort the whole merge ([#232](https://github.com/Infrared-city/infrared-api-sdk/issues/232)).
  Like the reach, the resolved cap is recorded on the schedule and a mismatched
  `retry_from` is refused: batch keys are positional (`{tile}#batch0`, `#batch1`, …), so a
  different cap **refills** them with different buildings rather than shifting them aside.

  **On finely triangulated input it is a correctness lever.** The batch estimator is
  `total_area / grid_size²`, but synthesis happens on each surface's own `nu × nv`
  rectangle, so every small facet rounds up to at least one cell and pays for the masked
  corners of its bounding rectangle. Measured (Hong Kong photogrammetric model, 461
  buildings → 54 928 surfaces, one tile, SDK 0.5.1, 2026-09-02): estimate 455 079, server
  synthesised **663 182 (×1.46)**, and the run **422'd on both batches** at the default
  budget (`analysis-surfaces would synthesize more than 262144 sensors`). Halving
  `max_sensors_per_job` gave 4 batches that completed (29 s). Raising `surface_grid_size`
  is the server's own suggested alternative. → [`../byo-inputs.md`](../byo-inputs.md#dense-or-photogrammetric-models-the-sensor-estimator-under-counts)
- **Client-side merge, not server compute, dominates wall-clock on large facade runs.** Verified on a real 6 km²/16.8k-building/39-batch run: server-side raytracing was 0.5-6.3s/job (flat regardless of a 1-day vs 1-year `TimePeriod`), but `merge_area_jobs()`/`merge_surface_area_jobs()` — downloading + JSON-decoding + reanchoring + typed-parsing every batch's result — was 55-80% of total time. Installing `infrared-sdk[fast]` (orjson) materially helps this stage. Budget your own timing expectations accordingly: annual vs. daily windows cost about the same; job/batch count is what scales cost, not simulated time span.

## See also

- Rendering these results on your own model (texture route, exact `cell_tris` route) -> `../surface-results-integration.md`

> **Note — response size.** `cell_tris` (the exact clipped per-cell geometry) is
> the bulk of a facade response: measured **96 % of the body** on a 281-surface /
> 8 786-sensor run — 0.2 MB → 4.9 MB, wall-clock 2.1 → 2.5 s (2026-09-02) — and
> 93.7 % on a large facade run. It defaults OFF (`emit_cell_tris=False`), so ask for it per
> selected building or for an export, never for the overview, and use
> `cell_area` when you only need coverage. Work is under way to let clients
> reproduce the same geometry locally, which will remove the trade entirely.
- For polygon/buildings setup -> `02-geometry.md`
- For BYO buildings/terrain meshes -> `../byo-inputs.md`
- For the per-model payloads -> `05-sky-view-factors.md`, `06-solar-radiation.md`, `04-direct-sun-hours.md`, `03-daylight-availability.md`
