# Coordinates: frames, CRS and reprojection

The SDK takes **WGS84 longitude/latitude in degrees, `[lon, lat]`** (GeoJSON, RFC 7946).
It does not reproject and it does not check plausibility. Coordinates in another CRS, or in
`[lat, lon]` order, run without an error on the wrong part of the planet.

Use this page for real GIS or CAD data (Shapefile, GeoPackage, GeoTIFF, Rhino, IFC). Guide chapter "Coordinates": <https://infrared.city/docs/sdk/1.0/sdk.md>.

## The frames

| Frame | Units and origin | What is in it |
|---|---|---|
| WGS84 lon/lat | degrees, `[lon, lat]` | the run `polygon`; `vegetation` and `ground_materials` features |
| Run frame | metres; `(0, 0)` = south-west corner of the polygon's bounding box; x east, y north, z up | `buildings`, `context_geometry`, `ground_geometry` |
| Surface UV | per surface `origin`, `u_axis`, `v_axis` | facade and roof results only |

- **Trees and ground materials stay in lon/lat** while the buildings next to them are in metres.
  Metre values in `vegetation` put every tree near (0, 0) degrees, in the sea off West Africa.
- `run_area*` moves the run-frame geometry into each tile for you. You never write that step.
- Own sensor points and interior geometry use their own local frame. See
  [python/surfaces-and-sensors.md](python/surfaces-and-sensors.md) and [python/interior.md](python/interior.md).

### The SDK projection

The run frame is an equirectangular projection on a sphere with R = 6,371,000 m. The cosine
is taken at the south-west corner. Use the same formula, and your meshes line up with the
result grid:

```python
import math

R = 6_371_000.0                                     # sphere of the SDK local frame

def to_local(lon: float, lat: float, polygon: dict) -> tuple[float, float]:
    """lon/lat -> metres in the run frame (origin = SW corner of the polygon bbox)."""
    ring = polygon["coordinates"][0]
    lon0, lat0 = min(p[0] for p in ring), min(p[1] for p in ring)
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return x, y

def to_lonlat(x: float, y: float, polygon: dict) -> tuple[float, float]:
    """The inverse: run-frame metres -> lon/lat."""
    ring = polygon["coordinates"][0]
    lon0, lat0 = min(p[0] for p in ring), min(p[1] for p in ring)
    return (lon0 + math.degrees(x / (R * math.cos(math.radians(lat0)))),
            lat0 + math.degrees(y / R))
```

### The frame rule

The SDK reads a plain buildings map as metres from the polygon's south-west bbox corner.
It does not move your geometry. Results come back in the same frame. So:

- **Pick the corner, then express every vertex relative to it.** The normal choice is the
  model's min (x, y). Build the polygon there (Recipe D) and submit `vertex - corner`.
- **Pad only to the north and east.** A pad to the south or west moves the whole scene by
  the pad. The result still looks plausible.
- Grid cell `(row j, column i)` is the sensor at `(i, j)` metres from the corner (± 0.5 m).
- The `AreaBuildings` object from `client.buildings.get_area(...)` keeps its own frame.
  Pass the object itself, not `.buildings`: the SDK then places it correctly, also for a
  smaller run polygon.
- **Check before you measure.** Draw the result over your footprints. A constant offset does
  not show in the numbers.

### Negative coordinates are correct

Buildings south or west of the corner have negative x or y. Public buildings come from a
margin around the polygon, so many are negative. They cast shade into your site.
Do not filter them out: the result gets brighter and still looks plausible.

### Height and terrain

`z` is metres up and relative. The SDK uses no vertical datum. Only the agreement between
your terrain and your buildings counts. Public buildings carry a height, not a ground elevation.

**Always set `terrain_alignment` yourself.** Do not rely on the default.

| Analysis | Values | Use |
|---|---|---|
| SVF, solar radiation, direct sun hours, daylight availability, UTCI, TCS | `"as-is"`, `"auto-align"`, `"assume-aligned"` | `"auto-align"`: buildings at z = 0 on a real terrain. `"as-is"`: your model already sits on its terrain. `"assume-aligned"`: a mismatch must fail (422). |
| Wind speed, pedestrian wind comfort | `"to-ground"`, `"as-is"` | `"to-ground"` when the scene sits on terrain. Wind takes no `ground_geometry`, and it reads the mesh z as the height above ground. |

