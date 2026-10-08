# Facades, roofs and own sensors

Move the sensors from the ground to the building shells, or to points that you give.
Call code: [../python/surfaces-and-sensors.md](../python/surfaces-and-sensors.md).
Terrain and shade from far objects: [11-terrain-and-context.md](11-terrain-and-context.md).

Only four analyses take these fields: `sky-view-factors`, `solar-radiation`, `direct-sun-hours`,
`daylight-availability`. UTCI, TCS and wind refuse them.

## Where the sensors go

| You set | Sensors land on | Comes back as |
|---|---|---|
| nothing | the ground, 1 m grid | `AreaResult` |
| `analysis_surfaces` | building shells: `"facades"`, `"roofs"`, `"all"` | `SurfaceAnalysisResult` |
| `sensor_points` | your points, one job, no tiling | `{"output": [...]}` |
| daylight-factor model | inside rooms | per-point values ([10-interior-daylight-factor.md](10-interior-daylight-factor.md)) |

One mode for each request. Ground and facades are two requests.

## The geometry channels

| Channel | Role |
|---|---|
| `buildings=` of the run (or `geometries` on the request) | Analysed. Sensors land here. |
| `context_geometry` | Casts shade only. Never analysed. |
| `ground_geometry` | Terrain. Never analysed. |
| `vegetation` | Trees, GeoJSON points, lon/lat |
| `ground_materials` | Material polygons, lon/lat |

The three mesh channels take `{id: {"coordinates": [...], "indices": [...]}}` in metres, with the
origin at the south-west corner of the polygon bounding box. The SDK re-frames them for each tile.

"My design in its neighbourhood" is the cheap pattern: cost follows the surfaces that you ask for.
Put the building you design in `buildings` and the surroundings in `context_geometry`.

## Fields

- `surface_grid_size`: cell size in metres, default 2.0, minimum 0.25.
- `surface_offset`: distance from the surface, default 0.1 m.
- `sensor_points`: `[x, y, z]` in the metre frame, up to 300,000 for each job.
  `sensor_normals`: one non-zero normal for each point (optional).
- `analysis_surfaces` and `sensor_points` exclude each other.
- `emit_cell_tris` is off by default. It adds exact cell outlines and makes the answer much larger.
  Turn it on for one selected building or for an export.
- `max_sensors_per_job` lowers the sensors in one batch. On very fine meshes, lower it or raise
  `surface_grid_size`: the estimate can under-count and the job is refused (422).

## Cost

A facade run is split into batches of at most about 250,000 sensors. Each batch is one billed job.
A tile with no target building sends no job. Use `preview_area(..., payload=, buildings=)` and
read `would_bill_jobs`.

## Results

- `result.columns.physical_values()`: one real value for each cell. NaN means no value.
- `result.columns.ids`, `.origin`, `.u_axis`, `.v_axis`, `.nu`, `.nv`, `.mean`, `.peak`, `.area`:
  one row for each surface. Surface ids look like `"<building-id>/<surface-index>"`.
- `result.aggregates["buildings"]`: area, mean and peak for each building.
- A surface with mean 0.0 is real data (party wall). A NaN cell is a masked cell.
- Draw with render buffers: [../surface-results-integration.md](../surface-results-integration.md).
- Check the type: `isinstance(result, SurfaceAnalysisResult)` when a flow mixes ground and facade runs.

## Pitfalls

- `grid.max()` equals the window length: night hours in a direct-sun-hours window
  ([04-direct-sun-hours.md](04-direct-sun-hours.md)).
- A facade result with dozens of surfaces from one terrain: the terrain went in `buildings`.
  Move it to `ground_geometry`.
- Everything sits a few metres off: the polygon corner is not at (0, 0) ([../geospatial-crs.md](../geospatial-crs.md)).
- `context_geometry` alone is refused. Put it beside terrain, facade sensors or own points.
- 413 `REF_TOO_LARGE`: the request is over 64 MiB. Weld and simplify meshes ([../byo-inputs.md](../byo-inputs.md)).
- A repeated facade run bills again in full.
