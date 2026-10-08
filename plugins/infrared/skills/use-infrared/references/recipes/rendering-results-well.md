# Making results look good on geometry

Read this before your first render. Every trap below produces a picture that *looks* like a
result: plausible enough to screenshot, wrong enough to mislead. None of them are model problems.

The Infrared platform renders the same results. This page shows what it does differently.
Grid rules: [../interpretation/grid-conventions.md](../interpretation/grid-conventions.md).
The cookbook notebooks use `cookbook/notebooks/ir_plot.py`; the TypeScript apps use the same rules.

## 0. Read values with the helper, never the raw array

The stored type of a result can differ by analysis and can change. A raw read gives wrong
numbers or raw bits. Always decode with the helper first:

| Result | Python | TypeScript |
|---|---|---|
| Ground grid | `result.physical_grid()` (NaN = no value) | `areaGridValuesF32(result)` |
| Facades and roofs | `result.columns.physical_values()`, `result.columns.render_buffers()` | `surfaceRenderBuffers(columns)` |
| Legend range | `legend_range(result)`, `shared_legend_range([...])`, `registry_fixed_range(type)` | `legendRange`, `sharedLegendRange`, `registryFixedRange` |

Decode one time and cache the array. Do not decode on each mouse move.

---

## 1. Auto-scaling to the grid's own min/max

**The failure:** each render is normalised to its own min and max. Two runs of the same analysis
get two scales, so the same value gets two colours. A baseline and a redesign cannot be compared,
and a flat grid is stretched until noise looks like structure.

**The rule:** the *analysis* sets the colour map and the scale, not the run. For the scale, choose one of:

- the fixed range from the public colour registry: `registry_fixed_range(analysis_type)`.
  It has a range for UTCI (-40 to 46 degrees C) and wind speed (0 to 20 m/s);
- a fixed domain of your own for the other analyses (table below), the same for all runs that you compare;
- one pooled range over all results that you compare: `shared_legend_range([a, b])`;
- for one result alone, `result.min_legend` and `result.max_legend` (its exact range).

```python
import matplotlib.pyplot as plt
from infrared_sdk import registry_fixed_range, shared_legend_range

STYLE = {                                  # colour map and unit for each analysis (as ir_plot.py)
    "sky-view-factors": ("viridis", "%", (0, 100)),
    "daylight-availability": ("cividis", "%", (0, 100)),
    "direct-sun-hours": ("magma", "h", None),          # 0 to the sun hours in YOUR window
    "solar-radiation": ("inferno", "kWh/m2", None),    # depends on the window: fix it per study
    "thermal-comfort-statistics": ("YlOrRd", "% of hours", (0, 100)),
    "thermal-comfort-index": ("RdYlBu_r", "degC", None),   # registry: -40 to 46
    "wind-speed": ("YlGnBu", "m/s", None),                 # registry: 0 to 20, top bin open
}
cmap, unit, domain = STYLE[result.analysis_type]
vmin, vmax = domain or registry_fixed_range(result.analysis_type) or (result.min_legend, result.max_legend)
plt.imshow(result.physical_grid(), origin="lower", cmap=cmap, vmin=vmin, vmax=vmax)
plt.colorbar(label=unit)
# Two scenarios on one scale: vmin, vmax = shared_legend_range([baseline, proposed])
```

Wind has an **open** top bound: values above the top take the last colour, and the legend
says "> 20". Clamp out-of-range values to the end colours. Never leave them without colour.
Pedestrian wind comfort is categorical: see section 5.

**Exception: difference plots.** Deltas go negative. See section 6.

---

## 2. Masked cells rendered as zero

**The failure:** NaN (no value) is mapped to 0. Building footprints and everything outside the polygon
are painted as the worst value: a solid blob that reads as a result. Statistics shift the same way.

**The rule:** no value means no data, not zero. Keep NaN. Render it transparent.

```python
import numpy as np
import matplotlib.pyplot as plt

cmap = plt.get_cmap("viridis").copy()
cmap.set_bad(alpha=0.0)                      # NaN -> fully transparent
plt.imshow(np.ma.masked_invalid(result.physical_grid()), cmap=cmap,
           origin="lower", vmin=vmin, vmax=vmax)
```

For facade results, `columns.physical_values()` already gives NaN for masked cells. Use `np.nanmean`.
In a GPU pipeline, discard the cell. Test the validity bit of the render buffers
([../surface-results-integration.md](../surface-results-integration.md)).

### The mirror image: real zeros treated as missing

A surface can come back with `mean = peak = 0.0` and every cell present: a party wall, a light well,
an elevation that a neighbour blocks. That is the answer. On a dense scene, a large share of facades can be exact
zeros, and the scene mean changes a lot with or without them. Decide which you report, and say so:

```python
means = result.columns.mean
lit = means[means > 0.0]
# "mean over all analysed facades"       -> means.mean()
# "mean over facades that see any sun"   -> lit.mean()
```

Keep zeros visible on the scale. A wall in permanent shade is a finding.

