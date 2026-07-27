# Making results look good on geometry

Read this before your first render. Every trap below produces a picture that *looks* like a
result — plausible enough to screenshot, wrong enough to mislead — and the usual reaction is
"the model is bad" rather than "the render is bad". None of them are model problems.

The Infrared platform (ForgeKit) renders exactly the same API payloads. What follows is what
it does differently, verified against SDK 0.5.1 and ForgeKit's own
`@infrared/analysis-colors` package.

---

## 1. Auto-scaling to the grid's own min/max

**The failure:** you normalise each render to `grid.min()` / `grid.max()`. Two runs of the
same analysis now use two different scales, so the same physical value is a different colour
in each — a baseline and a redesign become impossible to compare, and a flat, uneventful
grid gets stretched until sensor noise looks like structure. This is the single most common
cause of an ugly or misleading image.

**The rule:** use the analysis's calibrated bounds, which are on every result.

```python
import matplotlib.pyplot as plt
import numpy as np

vmin = result.min_legend if result.min_legend is not None else float(np.nanmin(result.merged_grid))
vmax = result.max_legend if result.max_legend is not None else float(np.nanmax(result.merged_grid))

plt.imshow(result.merged_grid, origin="lower", cmap="viridis", vmin=vmin, vmax=vmax)
```

The guard matters — the API may omit the legend fields. Never silently fall back to the data
range without saying so, and never fall back *per tile*.

ForgeKit hardcodes the same idea one level up: every analysis type in its registry carries a
fixed `steps: [min, max]` domain that never depends on the run.

| Analysis | ForgeKit domain | Unit |
|---|---|---|
| `wind-speed` | `[0, 15]` (top bin **open**: "> 15") | m/s |
| `sky-view-factors` | `[0, 100]` | % |
| `direct-sun-hours` | `[0, 12]` | hours |
| `daylight-availability` | `[0, 100]` | % |
| `solar-radiation` | `[0, 1000]` | kWh/m² |
| `thermal-comfort-index` | `[-40, 46]` | °C |

Note the **open** top bound on wind: values above 15 m/s clamp to the last colour and the
legend says "> 15" rather than pretending 15 is the maximum. Clamp out-of-domain values to
the end colours; don't leave them uncoloured.

**Exception — difference plots.** `min_legend`/`max_legend` are absolute-scale bounds and
deltas go negative. See §6.

---

## 2. Masked cells rendered as zero

**The failure:** you map `None` (surface grids) or `NaN` (area grids) to `0`. Building
footprints and everything outside the polygon are now painted as the *worst* value on the
scale — a solid dark blob that reads as a real result. Summary statistics silently shift the
same way.

**The rule:** masked means *no data*, not *zero*. Map to `NaN` and render transparent.

```python
import numpy as np
import matplotlib.pyplot as plt

cmap = plt.get_cmap("viridis").copy()
cmap.set_bad(alpha=0.0)                      # NaN -> fully transparent

plt.imshow(np.ma.masked_invalid(result.merged_grid), cmap=cmap,
           origin="lower", vmin=vmin, vmax=vmax)
```

For surface results the SDK does the conversion for you — `surface.grid()` returns a
`(nv, nu)` float64 array with masked cells already `NaN` (plain `np.array(surface.values)`
chokes on the `None` entries):

```python
grid = surface.grid()                        # masked cells are NaN, not 0
mean = np.nanmean(grid)                      # np.mean() would be wrong even if you never plot
```

In a GPU pipeline, discard rather than blend — see the premultiplied-mask shader in
[`../surface-results-integration.md`](../surface-results-integration.md), which keeps bilinear
edges clean instead of bleeding masked cells into their neighbours.

---

## 3. Giving facades their own scale

**The failure:** a facade-only run looks washed out on the shared scale, so you rescale it to
the facade percentiles. The facade now shows dramatic contrast that isn't there, and two
surfaces on the same building are no longer comparable.

**The rule:** roofs and facades share **one** scale. Roofs sit high (open sky), facades low
(obstructed) — *that contrast is the reading*, not a defect to normalise away.

```python
norm = plt.Normalize(vmin=result.min_legend, vmax=result.max_legend)   # ONE scale, whole scene

for key, surface in result.surfaces.items():
    draw(surface, norm)                       # surface.is_vertical tells you facade vs roof
```

`surface.is_vertical` uses the server's own facade rule (`|n_z| <= 0.5` for
`n = u_axis x v_axis`) — prefer it to eyeballing `v_axis[2]` yourself.

