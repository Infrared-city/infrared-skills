# Integrating Surface Results (rendering facade/roof grids on your own model)

How to take a `SurfaceAnalysisResult` (see `analyses/09-facade-terrain.md`) and display it on the geometry you submitted — in a BIM tool, game engine, or web viewer. Requires `infrared-sdk >= 0.4.12`.

## The contract, in rendering terms

Every entry in `result.surfaces` is keyed `"{building-id}/{surface-index}"` — the building id is **your own key** from the `geometries` you submitted, so results map straight back onto your elements. Each `SurfaceSensorGrid` is a planar sensor grid in its own UV frame:

- `origin` — 3D anchor of the grid (same coordinate frame as your submitted mesh, metres)
- `u_axis`, `v_axis` — unit vectors in the surface plane
- `grid_size` — cell edge length (your `surface_grid_size`)
- `nu`, `nv` — grid dimensions; `values` has `nu * nv` entries, **row-major in v** (`index = j * nu + i`)
- `values[k] is None` — masked cell: its centre lies outside the surface's true footprint. Never zero-fill; cut or skip these.
- `cell_area[k]`, `cell_tris[k]` — the cell's real covered area and its exact clipped triangle geometry (flat `[x,y,z, ...]`, 9 floats per triangle)

World position of cell (i, j)'s corner: `origin + u_axis * (i * grid_size) + v_axis * (j * grid_size)`; add one `grid_size` step along `u`/`v` for the far corners.

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

## Which route

| Need | Route |
|---|---|
| Interactive city-scale view, smooth gradients | 1 (texture) |
| Exact printable/exportable geometry, crisp edges | 2 (`cell_tris`) |
| Best of both | 1 for the overview, 2 on demand for selected elements |

## Display tips

- **Normalise facades separately from roofs.** For solar radiation especially, horizontal surfaces dominate the range (roofs can sit at 3&ndash;5&times; facade values in summer), compressing all facade variation into the bottom of a shared colormap. Classify by `v_axis` (vertical `v_axis` &rarr; facade) or by value clustering, and give facades their own scale when facades are the story.
- **Interpolation is a display choice, not an API request.** The grid is the lossless raw result; bilinear/bicubic filtering at render time produces the smooth transitions. Don't ask for (or build) pre-smoothed meshes — you'd bake in one display style and lose the sensor truth.
- Per-building rollups (`result.aggregates["buildings"]`: `area` / `mean` / `peak`) are ready-made for element-level coloring, dashboards, and ranking without touching the grids.

## See also

- Request fields, applicability, response shape -> `analyses/09-facade-terrain.md`
- Geometry / coordinate conventions -> `02-geometry.md`
