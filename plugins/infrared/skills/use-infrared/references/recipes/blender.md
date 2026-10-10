# Blender: facade and roof results on your 3D model

How to show an `analysis_surfaces` run (facades and roofs) in Blender, fast and with exact cells.
Scripts in `cookbook/scripts/blender/`: `export_buffers.py` (SDK side), `blender_facade_results.py`
(Blender), `legend_overlay.py` (any Python with Pillow).
Tested: Blender 4.5.3 LTS (headless), `infrared-sdk` 1.0.0, Hong Kong, 1.2 km x 1.2 km:
1,843 buildings, 276,934 frames, 3.2 million cells, 787k outline triangles. Four analyses, two
1920 x 1200 views each, and the `.blend`: 24 s. One analysis, three views: 8 s.

## The route

Do not make one mesh per cell. Use the render buffers:

1. Python (your SDK environment): run, then save the render buffers (`save_buffers`).
2. Blender: pack every frame into ONE texture atlas, one texel for each cell.
3. Blender: build ONE mesh from the outline triangles. Map each frame to its atlas block.
4. Sample the atlas with `Closest` interpolation. The cells stay crisp.

The mesh holds only the outline triangles (787k above), not 3.2 million cell quads.

## Several analyses: one layout

Analyses that ran on the same geometry and surface grid return the SAME layout: `anchor`,
`frames`, `dims`, `outline` and `outline_offsets` are byte-identical. Only `values` change.
So build the atlas packing and the mesh once, then add one atlas image and one material for
each analysis. In the `.blend`, a change of analysis is a material swap. The script checks the
layout of every file and stops on a mismatch. Cost on the area above: the shared part about
1.6 s once, about 1.2 s for each extra analysis.

## Step 1: save the buffers (SDK side)

```python
from export_buffers import save_buffers

svf, solar = client.run_area_and_wait([svf_request, solar_request], polygon, buildings=buildings)
sw = (sw_x, sw_y)  # the polygon's south-west corner in YOUR model frame, metres
save_buffers(svf, "svf.npz", buildings, frame_offset=sw)
save_buffers(solar, "solar.npz", buildings, frame_offset=sw)
```

Then, in Blender (each `--analysis` is `file|label|vmin|vmax`, with a fixed domain):

```bash
Blender -b --factory-startup --python-exit-code 1 --python blender_facade_results.py -- \
  --analysis "svf.npz|Sky view factor (%)|0|100" \
  --analysis "solar.npz|Solar radiation (kWh/m2)|0|140" \
  --context model.obj --trees trees.json --out renders/
python legend_overlay.py renders/
```

Blender's Python has `numpy`, but no `pyproj` and no `PIL`. Convert lon/lat (trees) to metres,
and draw legends, outside Blender.

## Step 2 and 3: the buffer layout

| Array | Shape | Use |
|---|---|---|
| `frames` | `(S, 9)` | `corner`, `u_step`, `v_step`, relative to `anchor` |
| `dims` | `(S, 3)` | `nu`, `nv`, start of the frame's cells in `values` |
| `outline` | `(T, 3, 2)` | `(s, t)` in cell units, `0..nu` and `0..nv` |
| `outline_offsets` | `(S + 1,)` | frame `f` owns triangles `offsets[f]:offsets[f+1]` |
| `values`, `valid` | `(C,)` | cell `k = start + j * nu + i` (row-major in v) |

- Vertex position: `anchor + corner + s * u_step + t * v_step`.
- Cell of a point: `(floor(s), floor(t))`. So the UV of a vertex in its atlas block at `(px, py)` is
  `((px + s) / W, (py + t) / H)`. Texel `(px + i, py + j)` holds cell `(i, j)`.
- Leave 1 texel of padding around each block. Copy the border cells into it, or an edge texel can
  read the neighbour block.
- Build the mesh with `foreach_set` (`vertices.co`, `loops.vertex_index`, `polygons.loop_start`,
  `uv_layers[...].data.uv`). `from_pydata` is much slower at this size.

## Traps (each one cost time)

| Trap | Symptom | Do this |
|---|---|---|
| Invalid cells hold `0`, not NaN | Gaps paint as the lowest colour | Test `valid`. Paint gaps a neutral grey that is not on the scale |
| Filmic / AgX view transform | The colour scale shifts, the legend lies | `scene.view_settings.view_transform = "Standard"` |
| Frames are in the polygon-SW frame | Results sit off your model | Add the polygon SW corner (in your model frame) to every vertex: `frame_offset` |
| Results and source buildings at the same place | Z-fighting | Remove the analysed buildings from the context. Keep only the others in grey |
| Camera `clip_end` is 100 m by default | Half the city is missing | `cam.data.clip_end = 20000` |
| Script error, exit code 0 | A failed build looks green | `Blender -b --factory-startup --python-exit-code 1 --python script.py -- args` |
| Non-planar faces (twisted tower) | Saw-tooth stripes | Real data: every triangle is its own frame. Not a render fault |
| Open shells (city models such as LandsD) | Whole buildings at 0 on a platform upload | The kernel keeps the authored winding of an open shell. Do not run a signed-volume flip on open meshes yourself. See below |
| One fixed domain per analysis | Each render auto-scales | SVF `[0, 100]`, see [rendering-results-well.md](rendering-results-well.md) |
| Principled BSDF in EEVEE | The first frame takes ~11 s (shader compile) | Diffuse + Emission: first frame ~1.5 s, same look at city scale |
| Importing context you then delete | Seconds lost on a full-area run | Scan the `o` names first. Import only when some building is not analysed |

## Open city meshes and winding

City models are often open shells: no floor, holes, one building split into many parts.
A signed-volume test on an open shell depends on the origin. Its sign is not a winding signal.

- The SDK kernel keeps the winding of open parts as authored and orients only closed parts.
- A tool that flips by signed volume can turn parts inside out. Their sensors are then inside the
  building, and the whole building reads 0. Measured on a Hong Kong file: 4,785 of 16,545 parts.
- If a tool in your pipeline does this, close the holes first (fan-cap every boundary loop). The
  volume is then the same from any origin.
- Check: render with back-face culling on. An inside-out part shows as hollow.

## Make it look good

- One `Sun` light, angle about 3 degrees, plus a soft sky colour. EEVEE Next renders a frame in
  about 1 s in background mode.
- Result material: Diffuse plus Emission, both from the atlas, emission strength about 0.35, so
  the scale stays readable in shade.
- Context buildings mid grey (`0.36`), ground near black: the results carry the colour.
- Composite the legend after the render (`legend_overlay.py`): fixed domain, label, analysis name.
