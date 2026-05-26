# Recipe: Infrared SDK Patterns in Rhino 8 Grasshopper

Calling the Python SDK from Rhino 8's Grasshopper Python 3 Script components. Small reusable patterns — paste the ones you need, mix and match. Not a full component template; the goal is a fast on-ramp for anyone building their own.

## When this applies

User has Rhino 8 (CPython 3.9 Script Editor) and wants to call the SDK from Grasshopper — typical: fetch buildings/trees/ground for an AOI, submit BYO meshes to a simulation, render the result as a heatmap on the canvas, save outputs next to the `.gh` file. For shipping a compiled `.gha` via Yak, use Rhino's own .NET docs — this recipe is Python-only.

## Install the SDK once per Rhino session

Rhino 8 ships **CPython 3.9** in the Script Editor. Install via the `# r:` directive at the top of any one Python 3 script:

```python
#! python 3
# r: infrared-sdk
```

Without `# venv:`, the package lands in the shared default env (`~/.rhinocode/py39-rh8/site-envs/default-<id>/`) and **every other Python 3 script in the session** can `import infrared_sdk` with no header. A failed install marks the env with a `.corrupt` sentinel — recover by deleting the env folder. If the SDK isn't on PyPI yet for Python 3.9, build a wheel from source (`uv build --wheel --out-dir <dest>`) and reference it by absolute path: `# r: /abs/path/to/infrared_sdk-x.y.z-py3-none-any.whl`.

---

## Pattern 1 — Component scaffold (SDK mode)

Always click "Convert to GH_ScriptInstance" in the editor — it auto-derives inputs from the `RunScript` signature and unlocks `BeforeRunScript` lifecycle hooks. The skeleton:

```python
#! python 3
# r: infrared-sdk

import Grasshopper

class MyComponent(Grasshopper.Kernel.GH_ScriptInstance):
    def BeforeRunScript(self):
        # Register outputs here (Pattern 2). Never change topology in RunScript.
        pass

    def RunScript(self, api_key: str, run: bool):
        # Inputs auto-add from this signature.
        # Use `ghenv.Component` (NOT self.Component — that's None in Rhino 8 SDK mode).
        return None  # return a tuple matched to registered outputs
```

## Pattern 2 — Auto-register outputs

Inputs auto-derive from the `RunScript` signature; outputs do not. Returning `(a, b, c)` does NOT create three output sockets. Register them programmatically in `BeforeRunScript`:

```python
def BeforeRunScript(self):
    import clr
    clr.AddReference("RhinoCodePluginGH")
    from RhinoCodePluginGH.Parameters import ScriptVariableParam
    import Grasshopper.Kernel as ghk
    import Rhino

    desired = [
        ("polygon", "Poly", "GeoJSON polygon", ghk.GH_ParamAccess.item, str),
        ("heatmap", "Heat", "Result mesh", ghk.GH_ParamAccess.item, Rhino.Geometry.Mesh),
    ]
    params = ghenv.Component.Params
    if [p.Name for p in params.Output] == [d[0] for d in desired]:
        return  # idempotent

    while params.Output.Count > 0:
        params.UnregisterOutputParameter(params.Output[0], True)
    for name, nick, desc, access, hint_t in desired:
        p = ScriptVariableParam(name)
        p.NickName, p.Description, p.Access = nick, desc, access
        try:
            p.TypeHints.Select(clr.GetClrType(hint_t))
        except Exception:
            pass  # falls back to generic object if T isn't in the catalog
        p.CreateAttributes()
        params.RegisterOutputParam(p)
    ghenv.Component.VariableParameterMaintenance()
    params.OnParametersChanged()
    ghenv.Component.Attributes.ExpireLayout()
```

**Gotchas, paid for in blood:**
- Use `RhinoCodePluginGH.Parameters.ScriptVariableParam` — NOT stdlib `Param_Mesh` / `Param_String`. The Script runner casts every output to `ScriptVariableParam` and throws otherwise. Diagnostic: any `Unable to cast object of type '...' to type 'ScriptVariableParam'` exception means you used the wrong base class.
- Topology changes only in `BeforeRunScript`; the GH SDK forbids it during solve.
- `TypeHints.Select(T)` picks from a fixed catalog: `str`, `int`, `float`, `bool`, `Mesh`, `Curve`, `Brep`, `Point3d`, `Vector3d`, `Plane`, `System.Drawing.Color`. Anything else silently falls back to generic-object — wrap in try/except.
- **First-solve count race:** the runner caches the expected output count from *before* `BeforeRunScript` fires. Use an adaptive return on the last line of `RunScript`:
  ```python
  results = [a, b, c]
  n = ghenv.Component.Params.Output.Count
  return tuple(results[:n] + [None] * (n - len(results)))
  ```
  Self-heals after the first solve.

## Pattern 3 — Sticky state across recomputes

`scriptcontext.sticky` survives between solves within the Rhino session. Scope keys with `ghenv.Component.InstanceGuid` so duplicated components don't collide:

```python
import scriptcontext as sc
SCOPE = "ir::{}".format(ghenv.Component.InstanceGuid)
sc.sticky[SCOPE + "::last_result"] = result
prev = sc.sticky.get(SCOPE + "::last_result")
```

