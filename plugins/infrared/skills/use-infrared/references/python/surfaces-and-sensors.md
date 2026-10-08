# Python: values on facades, roofs and your own points

By default the values sit on a 1 m ground grid. You can move the sensors:

| You set | Sensors land on | Comes back as |
|---|---|---|
| nothing | the ground, 1 m grid (drapes onto terrain) | `AreaResult`: `physical_grid()` |
| `analysis_surfaces` | facades, roofs or both of your buildings | `SurfaceAnalysisResult`: `columns` |
| `sensor_points` | exactly the points you give | `{"output": [...]}`, one value per point |

Only four analyses take facade and point sensors: solar radiation, sky view factor,
direct sun hours and daylight availability. UTCI, TCS and wind do not.
You cannot use `analysis_surfaces` and `sensor_points` in one request.

Docs: [Facade and roof runs](https://infrared.city/docs/sdk/1.0/sdk.md) (chapters "Facade and roof runs" and
"Draw facade and roof results fast"),
[Facade layout](https://infrared.city/docs/sdk/1.0/python/facade_layout/index.md),
[Analyses](https://infrared.city/docs/sdk/1.0/python/analyses/index.md).

## Facades and roofs

```python
import numpy as np
from infrared_sdk import InfraredClient, SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

client = InfraredClient()
lon, lat = 16.371, 48.208
polygon = {"type": "Polygon", "coordinates": [[
    [lon, lat], [lon + 0.004, lat], [lon + 0.004, lat + 0.003],
    [lon, lat + 0.003], [lon, lat]]]}
xy = [(100, 100), (120, 100), (120, 120), (100, 120)]
coordinates = [c for z in (0, 30) for x, y in xy for c in (x, y, z)]
indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
buildings = {"tower": {"coordinates": coordinates, "indices": indices}}

request = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    analysis_surfaces="all",        # "facades", "roofs" or "all"
    surface_grid_size=3.0,          # cell size in metres, minimum 0.25
)

# Pass payload= and buildings=. Without them the job count is too low,
# because a big facade run splits into batches, and each batch is one billed job.
preview = client.preview_area(polygon, payload=request, buildings=buildings)
print(preview.would_bill_jobs, "jobs,", preview.sensor_count, "sensors")

result = client.run_area_and_wait(request, polygon, buildings=buildings)

cols = result.columns                       # every surface of the run, by row
values = cols.physical_values()             # real values, NaN = no value
print(len(cols.ids), "surfaces,", values.shape[0], "cells")
print("min/max legend:", result.min_legend, result.max_legend)

# Per-building roll-up: area, mean and peak.
for building_id, agg in result.aggregates["buildings"].items():
    print(building_id, round(agg.mean, 1), round(agg.peak, 1))
```

A surface at exactly 0.0 is real data (a party wall, a light well). It is not a gap.
A cell with no value is NaN. Never fill NaN with zero.

### Draw it fast: render buffers

Do not build one mesh per cell. The render buffers are a few flat arrays that deck.gl,
three.js or raw WebGL read directly.

```python
buffers = cols.render_buffers()
print(buffers.values.dtype, buffers.values.shape, buffers.value_min, buffers.value_max)
```

The buffers hold the outline triangles, the frames, one value per cell, and one validity bit
per cell. Test the validity bit. Do not test the value: a cell with no value holds 0.
Use one colour scale for roofs and facades. Save a layout once per geometry to draw later:
see `FacadeLayout` and `attach_values` in the guide chapter "Draw facade and roof results fast".

## Your own sensor points

Own points run as one job and not as an area run. Send the geometry with the points.
Coordinates are in the metre frame of your geometry. The cap is 300,000 points for each job.

```python
request = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    geometries=buildings,                          # your meshes, in metres
    sensor_points=[[110, 90, 1.5], [110, 130, 15.0]],
    sensor_normals=[[0, -1, 0], [0, 1, 0]],        # optional: one normal per point
)
out = client.analyses.run_and_wait(request)
print(out["output"])                               # one value per point, same order
```

## Terrain and context shade

Terrain goes in `ground_geometry`, never in `buildings`. The ground grid then drapes onto it.
Without `ground_geometry`, the ground is a flat plane at z = 0, with no error.
`context_geometry` holds far objects that only cast shade. In 1.0 it reaches 128 m past a tile.
It needs terrain, facade sensors or own points beside it.

```python
def terrain_mesh_from_grid(elevation, step=10.0):
    """Heights in metres, shape (ny, nx), on a regular grid -> one SDK mesh."""
    elevation = np.asarray(elevation, dtype=float)
    ny, nx = elevation.shape
    gx, gy = np.meshgrid(step * np.arange(nx), step * np.arange(ny))
    verts = np.stack([gx, gy, elevation], axis=-1).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1))
    a = (j * nx + i).ravel()
    b, c, d = a + 1, a + nx, a + nx + 1
    tris = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c], 1)])
    return {"coordinates": verts.ravel().tolist(), "indices": tris.ravel().tolist()}

# A gentle slope that covers the whole polygon (about 340 m by 330 m).
slope = 2.0 + 0.5 * np.arange(40)[None, :] * np.ones((40, 1))   # rises 0.5 m per 10 m, to the east
terrain = terrain_mesh_from_grid(slope, step=10.0)

request = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    ground_geometry={"terrain": terrain},
    terrain_alignment="auto-align",   # seats buildings on the terrain
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
grid = result.physical_grid()          # a raster with no z: re-sample your terrain to draw it in 3D
print(grid.shape)
```

More on terrain, alignment modes and the drape:
[../analyses/11-terrain-and-context.md](../analyses/11-terrain-and-context.md).
A building mesh that comes from a BIM solid terrain: keep only the up-facing triangles.

## Limits

| Limit | Value |
|---|---|
| Own sensor points in one job | 300,000 |
| Facade sensors in one batch | about 250,000 (the SDK plans more batches) |
| Terrain triangles in one request | 500,000 |
| Triangles in one tile scene (all layers) | 5,000,000 |
| One request | 64 MiB |
