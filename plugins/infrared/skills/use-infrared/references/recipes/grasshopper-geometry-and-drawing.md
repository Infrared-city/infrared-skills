# Recipe: Grasshopper geometry in, results out, fast drawing

Rhino geometry to the Infrared SDK, and the results back to Rhino. Read [`grasshopper.md`](grasshopper.md) first (install, client, payloads, non-blocking component).

Python loops that make Rhino objects one by one cost minutes. These recipes use numpy and one bulk copy. Code uses `np` (numpy) and the helpers that this file defines.

## 1. Geometry in

### What the SDK expects

- `polygon`: one GeoJSON `Polygon`, one ring, no holes, WGS84 `[lon, lat]`.
- `buildings`: `{id: {"coordinates": [x, y, z, ...], "indices": [i, j, k, ...]}}` in metres, z up. The origin is the **south-west corner of the polygon bounding box**.
- `vegetation` (GeoJSON Points with `height` and `crownDiameter`) and `ground_materials` (keys `asphalt`, `concrete`, `soil`, `vegetation`, `water`) are in lon/lat.
- `ground_geometry` and `context_geometry` (on the payload) are mesh dicts in the same metre frame as buildings.

The SDK does not repair a bad mesh before it bills. A mesh with inward winding gives a paid, wrong result.

### Rules

- **Make the layer names inputs** (`context`, `designs`) with defaults. One run for each variant.
- **Read Rhino arrays in bulk.** `Mesh.Vertices.ToFloatArray()` and `Mesh.Faces.ToIntArray(True)` (`True` triangulates quads), then one `Marshal.Copy` into numpy. Never iterate over vertices in Python.
- **Round to millimetres** (`np.round(xyz, 3)`): smaller upload, stable geometry hash.
- **Clean each building on its own.** Touching buildings must stay separate. `clean_mesh` joins vertices, drops degenerate and duplicate triangles, fixes the winding and turns closed parts outward. An open shell keeps its direction. Do not "fix" open shells and bake them back into the model.
- **Clean once.** After `clean_mesh`, set `mesh_cleaning="off"` on the payload. Then the server does not clean again.
- **Unique IDs.** Use the object name, add `__1`, `__2` for duplicates, and prefix design buildings with the variant name. Filter by the AOI box before you convert.
- **Terrain** goes into `ground_geometry`. Far hills go into `context_geometry` (low poly). A single building above about 250,000 sensors cannot be split and the server can refuse the job: use a coarser `surface_grid_size`.

### Recipe: Rhino mesh to numpy, in bulk
```python
import numpy as np
import System
from System.Runtime.InteropServices import Marshal

def net_to_np(arr, dtype):
    """Copy a .NET array into numpy with one call."""
    out = np.empty(len(arr), dtype=dtype)
    if len(arr):
        Marshal.Copy(arr, 0, System.IntPtr(int(out.ctypes.data)), len(arr))
    return out

def mesh_arrays(mesh):
    v = net_to_np(mesh.Vertices.ToFloatArray(), np.float32).reshape(-1, 3)
    f = net_to_np(mesh.Faces.ToIntArray(True), np.int32).reshape(-1, 3)
    return v, f
```

A Brep needs a mesh first: `rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.Default)` gives a list. `Append` the parts into one mesh.

### Recipe: site frame

This class maps Rhino model coordinates to the site frame (metres, z up, origin at the AOI south-west corner) and back. It handles model units, the ground level and a rotation to true north.

```python
class SiteFrame:
    """model <-> site metres. `sw_model` is the model point (x, y, z) of the AOI south-west corner at ground level."""

    def __init__(self, sw_model, unit_to_m=1.0, north_deg=0.0):
        self.sw = np.asarray(sw_model, dtype=np.float64)   # model units
        self.k = float(unit_to_m)
        a = np.radians(north_deg)                          # angle of model +y from true north
        self.rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])

    def to_site(self, xyz):
        p = (np.asarray(xyz, dtype=np.float64) - self.sw) * self.k
        p[:, :2] = p[:, :2] @ self.rot.T
        return p

    def to_model(self, xyz):
        p = np.asarray(xyz, dtype=np.float64).copy()
        p[:, :2] = p[:, :2] @ self.rot
        return p / self.k + self.sw
```

