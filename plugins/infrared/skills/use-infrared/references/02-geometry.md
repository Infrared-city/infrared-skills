# Geometry (Polygon Input)

The polygon you pass to `run_area_and_wait()` and the buildings/vegetation/ground-materials sub-clients is a standard GeoJSON Polygon: `[longitude, latitude]` order, single ring, closed.

## Format

```python
polygon = {
    "type": "Polygon",
    "coordinates": [[
        [11.570, 48.195],   # [lon, lat]
        [11.580, 48.195],
        [11.580, 48.201],
        [11.570, 48.201],
        [11.570, 48.195],   # ring must close (first == last)
    ]],
}
```

## Validation

The SDK runs `validate_polygon()` (see `tiling/validation.py`) before any tiling. The chain:

1. Must be a dict with `type` and `coordinates` fields.
2. `type` must be `"Polygon"` (MultiPolygon not supported).
3. Single ring only — no holes (`len(coordinates) == 1`).
4. At least 4 positions (3 unique vertices + closing vertex).
5. Ring must be closed: `ring[0] == ring[-1]`.
6. Coordinate range: lon in [-180, 180], lat in [-90, 90].
7. No self-intersections.
8. Winding order is auto-normalised to CCW (shoelace area, x=lon y=lat); CW input is silently reversed.

Failures raise `PolygonValidationError` (a `ValueError` subclass).

## Pitfalls

- GeoJSON order is `[lon, lat]` — not `[lat, lon]`. Mixing them up is the most common source of "polygon outside expected area" bugs.
- Numpy arrays / float32 scalars are coerced to plain Python lists/floats automatically (so shapely / GeoPandas exports work).
- Zero-area polygons (collinear or duplicate vertices) are rejected.
- Hard cap of 100 non-empty tiles per run; pass `max_tiles_override` to lift it. A single tile is 512 × 512 m, so ~5 km on a side is the practical ceiling.
- `client.preview_area(polygon)` returns `tile_count`, `estimated_time_s`, and `estimated_cost_tokens` — always preview before running large polygons.

## See also

- `01-quickstart.md` — minimum-viable polygon + run
- `04-weather-data.md` — station lookup by lat/lon
- `analyses/` — per-analysis polygon expectations