No mode moves the sensor grid. Without `ground_geometry` the ground is a flat plane at z = 0.
Details: [analyses/11-terrain-and-context.md](analyses/11-terrain-and-context.md).

### Surface UV frames (results)

Each facade or roof surface has `origin`, `u_axis` and `v_axis` in metres. The outward normal
is `u_axis x v_axis`. With x east and y north, the compass bearing of a facade is
`degrees(atan2(n[0], n[1])) % 360`. Cell centres, textures and `cell_tris`:
[surface-results-integration.md](surface-results-integration.md).

## "My geometry is in the wrong place"

Nothing below raises an error. Work down the table.

| Symptom | Likely cause |
|---|---|
| Result over water, farmland or another country | Polygon not in WGS84, or `[lat, lon]`. Run the preflight below. |
| Everything mirrored about the diagonal | `[lat, lon]` swap, or `pyproj` without `always_xy=True` |
| Trees or ground materials far from the site | Metre values given where lon/lat is expected |
| Grid and surfaces a constant few metres off the buildings | Polygon corner is not your `(0, 0)`. See the frame rule. |
| Site too bright; far blocks cast no shade | Negative-coordinate buildings filtered out, or an occluder more than 128 m past the tile |
| Buildings float above or sink into terrain | Terrain in absolute heights, buildings at z = 0, no `terrain_alignment` |
| Overlay squashed toward the south-west | Placed with the polygon bounds, not `result.bounds` |
| Exported GeoTIFF upside down | Row 0 of the grid is south; row 0 of a GeoTIFF is north: `np.flipud` |

## What the SDK checks

`validate_polygon` (in `infrared_sdk.tiling.validation`, raises `PolygonValidationError`)
checks only the shape: a GeoJSON `Polygon`, one ring, closed, at least 4 positions,
`-180 <= lon <= 180`, `-90 <= lat <= 90`, no self-intersection. It turns a clockwise ring
counter-clockwise.

It does **not** check:

- **The CRS.** A UTM easting of 400,000 is refused, but small projected values that fall
  inside the degree range are accepted.
- **Plausibility.** `[0, 0]` is a valid polygon.
- **The antimeridian.** A ring from 179 to -179 gives wrong tiles.
- **Polar sites.** Above about 70 degrees latitude the local projection distorts. The SDK is
  made for city-scale polygons below about 50 km.

## Getting to WGS84

### A: GeoPandas or shapely, any projected CRS

```python
import geopandas as gpd
import shapely
from shapely.geometry import mapping

gdf = gpd.read_file("aoi.gpkg", layer="study_area").to_crs("EPSG:4326")   # the step people forget
geom = shapely.force_2d(gdf.geometry.iloc[0])
if geom.geom_type == "MultiPolygon":                # the SDK takes one Polygon
    geom = max(geom.geoms, key=lambda p: p.area)
polygon = mapping(geom)                             # [lon, lat], closed ring
```

### B: a bounding box, or C: GeoTIFF bounds

```python
from pyproj import Transformer
from shapely.geometry import box, mapping

def bbox_polygon(west: float, south: float, east: float, north: float, crs: str) -> dict:
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)   # always_xy keeps (lon, lat)
    w, s = to_wgs.transform(west, south)
    e, n = to_wgs.transform(east, north)
    return mapping(box(w, s, e, n))

polygon = bbox_polygon(500_000, 5_400_000, 500_500, 5_400_500, "EPSG:25832")

# GeoTIFF: with rasterio.open("dsm.tif") as src:
#     polygon = bbox_polygon(*src.bounds, src.crs.to_string())
```

### D: a CAD or BIM model in local metres

The model has a local origin and one known WGS84 anchor for it (site location or survey
point). Make the polygon from the model's own extent, so its south-west corner is the
model's min (x, y). Rotate the model to true north first, if it is not.