The polygon comes from the AOI rectangle in metres and the lon/lat of its south-west corner:

```python
from infrared_sdk.tiling.reanchor import unproject

def aoi_polygon(lon0, lat0, width_m, height_m):
    """GeoJSON polygon of a rectangle. (lon0, lat0) is its SW corner, so site origin = SW corner."""
    ring = [unproject(lon0, lat0, x, y) for x, y in
            [(0, 0), (width_m, 0), (width_m, height_m), (0, height_m), (0, 0)]]
    return {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}
```

Use the SDK projection. Do not write your own lon/lat approximation.

### Recipe: one building to an SDK entry
```python
from infrared_sdk.geometry import clean_mesh

def building_entry(mesh, frame):
    v, f = mesh_arrays(mesh)
    xyz = np.round(frame.to_site(v), 3)               # float64, site metres, mm precision
    c = clean_mesh(xyz, f.ravel())                    # weld, drop bad triangles, fix winding
    return {"coordinates": c.coordinates.tolist(), "indices": c.indices.astype(np.int64).tolist()}
```

Pass the entries as `buildings=` and set `mesh_cleaning="off"` on the payload.

## 2. Results

### Wire types

The raw array keeps the wire type. It is **not** the real value. **Always use the helper.** It gives real values and NaN for "no value".

```python
grid = result.physical_grid(np.float32)        # ground run: a new float32 array, NaN = no value
```

- Use float32 for display and for maths. Low-precision types shift LUT indices at the bin edges. A result grid is read-only.
- Ground grid: row 0 is the **south** row. `result.bounds` is `(min_lon, min_lat, max_lon, max_lat)`.
- `result.min_legend` and `result.max_legend` hold the data range (`None` for PWC class codes). One scale over variants: `infrared_sdk.shared_legend_range([res_a, res_b], mode="trimmed")`.

### Facade result

`result.columns` holds numpy columns for all surfaces. `result.building_aggregates` holds area, mean and peak for each building. The surface ID is `"{building-id}/{surface-index}"`. Use `columns.physical_values(start, end)` (float64), `columns.has_value(i)`, `columns.to_bytes()` and `SurfaceColumns.from_bytes(blob)`.

**Call `render_buffers()` before `client.close()`.** For a stored result, pass `layout=` (see the facade layout page of the docs).

`render_buffers()` gives `SurfaceRenderBuffers`:

- `anchor` (3,) f64: add to all positions. It keeps float32 precise.
- `frames` (9 S,) f32: for each surface, the corner, u step and v step (relative to `anchor`).
- `dims` (3 S,) u32: for each surface, `nu`, `nv` and the first cell index.
- `outline` (6 T,) f32 and `outline_offsets` (S+1,) u32: outline triangles in cell units `(s, t)`. Surface `f` owns triangles `oo[f]:oo[f+1]`.
- `values` (stored type can differ): one for each cell. An invalid cell holds 0. `validity`: u8 bitmap, 1 = has a value.
- A world point of a surface: `p = anchor + corner + s * u_step + t * v_step`.
- Cell `(i, j)` of surface `f` has the index `start_f + j * nu_f + i`.

### Recipe: legend from walls only

Roofs are brighter than walls and make the walls dark. Use the 99.5 percentile of the **wall** cells:

```python
def surface_up(buf):
    """z part of the unit normal of each surface."""
    fr = buf.frames.reshape(-1, 9)
    n = np.cross(fr[:, 3:6], fr[:, 6:9])
    return n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-30)

valid = np.unpackbits(buf.validity, bitorder="little")[:len(buf.values)].astype(bool)
dims = buf.dims.reshape(-1, 3)
wall = np.repeat(np.abs(surface_up(buf)) <= 0.5, (dims[:, 0] * dims[:, 1]).astype(np.int64))
hi = float(np.percentile(buf.values[wall & valid].astype(np.float32), 99.5))
```

