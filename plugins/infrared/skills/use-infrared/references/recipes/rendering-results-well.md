# Making results look good on geometry

Read this before your first render. Every trap below produces a picture that *looks* like a
result: plausible enough to screenshot, wrong enough to mislead. None of them are model problems.

The Infrared platform renders the same results. This page shows what it does differently.
Helper and grid rules: [../interpretation/grid-conventions.md](../interpretation/grid-conventions.md).
---
## 1. Auto-scaling to the grid's own min/max

**The failure:** each render is normalised to its own min and max. Two runs of the same analysis
get two scales, so the same value gets two colours. A baseline and a redesign cannot be compared,
and a flat grid is stretched until noise looks like structure.

**The rule:** the scale is set by the *analysis*, not by the run. Choose one of:

- a fixed domain for each analysis (table below), held constant for all runs that you compare;
- one pooled range over all results that you compare: `shared_legend_range([a, b])`;
- for a single result, `result.min_legend` and `result.max_legend`. They hold the exact range of
  that result (also on area results), so use them only when you do not compare runs.

```python
import matplotlib.pyplot as plt
from infrared_sdk import shared_legend_range

DOMAIN = {                       # fixed per analysis, never per run
    "sky-view-factors": (0, 100),          # %
    "daylight-availability": (0, 100),     # %
    "direct-sun-hours": (0, 12),           # h, for a 9 to 17 window: the ceiling is the sample count of YOUR window
    "solar-radiation": (0, 1000),          # kWh/m2
    "wind-speed": (0, 15),                 # m/s, top bin OPEN
    "thermal-comfort-index": (-40, 46),    # degC
}
vmin, vmax = DOMAIN[result.analysis_type]
plt.imshow(result.physical_grid(), origin="lower", cmap="viridis", vmin=vmin, vmax=vmax)
# For two scenarios: vmin, vmax = shared_legend_range([baseline, proposed])
```

The platform fixes the same idea in its registry: every analysis has a `[min, max]` domain.
Wind has an **open** top bound: values above 15 m/s take the last colour and the legend says "> 15".
Clamp out-of-domain values to the end colours. Never leave them uncoloured.

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
an elevation that a neighbour blocks. That is the answer. On one June run over 300 buildings, 555 of
1,730 facades (32 %) were exact zeros. The scene mean was 3.62 h with them and 5.33 h without.
Decide which you report, and say so:

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

**The failure:** `pedestrian-wind-comfort` returns comfort **class indices** (Lawson LDDC:
`0`=A … `4`=E), not a measurement. Run a continuous ramp over them and you get colours
*between* classes, which mean nothing — class B blends into class C, and a viewer reads a
smooth gradient where the standard defines five hard bins.

**The rule:** discrete colormap, discrete legend, `interpolation="nearest"`.

```python
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches

LAWSON_LDDC = ["A sitting long", "B sitting short", "C standing/strolling",
               "D walking", "E business walking"]
COLORS = ["#384672", "#38aead", "#69ad38", "#dee269", "#f00000"]   # platform wind-comfort palette

cmap = mcolors.ListedColormap(COLORS)
cmap.set_bad(alpha=0.0)
norm = mcolors.BoundaryNorm(np.arange(-0.5, len(COLORS)), cmap.N)   # one bin per class index

ax.imshow(np.ma.masked_invalid(result.physical_grid()), cmap=cmap, norm=norm,
          origin="lower", interpolation="nearest")
ax.legend(handles=[mpatches.Patch(color=c, label=l) for c, l in zip(COLORS, LAWSON_LDDC)],
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

The platform `wind-comfort` entry is `colorInterpolation: "binned"` with one colour per class
and `legendType: "equal_ranges"` — a stepped ramp, never a gradient. `wind-speed` is the
only common config it renders `linear`.

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

**The platform palette trick:** it extends each base palette by interpolation, with a *finer*
factor for the mesh than for the legend (`resultSubdivisionFactor` vs
`legendSubdivisionFactor`) — UTCI's 7 base colours become 21 mesh colours but only 14 legend
swatches. The surface reads smooth; the legend stays countable. When a user filters by value
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

For placement, use `result.bounds` — the SDK-computed `(min_lng, min_lat, max_lng, max_lat)`
of the *actual* merged grid. Reconstructing the extent from tile counts × step size drifts by
up to a tile, because the merged grid is padded past the polygon when the sides aren't an
integer multiple of the tile step. And **don't crop** the image to the polygon: `bounds`
describes the full grid, so the image must match it cell-for-cell — the `NaN` cells outside
the polygon give the overlay its true shape for free (§2).

---
## 8. The shortcut: let the server draw it

If you need only a correct PNG, the weather service draws it with the canonical palette:

```python
grid = result.physical_grid()
cells = np.where(np.isnan(grid), None, grid).tolist()      # NaN is not JSON: send null
png = client.weather.gen_grid_image(grid=cells, analysis_type="sky-view-factors")
open("result.png", "wb").write(png)
```

Pass `criteria` or `subtype` for pedestrian wind comfort and thermal comfort so the class
mapping matches section 5. The TypeScript SDK has `renderGridPng(grid, { analysisType })`:
one pixel for each cell, up to 960 px on the long side.
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
