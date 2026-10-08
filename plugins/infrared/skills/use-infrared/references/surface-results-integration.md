# Showing facade and roof results on your own model

How to draw the result of an `analysis_surfaces` run on the geometry you sent: in a web viewer,
a BIM tool or a game engine. Request fields: [analyses/09-facade-terrain.md](analyses/09-facade-terrain.md).
Call code: [python/surfaces-and-sensors.md](python/surfaces-and-sensors.md).
Guide chapter "Draw facade and roof results fast": <https://infrared.city/docs/sdk/sdk.md>

## The result: columns

A surface run gives a `SurfaceAnalysisResult`. Its `columns` hold every surface in rows
(`S` surfaces), and all cells in one value array:

| Field | Meaning |
|---|---|
| `ids` | Surface ids: `"<your-building-id>/<surface-index>"`. They map back to your elements |
| `origin` (S, 3) | **Centre of cell (0, 0)** in the frame that you submitted, in metres |
| `u_axis`, `v_axis` (S, 3) | Unit vectors in the surface plane |
| `grid_size`, `nu`, `nv` | Cell size and cell counts |
| `cell_offsets` (S+1) | Surface `i` owns `values[cell_offsets[i]:cell_offsets[i+1]]`, row-major in v (`j * nu + i`) |
| `values`, `physical_values()` | Stored values, and real values. NaN = no value |
| `mean`, `peak`, `area` | Roll-ups for each surface |
| `cell_area` | Fraction of each cell inside the surface, 0 to 1 (not m2) |

Cell centre: `origin + u_axis * (i * grid_size) + v_axis * (j * grid_size)`.
The cell corners are the centre `+/- 0.5 * grid_size` along each axis.
Reading `origin` as a corner puts every surface half a cell off, about 1.4 m diagonal at the
default 2 m grid. The error is uniform, so it looks fine.

## Route 1: render buffers (default for a viewer)

`columns.render_buffers()` (TypeScript: `surfaceRenderBuffers(columns)`) gives a few flat arrays
for deck.gl, three.js or WebGL: outline triangles in cell units, `frames`, `dims`, one value for each
cell, one validity bit for each cell, an `anchor` for the model transform, and `valueMin` and `valueMax`.
The shader finds the cell from the outline point. No mesh for each cell.

- Test the **validity bit**. A cell with no value holds 0 and a clear bit. Values are never NaN there.
- Draw both faces of every frame.
- Keep one run to one site so the corners stay accurate.
- Save the layout (frames and outline) once for each geometry (`FacadeLayout.to_bytes`) and the values
  for each run (`columns.to_bytes`). Rejoin with `attach_values`, which refuses a mismatch.
- Free memory: `client.forget_schedule(schedule)` for a schedule you will not merge.

## Route 2: textures per surface (BIM tools, engines)

Pack each surface into a small texture with two channels and discard the empty cells in the shader.
Bilinear filtering then gives smooth gradients with clean edges.

```
R = value / value_max   (0 for a masked cell)
G = 1.0                 (0 for a masked cell)
```

```glsl
vec2 c = texture(atlas, uv).rg;
if (c.g < 0.2) discard;                          // outside the surface
float v = clamp(c.r / max(c.g, 1e-4), 0.0, 1.0);
fragColor = vec4(colormap(v), 1.0);
```

The quad of a surface starts at `origin - (u + v) * grid_size / 2` and runs to
`origin + u * (nu - 0.5) * grid_size + v * (nv - 0.5) * grid_size`.

## Exact outlines

Set `emit_cell_tris=True` to get exact clipped cell triangles. They are about 96 % of the answer
body. Use them for one selected building, or for an export. "Overview, then click" keeps the
payload small:

1. Run the whole scene with the default (no triangles). Draw render buffers or textures.
2. On selection, run again with that building in `buildings`, the rest in `context_geometry`,
   and `emit_cell_tris=True`.
3. Cache by building id. Values are the same either way.

## Orientation

`origin`, `u_axis` and `v_axis` are a right-handed frame. The outward normal is `u_axis x v_axis`.
Tile metres have +x east and +y north:

```python
import math
import numpy as np

def bearing(normal):
    """Degrees clockwise from north: 0 = N, 90 = E, 180 = S, 270 = W."""
    return math.degrees(math.atan2(normal[0], normal[1])) % 360.0

cols = result.columns
normal = np.cross(cols.u_axis[0], cols.v_axis[0])
normal /= np.linalg.norm(normal)
print(bearing(normal), "deg")
```

A facade has `|n_z| <= 0.5`. Do not sort facade from roof by `v_axis[2]` alone.
A June run in Munich ordered the area-weighted sun hours S, E, W, N: a check that the normal points out.

## Display

- One shared colour scale for roofs and facades. The contrast between them is the reading.
  Isolate facades only with a labelled exception.
- A surface at exactly 0.0 is data (party wall, light well). A masked cell is NaN. They are different.
  On one Munich run, 32 % of the facades were exact zeros and moved the scene mean from 5.33 h to 3.62 h.
  Say whether your mean includes them.
- Interpolation is a display choice. Keep the grid as the lossless result.
- `result.aggregates["buildings"]` gives area, mean and peak for each building: use it for element
  colours, dashboards and ranking.

More on colour: [recipes/rendering-results-well.md](recipes/rendering-results-well.md).
