# Grid conventions (the one home for helper and grid rules)

Every area analysis returns an `AreaResult`. The same rules hold for wind, solar and thermal.

## Always read through the helper

The server stores each result in the smallest accurate type. The raw array keeps that type.

| Stored type | Analyses |
|---|---|
| f16 (half float) | solar radiation, sky view factor, TCS, wind speed, UTCI |
| f32 | direct sun hours, daylight availability, PWC class codes |
| int16 (scaled) | possible for scaled results: value = stored / `value_divisor` |
| f64 | a JSON result, or a run that mixes types |

Do not read `merged_grid` for values. UTCI arrives as f16 and the helper handles it. An int16 grid read
without the divisor is 10 times too large. In TypeScript an f16 grid is a `Uint16Array` of
half-float bits: a UTCI of 23.4 reads as 19930.

| | Python | TypeScript |
|---|---|---|
| Ground grid | `result.physical_grid()` (float64, NaN = no value; `dtype=np.float32` halves memory) | `areaGridValuesF32(result)` (Float32Array) |
| Facade or roof cells | `result.columns.physical_values()` | `surfaceValuesF32(columns)` |
| Render buffers | `result.columns.render_buffers()` | `surfaceRenderBuffers(columns)` |
| Legend range | `result.min_legend`, `result.max_legend` | `result.minLegend`, `result.maxLegend` |

Class results (pedestrian wind comfort) have no numeric legend range: `min_legend` is `None` and
`result.legend` holds the class names.

## What each cell means

| Analysis | Unit | Range | Meaning |
|---|---|---|---|
| `wind-speed` | m/s | 0 to 30 | Speed at pedestrian level for one inflow |
| `pedestrian-wind-comfort` | class code | 0 to 4 for Lawson LDDC (A best) | Class of the chosen criterion |
| `daylight-availability` | % of window | 0 to 100 | Share of the window with enough daylight |
| `direct-sun-hours` | hours | 0 to hours in the window | Sum of sun hours. Keep the window daylight-only |
| `sky-view-factors` | % | 0 to 100 | Visible sky |
| `solar-radiation` | kWh/m2 | 0 to hundreds | Energy over the window |
| `thermal-comfort-index` | degrees C | -40 to 50 | Felt temperature over the window |
| `thermal-comfort-statistics` | % of window | 0 to 100 | Share of time in the chosen band |

Per-analysis classes: [wind-results.md](wind-results.md), [solar-results.md](solar-results.md),
[thermal-results.md](thermal-results.md).

## The grid

| Property | Value |
|---|---|
| Cell pitch | 1 m by 1 m |
| One tile | 512 m. A larger area is tiled |
| Outside the polygon, or off the terrain | NaN. This is "no data", not "cold" or "dark" |
| Under a building footprint, on a terrain-draped run | 0.0. A real value. Mask it with your footprints |
| Row 0 | South edge of the grid |
| Column 0 | West edge of the grid |
| North up | `origin="lower"` in matplotlib, unflipped in Plotly |
| Extent | `result.bounds` = (west, south, east, north) of the real grid |

The grid is padded north and east when the polygon is not a multiple of the tile step.
Always place an overlay with `result.bounds`. Do not rebuild the extent from tile counts.
Do not crop the image to the polygon: the NaN cells give the overlay its true shape.

Mask NaN before every statistic:

```python
grid = result.physical_grid()
valid = grid[~np.isnan(grid)]
mean = valid.mean()
share_above = (valid > THRESHOLD).mean()      # NOT np.nanmean(grid > THRESHOLD)
```

## Plot bounds: fix them for each analysis

`result.min_legend` and `result.max_legend` are the exact range of this one result. Two runs get
two scales, so they cannot be compared. For comparison, use one fixed range for each analysis, or
a pooled range of all results to compare:

```python
from infrared_sdk import legend_range, shared_legend_range

vmin, vmax = shared_legend_range([baseline, proposed])      # one scale for both
vmin, vmax = legend_range(result, mode="trimmed")           # 2nd to 98th percentile
```

`legend_range` modes: `"exact"`, `"trimmed"`, `"fixed"` (you give the range).
Fixed display domains that work: SVF and daylight availability 0 to 100, direct sun hours 0 to the
daylight hours of your window, solar 0 to 1000 kWh/m2, wind 0 to 15 m/s (open top bin),
UTCI -40 to 46 C. More: [../recipes/rendering-results-well.md](../recipes/rendering-results-well.md).

## Compare scenarios

```python
baseline = client.run_area_and_wait(request, polygon, buildings=existing)
proposed = client.run_area_and_wait(request, polygon, buildings=redesign)
delta = proposed.physical_grid() - baseline.physical_grid()       # cell by cell
improved = (delta < 0).sum() / np.isfinite(delta).sum()           # when lower is better
```

- Same polygon, same weather file and `TimePeriod`, same analysis parameters.
- Change only the layer that the redesign touches.
- Plot the delta with a diverging map centred on zero. Do not use the legend range for a delta.

## Export to GeoTIFF

Row 0 of a grid is south. A GeoTIFF has row 0 at the north. Flip the rows.

```python
import rasterio
from rasterio.transform import from_bounds

west, south, east, north = result.bounds
grid = result.physical_grid().astype("float32")
height, width = grid.shape
with rasterio.open("result.tif", "w", driver="GTiff", height=height, width=width, count=1,
                   dtype="float32", crs="EPSG:4326", nodata=float("nan"),
                   transform=from_bounds(west, south, east, north, width, height)) as dst:
    dst.write(np.flipud(grid), 1)
```

For a metric raster, re-project the bounds to a local CRS (UTM, ETRS89 LAEA) and use metres.
`rasterio` is not an SDK dependency.