```python
import numpy as np

def polygon_around_model(all_xyz, anchor_lon: float, anchor_lat: float,
                         ne_margin_m: float = 10.0) -> tuple[dict, tuple[float, float]]:
    """Polygon whose bbox SW corner is the geometry's min (x, y). Pads north-east only.
    Returns (polygon, corner). Submit every mesh as vertex - corner."""
    v = np.asarray(all_xyz, dtype=float).reshape(-1, 3)
    x0, y0 = v[:, 0].min(), v[:, 1].min()                    # SW corner, no pad
    x1, y1 = v[:, 0].max() + ne_margin_m, v[:, 1].max() + ne_margin_m
    k = 6_371_000.0 * np.pi / 180                            # metres per degree on the SDK sphere
    lat0 = anchor_lat + y0 / k                               # cosine at the SW corner, as the SDK does
    ll = lambda x, y: [anchor_lon + x / (k * np.cos(np.radians(lat0))), anchor_lat + y / k]
    ring = [ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1), ll(x0, y0)]
    return {"type": "Polygon", "coordinates": [ring]}, (float(x0), float(y0))

def shift(mesh: dict, corner: tuple[float, float]) -> dict:
    """One {coordinates, indices} mesh, relative to the polygon corner."""
    v = np.asarray(mesh["coordinates"], dtype=float).reshape(-1, 3)
    v[:, 0] -= corner[0]
    v[:, 1] -= corner[1]
    return {**mesh, "coordinates": v.ravel().tolist()}

polygon, corner = polygon_around_model(every_vertex_you_submit, 16.3725, 48.2083)
buildings = {k: shift(m, corner) for k, m in model_buildings.items()}   # same for context, terrain
```

Give `polygon_around_model` every vertex that you submit (buildings, terrain, occluders).
Keep `corner`: it maps the results back into your model.

## Preflight before a run

```python
from shapely.geometry import shape
from infrared_sdk.tiling.validation import validate_polygon

def preflight(polygon: dict) -> None:
    validate_polygon(polygon)                       # shape errors raise here
    geom = shape(polygon)
    cx, cy = geom.centroid.x, geom.centroid.y
    if abs(cx) < 1 and abs(cy) < 1:
        raise ValueError("centroid near (0, 0): wrong CRS or lat/lon swap")
    minx, miny, maxx, maxy = geom.bounds
    if maxx - minx > 0.5 or maxy - miny > 0.5:
        raise ValueError("polygon spans more than 0.5 degrees: not city scale")
    if abs(cy) > 70:
        raise ValueError("above 70 degrees latitude: the local frame distorts")
```

For a known site, also check that the centroid is in the expected city.

## Export a result as GeoTIFF

```python
import numpy as np
import rasterio
from rasterio.transform import from_bounds

grid = result.physical_grid().astype("float32")    # real values, NaN = no value
west, south, east, north = result.bounds            # bounds of the GRID, not of the polygon
h, w = grid.shape
with rasterio.open("result.tif", "w", driver="GTiff", height=h, width=w, count=1,
                   dtype="float32", crs="EPSG:4326", nodata=np.nan,
                   transform=from_bounds(west, south, east, north, w, h)) as dst:
    dst.write(np.flipud(grid), 1)                   # grid row 0 = south; GeoTIFF row 0 = north
```

For a metric raster, reproject the file (`gdalwarp -t_srs EPSG:326xx`).

## Pitfalls

- A CRS other than WGS84 runs in the wrong country. Always `to_crs("EPSG:4326")` first.
- `pyproj` without `always_xy=True` gives `(lat, lon)` for EPSG:4326.
- MultiPolygon: the SDK takes one Polygon. Dissolve it or take the largest part.
- `POLYGON Z`: drop the z with `shapely.force_2d`.
- Buffers or snapping in metres: do them in the UTM zone of the site, then go back to WGS84.
  Never put UTM values into an SDK call.
- Polygons over the antimeridian or above 70 degrees latitude: not supported.
- More than 100 non-empty tiles: refused until you pass `max_tiles_override`. Check the
  price first ([throughput-and-limits.md](throughput-and-limits.md)).

## See also

- [byo-inputs.md](byo-inputs.md): your buildings, trees and ground as SDK inputs.
- [interpretation/grid-conventions.md](interpretation/grid-conventions.md): grid layout, row 0 = south.
- [analyses/09-facade-terrain.md](analyses/09-facade-terrain.md): facade and roof requests.
