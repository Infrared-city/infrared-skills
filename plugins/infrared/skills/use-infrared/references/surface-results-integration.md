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

## Display tips

- **Use ONE shared colour scale for roofs and facades.** They're read together, so a single `[min_legend, max_legend]` scale keeps every surface comparable across the whole scene — roofs sit high (open sky / high radiation), facades lower, and *that contrast is the reading*. This is the coherent default; don't give facades their own scale, or two surfaces on the same building stop being comparable. (Roofs can sit 3&ndash;5&times; facade values in summer solar. If you genuinely must inspect facades in isolation, clip to the facade percentiles as a deliberate, **labelled** exception — classify by `v_axis`, vertical `v_axis` &rarr; facade — but never silently.)
- **Interpolation is a display choice, not an API request.** The grid is the lossless raw result; bilinear/bicubic filtering at render time produces the smooth transitions. Don't ask for (or build) pre-smoothed meshes — you'd bake in one display style and lose the sensor truth.
- Per-building rollups (`result.aggregates["buildings"]`: `area` / `mean` / `peak`) are ready-made for element-level coloring, dashboards, and ranking without touching the grids.

## See also

- Request fields, applicability, response shape -> `analyses/09-facade-terrain.md`
- Geometry / coordinate conventions -> `02-geometry.md`
