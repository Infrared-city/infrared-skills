# Integrating Surface Results (rendering facade/roof grids on your own model)

How to take a `SurfaceAnalysisResult` (see `analyses/09-facade-terrain.md`) and display it on the geometry you submitted — in a BIM tool, game engine, or web viewer. Requires `infrared-sdk >= 0.4.12`.

## The contract, in rendering terms

Every entry in `result.surfaces` is keyed `"{building-id}/{surface-index}"` — the building id is **your own key** from the `geometries` you submitted, so results map straight back onto your elements. Each `SurfaceSensorGrid` is a planar sensor grid in its own UV frame:

- `origin` — 3D anchor of the grid (same coordinate frame as your submitted mesh, metres)
- `u_axis`, `v_axis` — unit vectors in the surface plane
- `grid_size` — cell edge length (your `surface_grid_size`)
- `nu`, `nv` — grid dimensions; `values` has `nu * nv` entries, **row-major in v** (`index = j * nu + i`)
- `values[k] is None` — masked cell: its centre lies outside the surface's true footprint. Never zero-fill; cut or skip these.
- `cell_area[k]` — the **fraction** of the cell inside the surface footprint, in `(0,1]` (dimensionless, *not* m²); multiply by `grid_size²` for the actual area. `cell_tris[k]` — the exact clipped triangle geometry (flat `[x,y,z, ...]`, 9 floats per triangle). Both keys are **absent** (not empty) when the server was asked not to emit them.
  That is controlled by **`emit_cell_tris`** on the request (SDK 0.5.1+), which **defaults
  to `False`** on every `analysis_surfaces` request — efficient by default, because on a
  large facade run the triangle arrays dominate the download (measured 93.7% of the
  payload), and the download is the phase that dominates wall-clock. Set it `True`
  explicitly when you need the clipped geometry for Route 2; leave it alone for Route 1
  or analysis-only work. `values` and every aggregate are identical either way, so
  nothing analytical is lost — only the exact per-cell outlines used for *drawing*.
  Handle both shapes: check for the key on `cell_tris` **and** `cell_area`, do not
  assume either is there.

`origin` is the **centre of cell (0, 0)**, not a corner. So:

```
centre(i, j) = origin + u_axis * (i * grid_size) + v_axis * (j * grid_size)
corners      = centre ± 0.5 * grid_size * u_axis ± 0.5 * grid_size * v_axis
```

Getting this wrong displaces every surface by half a cell in both `u` and `v` — a ~1.4 m diagonal error at the default 2 m `surface_grid_size`. It's a uniform offset, so it looks plausible rather than obviously broken.

To detect fully-covered cells, compare with an epsilon — `cell_area` is emitted from `f32`, so use `cell_area[k] >= 1.0 - 1e-6` rather than `== 1.0`, or float noise misclassifies full cells as partial.

## Route 1 — texture mapping (fast, smooth, simplest)

Build a small texture per surface (or pack all surfaces into one atlas) and map it onto the surface quad `origin -> origin + u*nu*gs -> ... -> origin + v*nv*gs`. Smooth gradients come free from GPU bilinear filtering; a "raw cells" view is the same texture with nearest filtering.

Handle masked cells with **premultiplied masking** so bilinear edges stay clean — two channels per texel:

```
R = value / value_max        (0 for masked cells)
G = 1.0                      (0 for masked cells)
```

```glsl
// fragment shader
vec2 c = texture(atlas, uv).rg;
if (c.g < 0.2) discard;                       // outside the footprint
float v = clamp(c.r / max(c.g, 1e-4), 0.0, 1.0);
fragColor = vec4(colormap(v), 1.0);
```

This is a complete production approach: ~15 shader lines + one packing loop, no geometry processing at all. Cutouts follow the mask at cell resolution (edges look stepped when zoomed far in — if that matters, use Route 2 or combine both).

