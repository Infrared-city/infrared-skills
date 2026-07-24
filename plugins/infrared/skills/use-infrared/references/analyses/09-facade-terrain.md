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

Terrain draping (all six raytraced models, including UTCI/TCS):

```python
payload = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    ground_geometry={"terrain": terrain_mesh},   # DotBim-style mesh
    terrain_alignment="auto-align",              # or "assume-aligned"
)
```

## Combining with weather-driven analyses (solar-radiation / UTCI / TCS)

`solar-radiation`, `thermal-comfort-index`, and `thermal-comfort-statistics` are normally built via `<Request>.from_weatherfile_payload(payload, location, time_period, weather_data)` (see `06-solar-radiation.md`). That classmethod's signature has **no passthrough** for `analysis_surfaces` / `surface_grid_size` / `ground_geometry` / `terrain_alignment` — and every payload class inherits `Payload`'s `frozen=True`, so you cannot set attributes on the object it returns. Skip the classmethod and call `extract_weather_fields` yourself, then construct the concrete request directly with both the weather fields and the facade/terrain fields in one call:

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
- `result.sensor_count`, `result.min_legend`, `result.max_legend`.

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

## See also

- Rendering these results on your own model (texture route, exact `cell_tris` route) -> `../surface-results-integration.md`
- For polygon/buildings setup -> `02-geometry.md`
- For BYO buildings/terrain meshes -> `../byo-inputs.md`
- For the per-model payloads -> `05-sky-view-factors.md`, `06-solar-radiation.md`, `04-direct-sun-hours.md`, `03-daylight-availability.md`