## Pattern 4 — Off-UI-thread work

Rhino 8 Script components do NOT support `# async: true`. The supported async pattern is a worker thread that calls `ExpireSolution(True)` to re-fire the component when the work is done:

```python
import threading

def _worker(component, key):
    result = some_long_call()              # SDK call, file I/O, etc.
    sc.sticky[key] = result
    component.ExpireSolution(True)         # safe to call from a worker thread

key = SCOPE + "::result"
if start and key not in sc.sticky:
    threading.Thread(target=_worker, args=(ghenv.Component, key), daemon=True).start()

result = sc.sticky.pop(key, None)          # consumed on the next solve
```

Use this for: SDK calls (`run_area_and_wait` blocks for 30s–5min), browser pickers (next pattern), file I/O — anything that shouldn't freeze the GH canvas.

## Pattern 5 — Browser-based AOI picker

A real basemap beats hand-typed bounding boxes. Open the user's browser to an inline Leaflet page served from an in-process `http.server`, POST the GeoJSON back, stash in sticky, re-fire the component. This same shape (in-process server + native browser) is a generic UI escape hatch any time GH's native widgets aren't enough — color pickers, parameter sliders, data tables — not just AOI picking.

```python
import socket, threading, webbrowser, json
from http.server import BaseHTTPRequestHandler, HTTPServer

PICKER_HTML = b"""<!doctype html>...inline Leaflet + leaflet-draw; POST /polygon..."""

def start_picker(component, sticky_key):
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(PICKER_HTML)
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            sc.sticky[sticky_key] = json.loads(self.rfile.read(n))
            self.send_response(200); self.end_headers()
            component.ExpireSolution(True)
        def log_message(self, *a): pass  # silence the default stdout spam

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    webbrowser.open("http://127.0.0.1:{}/".format(port))
```

**Learnings:**
- `ExpireSolution(True)` from a worker thread is supported and reliable.
- Pick a free port with `socket.bind(("127.0.0.1", 0))` — never hardcode one.
- Stash a `last_pick` boolean in sticky and fire only on the **rising edge** of the input boolean — otherwise the picker reopens on every recompute.
- The server keeps running until Rhino exits. Pro: reusable across solves with no warm-up. Con: shut it down explicitly (`srv.shutdown()`) if you care about port reuse during one session.
- Scope every sticky key by `InstanceGuid` (Pattern 3) — duplicating the component otherwise hijacks the original's state.

## Pattern 6 — DotBim ↔ Rhino Mesh

The SDK accepts and returns building/vegetation geometry as flat DotBim arrays. Two short helpers cover both directions:

```python
def dotbim_to_mesh(coords, indices):
    import Rhino.Geometry as rg
    m = rg.Mesh()
    for i in range(0, len(coords), 3):
        m.Vertices.Add(coords[i], coords[i+1], coords[i+2])
    for i in range(0, len(indices), 3):
        m.Faces.AddFace(int(indices[i]), int(indices[i+1]), int(indices[i+2]))
    m.Normals.ComputeNormals(); m.Compact()
    return m

def mesh_to_dotbim(mesh, mesh_id):
    coords, indices = [], []
    for v in mesh.Vertices:
        coords.extend([float(v.X), float(v.Y), float(v.Z)])
    for f in mesh.Faces:
        if f.IsTriangle:
            indices.extend([int(f.A), int(f.B), int(f.C)])
        else:  # triangulate quads
            indices.extend([int(f.A), int(f.B), int(f.C),
                            int(f.A), int(f.C), int(f.D)])
    return {"mesh_id": int(mesh_id), "coordinates": coords, "indices": indices}
```

Pass to the SDK as `client.run_area_and_wait(payload, polygon, buildings={"0": dotbim_dict, "1": ...})`. Keys are stringified ints.

## Pattern 7 — Locate the .gh file

For saving outputs next to the user's project, ask Grasshopper for its document path:

```python
import os
def gh_doc_dir():
    doc = ghenv.Component.OnPingDocument()
    if doc and doc.FilePath:
        return os.path.dirname(doc.FilePath)
    return os.path.expanduser("~/Desktop")  # unsaved-file fallback

out_dir = os.path.join(gh_doc_dir(), "ir_results")
os.makedirs(out_dir, exist_ok=True)
```

## Pattern 8 — Save PNG / GeoTIFF

**Use Pillow, not `Bitmap.SetPixel`** — the .NET per-pixel API takes ~5–15 seconds for a 512×512 grid; Pillow finishes in well under a second.

```python
# r: Pillow
from PIL import Image
import numpy as np

# Color your grid into an HxWx4 RGBA array (vectorise the ramp), then:
img = Image.fromarray(np.flipud(rgba), "RGBA")   # flipud → north-up PNG
img.save(os.path.join(out_dir, "{}.png".format(stamp)))
```

For a real GeoTIFF (QGIS-ready), add `# r: rasterio` once (heavy ~30s install, one-shot):