## Route 2 — exact mesh from `cell_tris` (crisp boundaries, no textures)

`cell_tris[k]` is the cell already clipped to the surface's true outline. Emit those triangles directly with the cell's value as a flat color (or average values to shared vertices for smooth shading). Boundaries are exact — no stepping — because the server did the clipping. Cost: more geometry (a few triangles per cell) and a mesh build pass.

**Check `cell_tris` is present before you rely on it** — it is absent on the centre-test / BYO-sensor path, and a client can ask the server to omit it. Fall back to the unclipped cell quad from `centre(i, j)` above (slightly over-drawn at footprint edges) or to Route 1, rather than indexing into a missing array.

## Which route

| Need | Route |
|---|---|
| Interactive city-scale view, smooth gradients | 1 (texture) |
| Exact printable/exportable geometry, crisp edges | 2 (`cell_tris`) |
| Best of both | 1 for the overview, 2 on demand for selected elements |

## Orientation — which way a surface faces

`origin` / `u_axis` / `v_axis` are a **right-handed** frame. The outward normal is
`u_axis × v_axis`, in that order — the server builds the frame as `u = ẑ × n`, `v = n × u`
from the surface's own triangle winding, so outward-wound shells (everything
`client.buildings` returns) give outward normals. Tile-local metres are `+x` east, `+y`
north, which fixes the compass mapping:

```python
import math
import numpy as np

def outward_normal(s):
    n = np.cross(s.u_axis, s.v_axis)
    return n / np.linalg.norm(n)

def bearing(n):
    """Degrees clockwise from north: 0 = N, 90 = E, 180 = S, 270 = W."""
    return math.degrees(math.atan2(n[0], n[1])) % 360.0
```

Checked against physics rather than assumed: a 21 June `direct-sun-hours` run in Munich gave
area-weighted means of **S 5.26 h, E 4.66 h, W 3.90 h, N 2.94 h** by this bearing — the
expected ordering, which only holds if the normal points outward.

For the facade/roof split use `surface.is_vertical`, which applies the server's own rule
(`|n_z| ≤ 0.5` for `n = u_axis × v_axis`). Do not classify by `v_axis[2]` alone.

## Display tips

- **Use ONE shared colour scale for roofs and facades.** They're read together, so a single `[min_legend, max_legend]` scale keeps every surface comparable across the whole scene — roofs sit high (open sky / high radiation), facades lower, and *that contrast is the reading*. This is the coherent default; don't give facades their own scale, or two surfaces on the same building stop being comparable. (Roofs can sit 3&ndash;5&times; facade values in summer solar. If you genuinely must inspect facades in isolation, clip to the facade percentiles as a deliberate, **labelled** exception — classify with `surface.is_vertical` — but never silently.)
- **A surface at exactly `0.0` is data, not a gap.** Party walls and fully occluded elevations return `mean = peak = 0.0` with every cell present — distinct from the `None` masked cells, which mean "no sensor here". On a 300-building Munich `direct-sun-hours` run, **555 of 1,730 facades (32%)** were exact zeros, moving the scene mean from 5.33 h to 3.62 h. Decide explicitly whether a building or scene aggregate includes them, and say which.
- **Interpolation is a display choice, not an API request.** The grid is the lossless raw result; bilinear/bicubic filtering at render time produces the smooth transitions. Don't ask for (or build) pre-smoothed meshes — you'd bake in one display style and lose the sensor truth.
- Per-building rollups (`result.aggregates["buildings"]`: `area` / `mean` / `peak`) are ready-made for element-level coloring, dashboards, and ranking without touching the grids.

## See also

- Making the render *read* correctly — legend bounds, masked cells, categorical output, colormap choice, north-up -> [`recipes/rendering-results-well.md`](recipes/rendering-results-well.md)
- Request fields, applicability, response shape -> `analyses/09-facade-terrain.md`
- Geometry / coordinate conventions -> `02-geometry.md`
