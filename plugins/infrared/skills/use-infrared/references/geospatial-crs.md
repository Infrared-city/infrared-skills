# Geospatial / CRS recipes

The SDK takes **WGS84 lon/lat in degrees** (GeoJSON RFC 7946). It does not negotiate CRS, does not reproject, does not warn on plausibility — if you hand it coordinates in another CRS or in `[lat, lon]` order, it runs anyway, on the wrong patch of the planet.

This file is the conversion + sanity layer for anyone arriving with real GIS data: shapefiles, GeoPackages, KML, PostGIS, rasterio bbox, Rhino/IFC models, QGIS layers.

## What the SDK accepts and validates

`validate_polygon()` in `infrared_sdk.tiling.validation` (importable; raises `PolygonValidationError`) checks **only**:

1. dict with `type` + `coordinates`
2. `type == "Polygon"` (no MultiPolygon)
3. Single ring (no holes)
4. ≥4 positions in the ring
5. Ring closed (`first == last`)
6. `-180 ≤ lon ≤ 180`, `-90 ≤ lat ≤ 90`
7. No self-intersection (O(n²) edge-pair scan)
8. Auto-normalises CW → CCW (silent)

It does **not** check:

- **CRS** — coordinates outside WGS84 that still happen to fall in `[-180, 180] × [-90, 90]` are accepted silently. UTM eastings of `4_500_000` get rejected by range; UTM eastings of `400_000` will be interpreted as a polygon in West Africa.
- **Plausibility** — `[0, 0]` (Gulf of Guinea, "Null Island") is a valid SDK polygon.
- **Antimeridian crossing** — ring going from `lon=179` to `lon=-179` is accepted and produces garbage tiling (`tiles.py` explicitly: "out of scope for v1").
- **Polar latitudes** — `|lat| > 70°` is accepted but the local-tangent-plane projection (`x = (lon - sw_lon) * 111_320 * cos(radians(lat))`, `transforms.py`) distorts noticeably. SDK is calibrated for **city-scale polygons under ~50 km span**.

## Recipe A — shapely / GeoPandas → SDK polygon

The 90% case. You have a `shapely.Polygon` or a `GeoDataFrame` row in some projected CRS (UTM, ETRS89/LAEA, Web Mercator, BNG, CH1903+, Gauss-Krüger, …) and need WGS84 GeoJSON.

```python
import geopandas as gpd
from shapely.geometry import mapping

# Read whatever format — shapefile, GeoPackage, KML, FlatGeobuf, PostGIS
gdf = gpd.read_file("aoi.gpkg", layer="study_area")

# Reproject to WGS84 — this is the one line most users forget
gdf_4326 = gdf.to_crs("EPSG:4326")

# Single feature, single polygon
geom = gdf_4326.geometry.iloc[0]
if geom.geom_type == "MultiPolygon":
    # SDK takes single Polygon only — pick the largest ring or dissolve upstream
    geom = max(geom.geoms, key=lambda p: p.area)

polygon = mapping(geom)   # GeoJSON dict — RFC 7946 [lon, lat] order
```

`mapping()` produces a dict with closed CCW exterior — SDK-ready. If your source was CW, SDK auto-flips; no action needed.

## Recipe B — bbox / extent → SDK polygon

When the AOI is a rectangle (rasterio dataset bounds, OS map sheet, manually typed corners):

```python
from shapely.geometry import box, mapping
from pyproj import Transformer

# Inputs in source CRS (here: ETRS89 / UTM zone 32N, EPSG:25832)
west, south, east, north = 500_000, 5_400_000, 500_500, 5_400_500
src_crs = "EPSG:25832"

# Project corners to WGS84 (always_xy=True keeps (lon, lat) order)
to_4326 = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
w, s = to_4326.transform(west, south)
e, n = to_4326.transform(east, north)

polygon = mapping(box(w, s, e, n))
```

Use `always_xy=True` on the Transformer. Without it, pyproj returns `(lat, lon)` for some CRSs (EPSG:4326 is one of them) — that bug ends up in production every six months.