```python
# r: rasterio
import rasterio
from rasterio.transform import from_bounds

# AreaResult.bounds = (lon_min, lat_min, lon_max, lat_max)
with rasterio.open(path, "w", driver="GTiff",
                   height=h, width=w, count=1, dtype=grid.dtype,
                   crs="EPSG:4326",
                   transform=from_bounds(lon_min, lat_min, lon_max, lat_max, w, h)) as dst:
    dst.write(np.flipud(grid), 1)  # GeoTIFF row 0 = north; SDK grid row 0 = south
```

A 2-line JSON sidecar (analysis type, bounds, legend min/max, timestamp) saved alongside the PNG covers the case where the user later wants `gdal_translate` to promote PNG → GeoTIFF.

## Pattern 9 — Heatmap mesh from a numpy grid

Project the SDK's lon/lat bounds to local meters (equirectangular is fine for AOIs ≲ 5 km), build a vertex grid, color each vertex, add quad faces. GH's canvas previews vertex-colored meshes directly:

```python
import math, Rhino.Geometry as rg

# SDK grid is SW-anchored: merged_grid[0, 0] = south + west.
def grid_to_mesh(grid, bounds_lonlat, lo, hi, ramp):
    h, w = grid.shape
    lon_min, lat_min, lon_max, lat_max = bounds_lonlat
    R = 6378137.0
    def to_xy(lon, lat, lon0, lat0):
        x = (lon - lon0) * math.cos(math.radians(lat0)) * math.pi / 180 * R
        y = (lat - lat0) * math.pi / 180 * R
        return x, y
    lon0, lat0 = (lon_min + lon_max) / 2, (lat_min + lat_max) / 2
    x0, y0 = to_xy(lon_min, lat_min, lon0, lat0)
    x1, y1 = to_xy(lon_max, lat_max, lon0, lat0)
    dx, dy = (x1 - x0) / max(w - 1, 1), (y1 - y0) / max(h - 1, 1)

    m = rg.Mesh()
    for j in range(h):
        for i in range(w):
            m.Vertices.Add(x0 + i * dx, y0 + j * dy, 0.0)  # j=0 → south, matches SDK
    for j in range(h):
        for i in range(w):
            v = grid[j, i]
            m.VertexColors.Add(*((180, 180, 180) if v != v else ramp(v, lo, hi)))
    for j in range(h - 1):
        for i in range(w - 1):
            a = j * w + i
            m.Faces.AddFace(a, a + 1, a + w + 1, a + w)
    m.Normals.ComputeNormals(); m.Compact()
    return m
```

`ramp(v, lo, hi)` returns an `(r, g, b)` int tuple — keep your color logic in one place so PNG and mesh paths stay consistent.

## Pattern 10 — Visible logging

Three places — pipe to all three so the user finds the failure no matter where they look:

```python
import time, Rhino, Grasshopper
LOG_KEY = SCOPE + "::log"

def log(msg):
    line = "[{}] {}".format(time.strftime("%H:%M:%S"), msg)
    print(line)                                                # editor panel
    Rhino.RhinoApp.WriteLine("[ir] " + line)                   # Rhino command line
    sc.sticky[LOG_KEY] = sc.sticky.get(LOG_KEY, "") + line + "\n"

# At the end of RunScript, surface the whole log on the component bubble:
ghenv.Component.AddRuntimeMessage(
    Grasshopper.Kernel.GH_RuntimeMessageLevel.Remark,
    sc.sticky.get(LOG_KEY, ""))
```

The yellow "i" (Remark) bubble is the most discoverable for non-coders — they hover, they see the log without opening the Script Editor.

## Pitfalls

- **`run_area_and_wait` blocks the GH solve thread** for 30s–5min depending on AOI size. Wrap in Pattern 4 for anything beyond a one-off demo.
- **`Bitmap.SetPixel` is slow** on grids over ~100×100. Always use Pillow (Pattern 8).
- **Topology changes only in `BeforeRunScript`** — never add/remove params during solve.
- **First-solve count race** — use the adaptive return pattern (Pattern 2).
- **`ghenv.Component`, not `self.Component`** — the latter is None in Rhino 8 SDK mode.
- **Sticky keys collide** between duplicated components unless scoped by `InstanceGuid` (Pattern 3).
- **`# async: true` doesn't work** on Script components — use threading + `ExpireSolution(True)`.
- **Grid orientation:** SDK `merged_grid[0, 0]` is the **SW** corner. Flip rows for any image format that expects row 0 = top (PNG, JPEG); leave alone for GIS formats with proper transforms (GeoTIFF).

## When NOT to use this recipe

- **Production `.gha` plugin** — out of scope; see Rhino's own Yak / .NET docs.
- **High-frequency real-time interaction** (live wind preview, etc.) — wrong tool; reach for Hops or a WebSocket bridge.
- **Rhino 7 (IronPython 2.7)** — the SDK doesn't support Py2; everything above assumes Rhino 8 CPython 3.9.

## See also

- [`byo-inputs.md`](../byo-inputs.md) — general BYO data shapes (DotBim format).
- [`interpretation/grid-conventions.md`](../interpretation/grid-conventions.md) — authoritative `merged_grid` layout, NaN handling, lon/lat corner ordering.