Use one legend over all variants, so that the colours compare.

## 3. Draw fast: numpy to Rhino meshes

pythonnet costs about 0.3 microseconds for each object call. A loop over 1.2 million facade cells takes minutes. These recipes take seconds.

- **Never loop over vertices, faces or colours in Python.** Copy numpy arrays with one `memmove`. Do not call `Mesh.Compact()` on a mesh with vertex colours: it re-indexes the vertices.
- **Name the overload.** `Vertices.AddVertices(Point3f[])` can bind the `IEnumerable<Point3d>` overload and fall back to a slow per-vertex loop. Use `AddVertices.Overloads[IEnumerable[rg.Point3f]]`.
- **Set the capacity first**, and **check the counts** after a bulk add. A silent partial mesh is worse than an error.

```python
import ctypes
import System
import Rhino.Geometry as rg
from System.Collections.Generic import IEnumerable
from System.Runtime.InteropServices import GCHandle, GCHandleType

def net_array(src, clr_type):
    """(n, k) contiguous numpy -> .NET Point3f[] / MeshFace[] / Point2f[] in one copy."""
    arr = System.Array.CreateInstance(clr_type, len(src))
    h = GCHandle.Alloc(arr, GCHandleType.Pinned)
    try:
        ctypes.memmove(h.AddrOfPinnedObject().ToInt64(), src.ctypes.data, src.nbytes)
    finally:
        h.Free()
    return arr

def make_mesh(verts, tris, uv=None):
    """Bulk mesh. Point3f = 3 x f32, Point2f = 2 x f32, MeshFace = 4 x i32 (D = C for a triangle)."""
    pts = np.ascontiguousarray(verts, dtype=np.float32)
    t = np.asarray(tris, dtype=np.int32)
    faces = np.ascontiguousarray(np.column_stack([t, t[:, 2]]))
    m = rg.Mesh()
    m.Vertices.Capacity, m.Faces.Capacity = len(pts), len(faces)
    m.Vertices.AddVertices.Overloads[IEnumerable[rg.Point3f]](net_array(pts, rg.Point3f))
    m.Faces.AddFaces(net_array(faces, rg.MeshFace))
    if uv is not None:
        m.TextureCoordinates.AddRange(net_array(np.ascontiguousarray(uv, np.float32), rg.Point2f))
    if m.Vertices.Count != len(pts) or m.Faces.Count != len(faces):
        raise RuntimeError("bulk mesh add incomplete")
    m.Normals.ComputeNormals()
    return m
```

### Recipe: colours through a lookup table

Make a table of 256 colours plus one grey for "no value". Compute an index for each value, then gather.
```python
def lut_index(vals, lo, hi):
    """Value -> LUT index 0..255. 256 = no value. float32 maths."""
    vals = np.asarray(vals, dtype=np.float32)
    nan = np.isnan(vals)
    if not hi > lo:                                       # flat range: mid colour, no divide by zero
        idx = np.full(len(vals), 128, dtype=np.int64)
    else:
        idx = np.trunc((np.where(nan, lo, vals) - lo) / np.float32(hi - lo) * 255)
        idx = np.clip(idx, 0, 255).astype(np.int64)
    idx[nan] = 256
    return idx

# lut: (257, 3) uint8 array: your 256 palette colours, then grey (128, 128, 128)
rgb = lut[lut_index(values, lo, hi)]                      # (n, 3) uint8, one gather
```

For vertex colours, build the .NET colours once. This list is the only Python loop. It is fine up to about one million vertices. For more, use a texture.
```python
from System.Drawing import Color
mesh.VertexColors.AppendColors(
    System.Array[Color]([Color.FromArgb(int(r), int(g), int(b)) for r, g, b in rgb.tolist()]))
```