A facade-only rescale is a legitimate *deliberate, labelled* exception ("facades only,
5th–95th percentile"). It is never the default, and never silent.

---

## 4. Picking a rendering route (and paying for the wrong one)

Two routes, one job. They read the same `SurfaceAnalysisResult`.

| | Route 1 — texture the UV grid | Route 2 — mesh from `cell_tris` |
|---|---|---|
| Looks like | smooth gradients, stepped footprint edges | crisp exact boundaries, no stepping |
| Cost | one small texture per surface | several triangles per cell |
| Needs `cell_tris` | no | **yes** |
| Best for | interactive city-scale views | export, print, selected elements |

**The failure:** `emit_cell_tris` **defaults to `False`** on any `analysis_surfaces` request
in SDK 0.5.1 — Route 2 code written against an older assumption gets `None` and either
crashes or renders an empty mesh. Per-cell geometry measured **93.7% of a facade payload**
(12.0 MB → 0.76 MB, 15.9x), which is why it is off by default. `values` and every aggregate
are identical either way, so nothing analytical is lost — only the per-cell outlines used for
*drawing*. (`cell_area` may go with them; treat it as optional too.)

```python
from infrared_sdk.analyses.types import AnalysesName, SvfModelRequest

# Route 1 / analysis only — the default, ~15x smaller download.
payload = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                          analysis_surfaces="all", surface_grid_size=1.0)

# Route 2 — you must ask for the geometry back.
payload = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                          analysis_surfaces="all", surface_grid_size=1.0,
                          emit_cell_tris=True)
```

Branch on presence rather than assuming — `cell_tris` is also absent on the centre-test /
BYO-sensor path:

```python
if surface.has_cell_geometry:
    for value, (a, b, c) in surface.triangles():   # exact clipped cells
        emit_triangle(a, b, c, color=cmap(norm(value)))
else:
    draw_texture(surface.grid())                   # Route 1 fallback
```

`triangles()` raises `ValueError` when the geometry is absent instead of yielding nothing —
an empty mesh is a silent failure, an exception is not. It also skips masked cells for you.

`emit_cell_tris` participates in `config_hash()`, so a resume can't merge tris-present tiles
from one run with tris-absent tiles from another.

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
COLORS = ["#384672", "#38aead", "#69ad38", "#dee269", "#f00000"]   # ForgeKit wind-comfort palette

cmap = mcolors.ListedColormap(COLORS)
cmap.set_bad(alpha=0.0)
norm = mcolors.BoundaryNorm(np.arange(-0.5, len(COLORS)), cmap.N)   # one bin per class index

ax.imshow(np.ma.masked_invalid(result.merged_grid), cmap=cmap, norm=norm,
          origin="lower", interpolation="nearest")
ax.legend(handles=[mpatches.Patch(color=c, label=l) for c, l in zip(COLORS, LAWSON_LDDC)],
          loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
```

Same discipline in the numbers: **don't average class indices.** The mean of A and E is not
C. Report the area share per class, or the mode. Mask *before* comparing — `NaN == 4` is
`False`, not `NaN`, so `np.nanmean(grid == 4)` quietly counts every outside-the-polygon cell
in the denominator and under-reports the hotspot share:

```python
valid = result.merged_grid[~np.isnan(result.merged_grid)]
class_e_share = (valid == 4).mean()          # NOT np.nanmean(grid == 4)
```

ForgeKit's `wind-comfort` entry is `colorInterpolation: "binned"` with one colour per class
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
delta = proposed.merged_grid - baseline.merged_grid
lim = float(np.nanmax(np.abs(delta)))                      # symmetric about zero
plt.imshow(delta, cmap="RdBu_r", origin="lower",
           norm=mcolors.TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim))
```

Do **not** reuse `min_legend`/`max_legend` here — those are absolute-scale bounds and deltas
go negative.

**ForgeKit's palette trick:** it extends each base palette by interpolation, with a *finer*
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

If you just need a correct PNG and don't need interactivity, skip all of the above — the
weather service renders with Infrared's canonical palette and legend:

```python
from infrared_sdk.tiling.merger import grid_to_list

png = client.weather.gen_grid_image(
    grid=grid_to_list(result.merged_grid),     # NOT .tolist() — that leaves NaN, which is not JSON
    analysis_type="wind-speed",                # without this you get a generic palette
)
open("result.png", "wb").write(png)
```

`grid_to_list` converts `NaN -> None`. Pass `criteria` / `subtype` for PWC and thermal
comfort so the categorical mapping matches §5. Details:
[`../07-images.md`](../07-images.md).

---

## Checklist before you ship a render

- [ ] Colour bounds come from `min_legend` / `max_legend` (or a fixed per-analysis domain), never per-run min/max
- [ ] Masked cells are `NaN` and transparent — never `0`
- [ ] Roofs and facades on one scale; any exception is labelled on the image
- [ ] `emit_cell_tris=True` if and only if you draw exact cells; branch on `has_cell_geometry`
- [ ] Categorical analyses get a discrete colormap + a class legend, and no averaged indices
- [ ] Perceptually uniform colormap; diverging only where zero is a real midpoint, and centred
- [ ] North is up, and the overlay uses `result.bounds` uncropped
- [ ] The legend states the unit and says whether the end bins are open ("> 15 m/s")

## See also

- [`../surface-results-integration.md`](../surface-results-integration.md) — the UV-grid contract, both routes in depth, the masking shader
- [`../interpretation/grid-conventions.md`](../interpretation/grid-conventions.md) — grid layout, scenario diffs, GeoTIFF export
- [`../07-images.md`](../07-images.md) — server-rendered PNGs
- [`../analyses/09-facade-terrain.md`](../analyses/09-facade-terrain.md) — facade/roof request fields and response shape
- Notebooks: `12_surface_results_rendering.ipynb` (both routes, whole-tile shared scale), `10_real_world_map_overlay.ipynb` (folium overlay)