---

## 3. Giving facades their own scale

**The failure:** a facade-only run looks washed out on the shared scale, so you rescale it to the
facade percentiles. The facade now shows contrast that is not there, and two surfaces of one building
are no longer comparable.

**The rule:** roofs and facades share **one** scale. Roofs sit high (open sky), facades low.
That contrast is the reading.

```python
vmin, vmax = result.min_legend, result.max_legend      # one scale for the whole scene
```

A facade-only rescale is allowed as a deliberate and labelled exception ("facades only, 5th to 95th
percentile"). Never silent.

---

## 4. Picking a rendering route (and paying for the wrong one)

Two routes read the same result: render buffers or textures (light, smooth gradients, stepped edges)
and exact cell triangles (crisp edges, about 96 % of the download).

**The failure:** asking for cell triangles on every run. `emit_cell_tris` is off by default for a
reason. `values` and every aggregate are identical either way. Only the exact outlines change.

```python
from infrared_sdk import SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

# Overview or analysis: the default. Small download.
overview = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                           analysis_surfaces="all", surface_grid_size=1.0)

# One selected building or an export: ask for the exact outlines.
detail = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                         analysis_surfaces="all", surface_grid_size=1.0, emit_cell_tris=True)
```

Draw the overview from render buffers. Ask for triangles for the building that the user selects.
Details: [../surface-results-integration.md](../surface-results-integration.md).

---

## 5. A continuous colormap on categorical output

**The failure:** `pedestrian-wind-comfort` returns comfort **class indices** (for Lawson LDDC
`0`=A … `4`=E; other criteria have other classes, listed in `result.legend`), not a measurement. Run a continuous ramp over them and you get colours
*between* classes, which mean nothing — class B blends into class C, and a viewer reads a
smooth gradient where the standard defines five hard bins.

**The rule:** discrete colormap, discrete legend, `interpolation="nearest"`.

```python
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

LAWSON_LDDC = ["A sitting long", "B sitting short", "C standing/strolling",
               "D walking", "E business walking"]
labels = result.legend or LAWSON_LDDC       # the classes of the criteria that you ran
PLATFORM = ["#384672", "#38aead", "#69ad38", "#dee269", "#f00000"]  # platform palette, 5 classes
COLORS = PLATFORM if len(labels) == 5 else list(plt.get_cmap("RdYlGn_r", len(labels))(range(len(labels))))

cmap = mcolors.ListedColormap(COLORS)
cmap.set_bad(alpha=0.0)
norm = mcolors.BoundaryNorm(np.arange(-0.5, len(COLORS)), cmap.N)   # one bin per class index

ax.imshow(np.ma.masked_invalid(result.physical_grid()), cmap=cmap, norm=norm,
          origin="lower", interpolation="nearest")
ax.legend(handles=[mpatches.Patch(color=c, label=l) for c, l in zip(COLORS, labels)],
          loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
```

Same discipline in the numbers: **don't average class indices.** The mean of A and E is not
C. Report the area share per class, or the mode. Mask *before* comparing — `NaN == 4` is
`False`, not `NaN`, so `np.nanmean(grid == 4)` quietly counts every outside-the-polygon cell
in the denominator and under-reports the hotspot share:

```python
grid = result.physical_grid()
valid = grid[~np.isnan(grid)]
class_e_share = (valid == 4).mean()          # NOT np.nanmean(grid == 4)
```

Draw wind comfort as discrete classes: one colour per class, a stepped legend, never a
gradient. Wind speed is continuous and gets a gradient.

---

## 6. Rainbow colormaps, and the wrong kind of scale

**The failure:** `jet` / `rainbow` are not perceptually uniform — lightness rises and falls
across the ramp, so the eye sees sharp bands at the yellow and cyan turns that exist nowhere
in the data, and gentle real gradients disappear in the flat stretches. Measured on the
256-step ramp: `jet`'s step-to-step lightness variation is **13x** viridis's, and its
lightness is non-monotonic (it goes down, then up). It also collapses to mush in greyscale
and for red-green colour blindness.

**The rule:**

- **Sequential** (`viridis`, `magma`, `plasma`) for one-directional quantities — SVF, sun
  hours, solar radiation, wind speed, daylight.
- **Diverging** (`RdBu_r`, `coolwarm`) *only* where zero is a meaningful midpoint: scenario
  deltas, before/after, deviation from a comfort threshold. Centre it, or the neutral colour
  lands on a non-zero value and half the map lies about its sign.

```python
delta = proposed.physical_grid() - baseline.physical_grid()
lim = float(np.nanmax(np.abs(delta)))                      # symmetric about zero
plt.imshow(delta, cmap="RdBu_r", origin="lower",
           norm=mcolors.TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim))
```

Do **not** reuse `min_legend`/`max_legend` here: they are the range of absolute values, and deltas
go negative.

**A palette trick:** interpolate the base palette more finely for the mesh than for the
legend. The surface reads smooth; the legend stays countable. When a user filters by value
range it sets **alpha 0** on the excluded cells rather than recolouring them, so the
remaining colours keep their meaning.

---

## 7. North-down, and hand-derived extents

**The failure:** the render is vertically mirrored, or the overlay sits a tile off the real
streets. Both look plausible until someone who knows the site sees it.

Infrared grids are **row 0 = south, column 0 = west**. Different consumers disagree:

| Target | What to do |
|---|---|
| matplotlib | `origin="lower"` |
| Plotly | unflipped |
| folium / leaflet `ImageOverlay` | `np.flipud(grid)` — its first row is drawn at the **north** edge |
| GeoTIFF | `np.flipud(grid)` — GeoTIFF row 0 is north |
| Canvas, deck.gl `BitmapLayer`, MapLibre image source | flip the rows of `areaGridValuesF32(result)`; image row 0 is north |

For placement, use `result.bounds` (`[west, south, east, north]`, the same in TypeScript) — the SDK-computed extent
of the *actual* merged grid. Reconstructing the extent from tile counts × step size drifts by
up to a tile, because the merged grid is padded past the polygon when the sides aren't an
integer multiple of the tile step. And **don't crop** the image to the polygon: `bounds`
describes the full grid, so the image must match it cell-for-cell — the `NaN` cells outside
the polygon give the overlay its true shape for free (§2).

---
## 8. The shortcut: let the SDK draw it

If you need only a correct PNG, the SDK draws it on your machine with the official colours
(from the public colour registry; no job, no key):

```python
rows = result.to_list()[::-1]                              # NaN -> None; row 0 is south, the PNG top is north
png = client.weather.gen_grid_image(grid=rows, analysis_type=result.analysis_type)
open("result.png", "wb").write(png)
```

Pass `criteria` or `subtype` for pedestrian wind comfort and thermal comfort so the class
mapping matches section 5. One pixel for each cell, up to 960 px on the long side. No-data
cells are transparent. TypeScript: `renderGridPng(rows, { analysisType })`.

---

## 9. Drawing a terrain-draped grid in 3D

A ground-grid run with `ground_geometry` is draped onto the terrain server-side, but the
raster comes back with **no z**. To draw it on the relief, re-sample your own terrain at
each sensor position: grid cell `(j, i)` is the sensor at `(corner_x + i, corner_y + j)`
metres in the frame you submitted
([`../geospatial-crs.md#the-frame-rule`](../geospatial-crs.md#the-frame-rule)); draw the
cell ±0.5 m around it, lifted slightly above the surface.

```python
import numpy as np
from matplotlib.tri import LinearTriInterpolator, Triangulation

def drape_z(terrain_mesh, grid_shape, corner=(0.0, 0.0)):
    """Terrain height under every sensor of a merged grid; NaN where no triangle covers it.
    `corner` = the model point you submitted as (0, 0)."""
    v = np.asarray(terrain_mesh["coordinates"], dtype=float).reshape(-1, 3)
    f = np.asarray(terrain_mesh["indices"], dtype=int).reshape(-1, 3)
    ny, nx = grid_shape
    xs = corner[0] + np.arange(nx)          # column 0 = west
    ys = corner[1] + np.arange(ny)          # row 0 = south
    gx, gy = np.meshgrid(xs, ys)
    z = LinearTriInterpolator(Triangulation(v[:, 0], v[:, 1], f), v[:, 2])(gx, gy)
    return z.filled(np.nan)                 # (ny, nx)

z = drape_z(terrain_mesh, result.physical_grid().shape)
```

`matplotlib.tri` interpolates on the triangles you pass (no re-triangulation); a vectorised
numpy barycentric test is the dependency-free equivalent. Bucket by triangle for large
inputs. Footprint cells come back as `0.0` on this path — mask them with your own
footprints (§2 covers masked cells).

---

## Checklist before you ship a render

- [ ] Colour bounds come from a fixed per-analysis domain or a shared range for runs that you compare
- [ ] Masked cells are `NaN` and transparent — never `0`
- [ ] Roofs and facades on one scale; any exception is labelled on the image
- [ ] `emit_cell_tris=True` only for the building or export that needs exact cells
- [ ] Categorical analyses get a discrete colormap + a class legend, and no averaged indices
- [ ] Perceptually uniform colormap; diverging only where zero is a real midpoint, and centred
- [ ] North is up, and the overlay uses `result.bounds` uncropped
- [ ] The legend states the unit and says whether the end bins are open ("> 15 m/s")

## See also

- [`../surface-results-integration.md`](../surface-results-integration.md) — the columns contract, render buffers, the masking shader
- [`../interpretation/grid-conventions.md`](../interpretation/grid-conventions.md) — grid layout, scenario diffs, GeoTIFF export
- [`../analyses/09-facade-terrain.md`](../analyses/09-facade-terrain.md) — facade/roof request fields and response shape
- Cookbook notebooks: [../../../../../../cookbook/](../../../../../../cookbook/README.md)