### Recipe: ground grid

Ground results are a regular grid. Draw one textured rectangle. `rgb = lut[lut_index(grid, lo, hi)]` has shape `(rows, cols, 3)`. Row 0 is south, so v = 0 is at the bottom (`write_png` in section 4 flips the rows). Make each cell `k x k` texels with `np.repeat(np.repeat(rgb, k, 0), k, 1)`. Put the corners from `result.bounds` (moved into the model frame) on a flat rectangle. Or give your cropped terrain mesh planar UVs: `u = (x - x0) / (x1 - x0)`, `v = (y - y0) / (y1 - y0)`. 
## 4. Facades fast: atlas texture

A 1 m facade run gives millions of cells. Two triangles for each cell give millions of triangles: slow to build, to upload and to bake. Instead draw only the **outline** of each surface and paint the cell values as a texture.

The recipe packs each surface as a block of `(nu + 2) x (nv + 2)` texels (one texel for each cell and a border) onto pages. It colours each texel with the LUT colour of its cell. The border repeats the edge cell, so filtering never mixes neighbours. The UV of an outline vertex `(s, t)` is `((x0 + 1 + s) / page_width, (y0 + 1 + t) / page_height)`. Make one mesh for each page. Write the PNGs in parallel threads (zlib releases the GIL).

Rules:

- **Page sizes are powers of two.** Rhino shrinks other sizes and blurs them. It also filters textures linearly and makes mip levels. You cannot switch this off. So keep a border, sort blocks by orientation (down, wall, roof) and fill empty texels with the **page mean colour**. Then a far view does not mix a bright roof into a dark wall. Alpha 0 makes far facades transparent. Grey tints them. Keep the atlas opaque.
- **Choose `k` from the largest block:** `k` is 4, 2 or 1, the largest that fits `4096 // biggest_block`. A very long wall lowers `k` for the whole run. Give long walls their own pages if that hurts.
- Put the PNGs next to the `.gh` file so that a baked material still finds them. Delete the old PNGs of the same variant on each run (a 1 m run writes tens of MB).
- **Test the mapping offline.** Sample the texture at the UV of each cell centre. It must give the cell colour. Repeat this test when you change the packer.

