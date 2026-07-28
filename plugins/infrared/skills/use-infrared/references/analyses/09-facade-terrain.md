# Facade & Terrain Analysis (analysis-surfaces / sensor-points / ground-geometry)

Analyse **building surfaces** (facades, roofs) or **arbitrary sensor points** instead of the default 512x512 ground grid, and drape results over **terrain geometry**. Requires `infrared-sdk >= 0.4.12`.

Facade/BYO-sensor fields work on the 4 raytraced solar-family models ONLY: `sky-view-factors`, `solar-radiation`, `direct-sun-hours`, `daylight-availability`. Terrain fields additionally work on `thermal-comfort-index` / `thermal-comfort-statistics`.

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

### `terrain_alignment` — how your geometry meets the ground

| Mode | What the server does |
|---|---|
| `"auto-align"` (default) | **Seats the scene.** Every solid in `geometries`, `context_geometry` and `vegetation` is re-based to local grade before inference — each base vertex drops to the terrain beneath it, with a 0.5 m skirt so footprints stay sealed on a slope. The seated geometry is what the grid drape, the under-building mask, the occluder union and facade synthesis all read. |
| `"assume-aligned"` | **Validates only, moves nothing.** Any object whose base falls outside a ±1 m band around the terrain is a **422 for the whole job**, naming the first five offenders with residuals. Use it when your geometry is already prepped against this exact DEM and you want a mismatch to be loud. |

With no `ground_geometry` the setting is inert.

**Do not compare alignment modes by their means.** Buildings move vertically, so facades gain and lose exposure in roughly equal measure. On a measured facade run the mean delta was **+0.03 kWh/m²** while **44% of facades moved by more than 1 kWh/m²**, spanning −48.8 to +85.6. Compare per-surface distributions.

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

Terrain-only requests (no facade/sensor fields) still return the normal grid result.

## Pitfalls

- `analysis_surfaces` and `sensor_points` are **mutually exclusive** — the SDK raises a `ValidationError` client-side before any network call.
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
  that sizes facade sub-tile batches. A latency lever, not a correctness one, and it may
  only make batches **smaller** — the ceiling is 90 % of the server's hard cap, because
  batch sizing is an estimate and the margin is what keeps it safe.

  Use it sparingly and measure: halving it on a 6 km² Vienna facade run took 39 jobs to 67
  and made the run **21 % slower**, because per-request overhead then dominates. Aggressive
  values are worse than they look — a cap of 2000 produced 1000 jobs, and a 0.3 % download
  failure rate was then enough to abort the whole merge ([#232](https://github.com/Infrared-city/infrared-api-sdk/issues/232)).
  Like the reach, the resolved cap is recorded on the schedule and a mismatched
  `retry_from` is refused: batch keys are positional (`{tile}#batch0`, `#batch1`, …), so a
  different cap **refills** them with different buildings rather than shifting them aside.
- **Client-side merge, not server compute, dominates wall-clock on large facade runs.** Verified on a real 6 km²/16.8k-building/39-batch run: server-side raytracing was 0.5-6.3s/job (flat regardless of a 1-day vs 1-year `TimePeriod`), but `merge_area_jobs()`/`merge_surface_area_jobs()` — downloading + JSON-decoding + reanchoring + typed-parsing every batch's result — was 55-80% of total time. Installing `infrared-sdk[fast]` (orjson) materially helps this stage. Budget your own timing expectations accordingly: annual vs. daily windows cost about the same; job/batch count is what scales cost, not simulated time span.

## See also

- Rendering these results on your own model (texture route, exact `cell_tris` route) -> `../surface-results-integration.md`

> **Note — response size.** `cell_tris` (the exact clipped per-cell geometry) is
> the bulk of a facade response; measurements put it around 90% of the body. It
> defaults OFF, so ask for it only when you are drawing crisp outlines, and use
> `cell_area` when you only need coverage. Work is under way to let clients
> reproduce the same geometry locally, which will remove the trade entirely.
- For polygon/buildings setup -> `02-geometry.md`
- For BYO buildings/terrain meshes -> `../byo-inputs.md`
- For the per-model payloads -> `05-sky-view-factors.md`, `06-solar-radiation.md`, `04-direct-sun-hours.md`, `03-daylight-availability.md`
