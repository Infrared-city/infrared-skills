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

`result.to_dict()` serializes for JSON (numpy -> nested lists, NaN -> `None`).

## Pitfalls

- Never derive heatmap colour range from the grid — use `min_legend` / `max_legend` as `zmin` / `zmax`. Direct Sun Hours / Daylight cluster near the max and look washed out otherwise.
- Buildings passed to `run_area_and_wait()` must be in **polygon-bbox-SW frame** (meters from SW corner of bbox). `client.buildings.get_area()` returns them in this frame.
- Solar context margin produces buildings with **negative coordinates** in per-tile frame — that is correct; do not filter them out.
- Cold start: first request in a session is 2-5x slower (Lambda warm-up).
- `MultiPolygon` is not supported. Split into separate Polygon calls.

## See also

- `references/workflows/webhooks.md` — receive job events instead of polling
- `references/workflows/images.md` — render the merged grid to PNG
- `references/workflows/errors.md` — `AreaTimeoutError`, `JobFailedError`