```python
import zlib, struct

PAD = 1

def next_pow2(n):
    return 1 << max(0, int(n) - 1).bit_length()

def pack_pages(nu, nv, size, group):
    """Shelf packer. Returns page, x0, y0 for each surface and the used height of each page."""
    w, h = nu + 2 * PAD, nv + 2 * PAD
    page, x0, y0 = (np.empty(len(w), np.int64) for _ in range(3))
    heights, x, y, shelf = [], 0, 0, 0
    wl, hl = w.tolist(), h.tolist()
    for f in np.lexsort((np.arange(len(h)), -h, group)).tolist():   # group, then tallest first
        if x + wl[f] > size:
            y, x, shelf = y + shelf, 0, 0
        if y + hl[f] > size:
            heights.append(y)
            y, x, shelf = 0, 0, 0
        page[f], x0[f], y0[f] = len(heights), x, y
        x += wl[f]
        shelf = max(shelf, hl[f])
    return page, x0, y0, heights + [y + shelf]

def facade_atlas(buf, lut, lo, hi, size=4096):
    """Render buffers -> (page images, per-page vertices and UVs in world coordinates)."""
    S = len(buf.dims) // 3
    fr = buf.frames.reshape(-1, 9).astype(np.float64)
    nu, nv, start = (buf.dims.reshape(-1, 3).astype(np.int64)).T
    group = np.digitize(surface_up(buf), [-0.5, 0.5])          # 0 down, 1 wall, 2 roof
    biggest = int((np.maximum(nu, nv) + 2 * PAD).max())
    k = 4 if size // biggest >= 4 else 2 if size // biggest >= 2 else 1   # texels for each cell
    cells = size // k                                          # page size in cells; page = size texels
    page, x0, y0, used = pack_pages(nu, nv, cells, group)
    n_pages = len(used)
    ph = np.array([next_pow2(u) for u in used])                # page heights in cells (power of two)

    # Colour of every cell, "no value" = grey.
    valid = np.unpackbits(buf.validity, bitorder="little")[:len(buf.values)].astype(bool)
    vals = np.where(valid, buf.values.astype(np.float32), np.nan)
    cell_rgb = lut[lut_index(vals, lo, hi)]

    # One texel for each padded block position: clamp to the nearest cell (the border repeats the edge).
    w, h = nu + 2 * PAD, nv + 2 * PAD
    f = np.repeat(np.arange(S), w * h)
    t = np.arange(len(f)) - np.repeat(np.cumsum(w * h) - w * h, w * h)
    bx, by = t % w[f], t // w[f]
    cell = start[f] + np.clip(by - PAD, 0, nv[f] - 1) * nu[f] + np.clip(bx - PAD, 0, nu[f] - 1)
    tex_rgb = cell_rgb[cell]
    px, py, pg = x0[f] + bx, y0[f] + by, page[f]

    images = []
    for p in range(n_pages):
        m = pg == p
        mean = tex_rgb[m].mean(axis=0).astype(np.uint8)          # empty texels get the page mean
        img = np.empty((ph[p], cells, 3), np.uint8)
        img[:] = mean
        img[py[m], px[m]] = tex_rgb[m]
        images.append(np.repeat(np.repeat(img, k, 0), k, 1))     # k x k texels for each cell

    # Outline triangles -> world positions and UVs. 3 vertices for each triangle.
    oo = buf.outline_offsets.astype(np.int64)
    tri_surface = np.repeat(np.arange(S), np.diff(oo))
    vs = np.repeat(tri_surface, 3)
    st = buf.outline.reshape(-1, 2).astype(np.float64)
    pos = buf.anchor + fr[vs, 0:3] + st[:, :1] * fr[vs, 3:6] + st[:, 1:] * fr[vs, 6:9]
    uv = np.column_stack([(x0[vs] + PAD + st[:, 0]) / cells,
                          (y0[vs] + PAD + st[:, 1]) / ph[page[vs]]])
    tri_page = np.repeat(page[tri_surface], 3)
    return images, [(pos[tri_page == p], uv[tri_page == p]) for p in range(n_pages)]

def write_png(path, rgb):
    """Dependency free PNG writer. Row 0 of `rgb` is the bottom of the image, so flip it."""
    h, w, _ = rgb.shape
    raw = np.insert(rgb[::-1].reshape(h, -1), 0, 0, axis=1).tobytes()    # filter byte 0 for each row
    def chunk(tag, d):
        return struct.pack(">I", len(d)) + tag + d + struct.pack(">I", zlib.crc32(tag + d))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))
```

Make one mesh for each page. Each triangle has its own 3 vertices:

```python
verts_model = frame.to_model(pos)                         # back to Rhino coordinates
n = len(verts_model) // 3
tris = np.arange(3 * n, dtype=np.int32).reshape(-1, 3)
mesh = make_mesh(verts_model, tris, uv=uv)
```

## 5. Show and bake safely

- **The Grasshopper preview cannot show textures.** It shows vertex colours only. For textured meshes, use a `DisplayConduit` and set `comp.Hidden = True`.
- Rhino Shaded mode does not show textures by default. Rendered mode does.
- **One conduit for each component**, stored in `sticky` by `InstanceGuid`. Empty the old one (`items = []`, then disable) before you make a new one. An orphaned conduit keeps drawing old results and holds its meshes in memory.
- **Bake with tags.** Put `ir_<model> = <component guid>` and `ir_variant = <name>` as user strings on each baked object. On a new bake, delete only the objects that have **this** component's tag. Never delete other objects.
- **Bake on a layer** such as `IR_Result::<variant>`. Create it if it is missing. Do not change existing layers in code on macOS.
- **Textured bake:** one `Rhino.DocObjects.Material` for each page with `SetBitmapTexture(png)`, `DiffuseColor = White`, `MaterialSource = MaterialFromObject`.
- **Store the result in `sticky` before the bake.** A bake error must not lose a paid result.
- Store metadata on the mesh (`UserDictionary`): analysis, variant, legend range, PNG path. `AddMesh` returns `Guid.Empty` for an invalid mesh: check it.

