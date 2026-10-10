# Blender: facade and roof results on your 3D model

Scripts in `cookbook/scripts/blender/`: `export_buffers.py` (SDK side), `blender_facade_results.py`
(Blender 4.5 LTS, headless), `legend_overlay.py` (Pillow). Tested on 1,843 buildings, 3.2 Mio cells:
4 analyses, 2 views each and the `.blend` in 24 s.

## The route

No mesh per cell. Save the render buffers, then in Blender pack every frame into ONE texture atlas
(one texel per cell, `Closest` sampling) and build ONE mesh from the outline triangles.
Analyses on the same geometry and grid return the SAME layout (only `values` change): build the
atlas packing and mesh once, add one atlas image and material per analysis. The script checks
the layout of every file and stops on a mismatch.

```python
from export_buffers import save_buffers

svf, solar = client.run_area_and_wait([svf_request, solar_request], polygon, buildings=buildings)
sw = (sw_x, sw_y)  # the polygon's south-west corner in YOUR model frame, metres
save_buffers(svf, "svf.npz", buildings, frame_offset=sw)
save_buffers(solar, "solar.npz", buildings, frame_offset=sw)
```

```bash
Blender -b --factory-startup --python-exit-code 1 --python blender_facade_results.py -- \
  --analysis "svf.npz|Sky view factor (%)|0|100" \
  --analysis "solar.npz|Solar radiation (kWh/m2)|0|140" \
  --context model.obj --trees trees.json --out renders/
python legend_overlay.py renders/
```

## The buffer layout

| Array | Shape | Use |
|---|---|---|
| `frames` | `(S, 9)` | `corner`, `u_step`, `v_step`, relative to `anchor` |
| `dims` | `(S, 3)` | `nu`, `nv`, start of the frame's cells in `values` |
| `outline` | `(T, 3, 2)` | `(s, t)` in cell units, `0..nu` and `0..nv` |
| `outline_offsets` | `(S + 1,)` | frame `f` owns triangles `offsets[f]:offsets[f+1]` |
| `values`, `valid` | `(C,)` | cell `k = start + j * nu + i` |

Vertex: `anchor + corner + s * u_step + t * v_step`. UV in the atlas block at `(px, py)`:
`((px + s) / W, (py + t) / H)`. Pad each block by 1 texel and copy the border cells into it.
Build meshes with `foreach_set`, not `from_pydata`.

## Traps

| Trap | Symptom | Do this |
|---|---|---|
| Invalid cells hold `0`, not NaN | Gaps paint as the lowest colour | Test `valid`; paint gaps neutral grey |
| Filmic / AgX view transform | The colour scale shifts | `view_transform = "Standard"` |
| Results are in the polygon-SW frame | Results sit off your model | Add `frame_offset` to every vertex |
| Analysed buildings also in the context | Z-fighting | Remove them from the context mesh |
| Camera `clip_end` is 100 m | Half the city is missing | `clip_end = 20000` |
| Script error, exit code 0 | A failed build looks green | `--python-exit-code 1` |
| Principled BSDF in EEVEE | First frame ~11 s (shader compile) | Diffuse + Emission: ~1.5 s |
| Non-planar faces | Saw-tooth stripes | Real data: one frame per triangle |
| Auto-scaled colours | Renders cannot be compared | One fixed domain per analysis ([rendering](rendering-results-well.md)) |

Open city meshes (no floor, holes) keep their authored winding in the SDK. A tool that flips
open shells by signed volume turns parts inside out: whole buildings then read 0. Check with
back-face culling on; close the holes first if a tool in your pipeline flips them.
