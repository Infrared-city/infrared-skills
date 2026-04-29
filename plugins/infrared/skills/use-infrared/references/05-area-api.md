# Area API

Multi-tile analyses over polygons larger than one 512x512m tile. The SDK auto-tiles, parallelizes calls, and stitches a merged grid.

## Cost preview

```python
preview = client.preview_area(polygon)
print(f"Tiles: {preview.tile_count}")
print(f"Estimated time: {preview.estimated_time_s}s")
print(f"Estimated cost: {preview.estimated_cost_tokens} tokens")
```

Returns `AreaPreview(tile_count, estimated_time_s, estimated_cost_tokens)`. Heuristics: 10 tokens/tile, 10 s/tile. `max_tiles_override=N` lifts the default ~100 non-empty cap.

## Basic usage (fetch-once-reuse)

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName

polygon = {
    "type": "Polygon",
    "coordinates": [[
        [13.4050, 52.5200], [13.4110, 52.5200],
        [13.4110, 52.5254], [13.4050, 52.5254],
        [13.4050, 52.5200],
    ]],
}

with InfraredClient() as client:
    area = client.buildings.get_area(polygon)          # fetch buildings once
    # area.failed_tiles lists any tiles where building fetch failed (empty on full success)
    wind_result = client.run_area_and_wait(
        WindModelRequest(
            analysis_type=AnalysesName.wind_speed,
            wind_speed=10, wind_direction=180,
        ),
        polygon,
        buildings=area.buildings,
    )
    print(wind_result.grid_shape)      # e.g. (768, 1024)
    print(wind_result.succeeded_jobs)
```

## Multi-analysis runs

Pass a list of payloads to pool every submission across types into one 20-worker pool. Same trick for parameter sweeps (e.g. 8 wind directions = `8 x tile_count` jobs in one pool).

```python
results = client.run_area_and_wait(
    [wind_payload, svf_payload, solar_payload],
    polygon,
    buildings=area.buildings,
)
wind_result, svf_result, solar_result = results
```

Per-call cap is `max_workers` (default 20). To exceed it, instantiate multiple `InfraredClient`s in separate threads/processes.

## Polygon requirements

GeoJSON Polygon `{"type": "Polygon", "coordinates": [[[lon, lat], ...]]}`. Single ring (not MultiPolygon), `[longitude, latitude]` order, closed, >=3 unique vertices, no self-intersection. Max ~100 non-empty tiles (override with `max_tiles_override`).

## Tile geometry

| Config                   | Inference | Context | Step | Overlap        | Crop                 |
| ------------------------ | --------- | ------- | ---- | -------------- | -------------------- |
| Wind (`wind-speed`, PWC) | 512m      | 512m    | 256m | 50% (256m)     | Centre 256x256 cells |
| Solar (all others)       | 512m      | 666m    | 512m | None edge-edge | Full 512x512 cells   |

Cell pitch is 1m. Wind merges from centre crops; solar tiles butt edge-to-edge with 77m context margin for distant-shadow buildings. Cells outside the polygon become NaN.

## AreaResult fields

| Field            | Type              | Description                                |
| ---------------- | ----------------- | ------------------------------------------ |
| `merged_grid`    | `numpy.ndarray`   | Merged grid, NaN outside polygon           |
| `polygon`        | `dict`            | Source GeoJSON polygon                     |
| `analysis_type`  | `str`             | Analysis type that was run                 |
| `grid_shape`     | `tuple[int, int]` | (rows, cols) of merged grid                |
| `succeeded_jobs` / `total_jobs` | `int`  | Job counts                          |
| `failed_jobs` / `skipped_jobs`  | `list[str]` | Failed / non-terminal job IDs  |
| `min_legend`     | `float\|None`     | Legend min across tiles (use as zmin)      |
| `max_legend`     | `float\|None`     | Legend max across tiles (use as zmax)      |

`result.to_dict()` serializes for JSON (numpy -> nested lists, NaN -> `None`) — this is also the shape `client.weather.gen_grid_image()` expects.

## Why building coordinates differ per tile

When you pass `buildings` to `run_area_and_wait()` / `run_area()`, the same building can appear in multiple tiles with **different coordinate values** — that is correct. For each tile the SDK:

1. Computes the tile's **inference SW offset** relative to the polygon bbox SW (based on the tile's row/col and the step size).
2. Expands the tile's bbox by the **context margin** (0 m for wind, 77 m for solar) — this expanded area is only used to *select* which buildings to include.
3. Tests each building's bbox against the expanded selection area.
4. Deep-copies the building and **subtracts the inference tile's SW offset** from its coordinates, converting from polygon-bbox-SW frame to tile-SW frame.

Building coordinates are always relative to the **inference square** (512×512m), not the context square. A building caught only by the solar context margin sits outside 0–512 m, so its tile-frame x or y will be **negative** — the API needs the position relative to the inference origin to compute its shadow / wind effect. Don't filter negative coordinates out.

## Concurrency and per-call caps

`max_workers` (default 20) is the cap **per `run_area*` call**, not per tile or per payload. A multi-payload call like `run_area_and_wait([8 payloads], polygon)` over a 24-tile polygon still runs 20 concurrent submissions, not 192 — submissions queue against the same pool. To exceed it, instantiate multiple `InfraredClient` objects in separate threads or processes (each with its own pool). The backend also enforces an account-level concurrency ceiling (~100 simultaneous tile jobs by default); contact support if you regularly need more.

## Pitfalls

- Never derive heatmap colour range from the grid — use `min_legend` / `max_legend` as `zmin` / `zmax`. Direct Sun Hours / Daylight cluster near the max and look washed out otherwise. The API currently returns `None` for these fields on all analyses; always apply a fallback: `zmin = result.min_legend if result.min_legend is not None else float(np.nanmin(result.merged_grid))`.
- Buildings passed to `run_area_and_wait()` must be in **polygon-bbox-SW frame** (meters from SW corner of bbox). `client.buildings.get_area()` returns them in this frame.
- Solar context margin produces buildings with **negative coordinates** in per-tile frame — that is correct; do not filter them out.
- The 77 m solar context margin is also the **shadow-casting horizon** — buildings further than 77 m from a tile's edge can't occlude into that tile. At low sun angles (early/late hours, winter) shadows on multi-tile polygons may clip at tile seams. Avoid those hours, or fall back to a single-tile polygon.
- Cold start: first request in a session is 2-5x slower (Lambda warm-up).
- `MultiPolygon` is not supported. Split into separate Polygon calls.

## See also

- `06-webhooks.md` — receive job events instead of polling
- `07-images.md` — render the merged grid to PNG
- `08-error-handling.md` — `AreaTimeoutError`, `JobFailedError`