```python
import Rhino
import System.Drawing as sd

class IRConduit(Rhino.Display.DisplayConduit):
    def __init__(self, items):                       # items: [(mesh, png path or None)]
        super().__init__()                           # needed before Enabled = True
        self.items, self.box = [], rg.BoundingBox.Empty
        for mesh, png in items:
            self.box.Union(mesh.GetBoundingBox(False))
            dm = None
            if png:
                dm = Rhino.Display.DisplayMaterial(sd.Color.White)
                dm.SetBitmapTexture(png, True)       # True = diffuse texture slot
                dm.IsTwoSided = True
            self.items.append((mesh, dm))

    def CalculateBoundingBox(self, e):
        e.IncludeBoundingBox(self.box)

    def PostDrawObjects(self, e):
        for mesh, dm in self.items:
            if dm is None:
                e.Display.DrawMeshFalseColors(mesh)
            else:
                e.Display.DrawMeshShaded(mesh, dm)
```

## 6. Query and statistics for each building

Do these steps with numpy on whole arrays. A Python loop over groups of 1800 buildings takes many seconds. A composite-key `argsort` and `reduceat` take under a second.

### Per-building statistics from the columns

```python
def building_stats(columns, mask=None):
    """Area-weighted mean, min and max of every building. `mask` selects cells. No Python loop over buildings."""
    ids = np.asarray(columns.ids, dtype=str)
    names, surf_b = np.unique(np.char.rpartition(ids, "/")[:, 0], return_inverse=True)
    n_cells = np.diff(columns.cell_offsets)
    cell_b = np.repeat(surf_b, n_cells)
    w = np.repeat(columns.grid_size.astype(np.float64) ** 2, n_cells)   # cell area; edge cells are partly covered
    v = columns.physical_values()                                       # float64, NaN = no value
    ok = np.isfinite(v) if mask is None else np.isfinite(v) & mask
    cb, v, w = cell_b[ok], v[ok], w[ok]

    n = len(names)
    area = np.bincount(cb, w, n)
    mean = np.bincount(cb, w * v, n) / np.maximum(area, 1e-12)
    lo, hi = np.full(n, np.inf), np.full(n, -np.inf)
    np.minimum.at(lo, cb, v)                                            # unbuffered, but still vectorised
    np.maximum.at(hi, cb, v)
    return names, area, mean, lo, hi
```

`result.building_aggregates` already gives area, mean and peak. Use this recipe for other statistics or a subset of cells.

### Query by region (boxes or footprints)

Make the world centre of every cell with numpy: for cell `k` of surface `f`, `i = (k - start_f) % nu_f`, `j = (k - start_f) // nu_f`, and the centre is `anchor + corner_f + (i + 0.5) * u_f + (j + 0.5) * v_f`. Use `np.repeat(np.arange(S), nu * nv)` to find `f` for every cell. Move the centres to model coordinates with `frame.to_model`. Then `inside = np.all((c >= box_min) & (c <= box_max), axis=1) & valid` selects the cells of a box. Pass `inside` as `mask` to `building_stats` for a box query. For ground results, cell `(row, col)` has its centre at `(col + 0.5) / cols` and `(row + 0.5) / rows` of `result.bounds` (row 0 is south).

A query runs on the UI thread after each run. Keep it fast and memoise it. In a Rhino 8 script component, geometry inputs without a type hint arrive as **Guids in `ghdoc`**. Look them up in `scriptcontext.doc`, then in `RhinoDoc.ActiveDoc`.
