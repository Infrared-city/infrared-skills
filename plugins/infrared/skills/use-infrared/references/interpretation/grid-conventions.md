# Grid conventions (shared across all analyses)

Every analysis returns the same `AreaResult` shape. These conventions hold for wind, solar, and thermal alike — once you know them, every grid reads the same way.

## Quick lookup — what does each cell mean?

| Analysis | Cell unit | Typical range | Meaning |
|---|---|---|---|
| `wind-speed` | m/s | 0–30 | Steady-state wind magnitude near pedestrian level for one (speed, direction) inflow |
| `pedestrian-wind-comfort` | comfort class (int) | 0–4 wire format (Lawson LDDC: A=0 best … E=4 unsafe); NEN-8100 safety / criteria with an extra unsafe class may extend the range. Visualization layers (e.g. composite image gen) often shift to 1-based. | Categorical class per chosen criterion |
| `daylight-availability` | hours | 0 – period length | Cumulative hours of usable daylight per cell over the `TimePeriod` |
| `direct-sun-hours` | hours | 0 – period length | Cumulative un-occluded sun hours over the `TimePeriod` |
| `sky-view-factors` | fraction | 0–1 | Hemisphere visible from the cell (1 = fully open, 0 = obstructed) |
| `solar-radiation` | kWh/m² | 0–~hundreds | Cumulative shortwave irradiance per pixel over the `TimePeriod` |
| `thermal-comfort-index` (UTCI) | °C | -40 to 50 | Felt temperature combining air, MRT, humidity, wind |
| `thermal-comfort-statistics` (TCS) | hours (subtype-dependent) | 0 – period length | Hours per cell in the chosen `TcsSubtype` band |

For per-analysis class breaks (e.g. UTCI stress thresholds, PWC class semantics), see `wind-results.md`, `solar-results.md`, `thermal-results.md`.

## The grid

`result.merged_grid` is a 2-D `numpy.ndarray`.

| Property | Value |
|---|---|
| Cell pitch | **1 m × 1 m** (fixed; do not assume otherwise) |
| Single-tile coverage | **512 m × 512 m** (auto-tiled if polygon larger) |
| Outside polygon | `NaN` (never zero — distinguishes "no data" from "cold/dark/calm") |
| Row 0 | South edge of polygon bbox |
| Column 0 | West edge of polygon bbox |
| Orientation | Plot with `origin="lower"` (matplotlib) or unflipped (Plotly) for north-up |

If you flip rows or treat NaN as zero, summary statistics will be wrong. Always mask with `np.isnan`:

```python
import numpy as np
valid = result.merged_grid[~np.isnan(result.merged_grid)]
mean_value = valid.mean()
area_share_above_threshold = (valid > THRESHOLD).mean()
```

## Plot bounds — always use legend metadata

Distributions are heavy-tailed (especially solar/daylight). Use the result's legend metadata, not the data range, for colour bounds:

```python
fig = px.imshow(
    result.merged_grid,
    zmin=result.min_legend,   # NOT result.merged_grid.min()
    zmax=result.max_legend,
    origin="lower",
)
```

`min_legend` / `max_legend` are calibrated per analysis type so heatmaps from different runs of the same analysis stay comparable.

## Comparing scenarios (baseline vs proposed)

The standard architectural workflow — "what does my redesign change?" — uses **same-shape** grids from two runs:

```python
baseline = client.run_area_and_wait(payload, polygon, buildings=existing_buildings, ...)
proposed = client.run_area_and_wait(payload, polygon, buildings=redesign_buildings, ...)

delta = proposed.merged_grid - baseline.merged_grid    # cell-by-cell change
improved_share = (delta < 0).sum() / np.isfinite(delta).sum()    # for "lower is better"
```

To make scenarios comparable:

- **Pin the polygon** — same `polygon` dict for both runs. Different polygons = different bbox = different grid shape.
- **Pin the weather** — same `TimePeriod` and same EPW `identifier`. Mixing weather files corrupts comfort/UTCI deltas.
- **Pin the analysis parameters** — same wind speed/direction, same TCS subtype, same PWC criterion.
- Vary only the layer the redesign touches (buildings, vegetation, or ground materials).

Plot deltas with a diverging colormap (`RdBu`, `coolwarm`) centred at zero. Don't reuse `min_legend`/`max_legend` for delta plots — those are absolute-scale bounds.

## Exporting to GeoTIFF

For GIS handoff (QGIS, ArcGIS, Earth Engine), write `merged_grid` to a georeferenced raster. The bbox of the input polygon plus the 1 m cell pitch gives you the affine transform:

```python
import numpy as np
import rasterio
from rasterio.transform import from_bounds

grid = result.merged_grid
lons = [c[0] for c in result.polygon["coordinates"][0]]
lats = [c[1] for c in result.polygon["coordinates"][0]]
west, east = min(lons), max(lons)
south, north = min(lats), max(lats)
height, width = grid.shape

transform = from_bounds(west, south, east, north, width, height)

with rasterio.open(
    "result.tif", "w",
    driver="GTiff", height=height, width=width, count=1,
    dtype=grid.dtype, crs="EPSG:4326", transform=transform,
    nodata=np.nan,
) as dst:
    dst.write(np.flipud(grid), 1)   # GeoTIFF expects row 0 = north
```

Note the `np.flipud` — Infrared grids are row 0 = south, GeoTIFF is row 0 = north. Skip this and your raster will appear vertically mirrored in QGIS.

For a metric raster, reproject the polygon to a local projected CRS (UTM zone, ETRS89/LAEA) and use `from_bounds` in metres instead.

## See also

- `wind-results.md`, `solar-results.md`, `thermal-results.md` — per-analysis units and class breaks
- `../05-area-api.md` — `AreaResult` field reference