## Recipe C — raster (GeoTIFF) bounds → SDK polygon

```python
import rasterio
from shapely.geometry import box, mapping
from pyproj import Transformer

with rasterio.open("dsm.tif") as src:
    src_bounds = src.bounds                  # in dataset CRS
    src_crs = src.crs.to_string()            # e.g. "EPSG:25833"

to_4326 = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
w, s = to_4326.transform(src_bounds.left, src_bounds.bottom)
e, n = to_4326.transform(src_bounds.right, src_bounds.top)

polygon = mapping(box(w, s, e, n))
```

## Recipe D — Rhino / Revit / IFC model → SDK polygon

BIM models live in a local meter frame anchored to some site origin. The model itself is in meters relative to its own origin; geo-anchoring is one extra constant.

```python
# Site anchor in WGS84 (read from your model's "true north / site location" metadata)
ANCHOR_LON, ANCHOR_LAT = 11.5755, 48.1975   # Munich Marienplatz

# Model footprint in local meters relative to the anchor
import numpy as np
model_xy_m = np.array([[ -50, -50], [50, -50], [50, 50], [-50, 50]])

# Inverse of the SDK's local tangent plane
import math
m_per_deg_lat = 111_320.0
m_per_deg_lon = 111_320.0 * math.cos(math.radians(ANCHOR_LAT))

ring = [
    [ANCHOR_LON + dx / m_per_deg_lon, ANCHOR_LAT + dy / m_per_deg_lat]
    for dx, dy in model_xy_m
]
ring.append(ring[0])    # close
polygon = {"type": "Polygon", "coordinates": [ring]}
```

For the **buildings** payload itself, you can stay in local meters — the SDK accepts DotBim coordinates in polygon-bbox-SW meter frame (X=east, Y=north, Z=up). See [`byo-inputs.md`](byo-inputs.md). The frame origin is the SW corner of the *polygon* bbox, not the model anchor — translate accordingly.

## Sanity checks before running

A 10-line pre-flight catches every CRS bug I've seen:

```python
from infrared_sdk.tiling.validation import validate_polygon, PolygonValidationError
from shapely.geometry import shape

def preflight(polygon: dict, expected_country_iso: str | None = None) -> None:
    p = validate_polygon(polygon)                     # raises on structural issues
    geom = shape(p)
    cx, cy = geom.centroid.x, geom.centroid.y

    # 1. Plausibility: centroid is on land somewhere believable
    if abs(cx) < 1 and abs(cy) < 1:
        raise ValueError(f"Centroid {cx:.4f},{cy:.4f} is Null Island — likely lat/lon swap")

    # 2. Size: SDK is calibrated for <50 km span (~0.5° at 50° lat)
    minx, miny, maxx, maxy = geom.bounds
    if (maxx - minx) > 0.5 or (maxy - miny) > 0.5:
        raise ValueError(f"Polygon span > 0.5° — out of city-scale envelope")

    # 3. Polar / antimeridian guard
    if abs(cy) > 70:
        raise ValueError(f"Centroid lat {cy:.1f}° — local tangent plane distorts at >70°")
    if (maxx - minx) > 180:
        raise ValueError("Polygon appears to cross the antimeridian — not supported")

    # 4. Optional: ISO country check (requires shapely + naturalearth)
    if expected_country_iso:
        ...
```

The **lat/lon swap** check (centroid not near `[0, 0]`) and the **size** check together catch ~all real-world mistakes. Wire this into your client wrapper and you'll never debug a "polygon is in the wrong country" again.

## Picking a metric CRS for your own work (UTM auto-select)

When you need to *also* work in meters alongside the SDK (e.g. computing buffer distances, snapping vertices, comparing to a cadastral layer), pick the UTM zone for the polygon centroid. Same pattern the Infrared QGIS plugin uses:

```python
import math
from pyproj import CRS, Transformer

def utm_crs_for(lon: float, lat: float) -> CRS:
    """WGS84 / UTM zone for a (lon, lat) in degrees."""
    # `% 60` guards the lon=180 (antimeridian) edge — without it the formula yields zone 61.
    zone = int((lon + 180) / 6) % 60 + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)

# Example: project an SDK-ready WGS84 polygon to local meters for buffering
from shapely.geometry import shape
from shapely.ops import transform

geom_4326 = shape(polygon)
cx, cy = geom_4326.centroid.x, geom_4326.centroid.y

utm = utm_crs_for(cx, cy)
to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True).transform
geom_m = transform(to_utm, geom_4326)

# Now you can do metric ops:
buffered_m = geom_m.buffer(50)   # 50-metre buffer
```

Don't use this UTM frame *inside* SDK payloads — the SDK does its own internal projection. Use it for your own pre/post-processing only.

## Outputs: GeoTIFF in WGS84 and in UTM

The default GeoTIFF export from `grid-conventions.md` writes `EPSG:4326`, which displays correctly in any GIS but has non-square pixels in meters away from the equator. For most architectural deliverables, a metric raster is friendlier:

```python
import numpy as np, rasterio
from rasterio.transform import from_bounds
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer

grid = result.merged_grid                    # row 0 = south, row -1 = north
west_4326, south_4326, east_4326, north_4326 = shape(result.polygon).bounds

# Reproject the bbox corners to UTM for a metric raster
utm = utm_crs_for((west_4326 + east_4326) / 2, (south_4326 + north_4326) / 2)
fwd = Transformer.from_crs("EPSG:4326", utm, always_xy=True).transform
west_m, south_m = fwd(west_4326, south_4326)
east_m, north_m = fwd(east_4326, north_4326)

h, w = grid.shape
transform_m = from_bounds(west_m, south_m, east_m, north_m, w, h)

with rasterio.open(
    "result_utm.tif", "w",
    driver="GTiff", height=h, width=w, count=1,
    dtype=grid.dtype, crs=utm.to_string(), transform=transform_m,
    nodata=np.nan,
) as dst:
    dst.write(np.flipud(grid), 1)            # SDK row 0 = south; GeoTIFF row 0 = north
```

Don't skip the `np.flipud` — see `interpretation/grid-conventions.md`.

## Pitfalls

- **CRS-not-WGS84** silently runs in the wrong country. Always `gdf.to_crs("EPSG:4326")` before `mapping()`.
- **`[lat, lon]` instead of `[lon, lat]`** — most common SDK bug. The preflight `Null Island` check catches the worst case.
- **`pyproj.Transformer.from_crs(..., always_xy=False)`** (default) returns `(lat, lon)` for EPSG:4326 and a handful of others. Always pass `always_xy=True`.
- **MultiPolygon input** — SDK takes single Polygon only. Dissolve upstream or pick the largest ring.
- **Z values on polygon** — `POLYGON Z` is fine in shapely but `mapping()` keeps the Z. SDK validation tolerates it (range check only reads `pos[0]`, `pos[1]`), but be explicit: `geom = shapely.force_2d(geom)`.
- **Polygons crossing the antimeridian or `|lat| > 70°`** — not supported. Split or relocate.
- **>50 km span** — local tangent plane distortion + 100-tile cap. Tile by hand if you must.
- **UTM zone boundary** — a polygon straddling two UTM zones (~6° lon apart) projects into one zone with growing distortion at the far edge. At city scale this is invisible; for >20 km E-W you may want LAEA (EPSG:3035 for Europe) instead. The SDK never sees this — it's only for your own metric workspace.

## See also

- [02-geometry.md](02-geometry.md) — polygon format, SDK validation chain
- [byo-inputs.md](byo-inputs.md) — building local-meter frame vs vegetation/ground lon/lat
- [interpretation/grid-conventions.md](interpretation/grid-conventions.md) — GeoTIFF export, row 0 = south
- [Infrared-QGIS plugin](https://github.com/Infrared-city/Infrared-QGIS) — production reference implementation of the QGIS → UTM → SDK conversion chain
