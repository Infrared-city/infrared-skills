# Geospatial / CRS recipes

The SDK takes **WGS84 lon/lat in degrees** (GeoJSON RFC 7946). It does not negotiate CRS, does not reproject, does not warn on plausibility — if you hand it coordinates in another CRS or in `[lat, lon]` order, it runs anyway, on the wrong patch of the planet.

This file is the conversion + sanity layer for anyone arriving with real GIS data: shapefiles, GeoPackages, KML, PostGIS, rasterio bbox, Rhino/IFC models, QGIS layers. It is also the **authoritative map of every frame the SDK uses** — degrees in, two metre frames in the middle, a surface UV frame out.

## The frames, end to end

Four frames. Nothing in the API errors when you supply the wrong one — geometry simply lands somewhere else and the run succeeds.

| Frame | Units / origin | What is in it |
|---|---|---|
| **WGS84 lon/lat** | degrees, `[lon, lat]` (RFC 7946) | the `polygon` argument; `vegetation` and `ground_materials` features |
| **Polygon-bbox-SW metres** | SW corner of the *polygon's bounding box* = `(0, 0)`; `+x` east, `+y` north, `z` up | `buildings`, `context_geometry`, `ground_geometry` as passed to `run_area()` / `run_area_and_wait()`; what `client.buildings.get_area()` returns |
| **Tile-local metres** | SW corner of that tile's **inference** square = `(0, 0)`; same axes | `payload.geometries` on a single-tile `client.analyses.execute()`; `sensor_points` / `sensor_normals`; interior-model geometry |
| **Surface UV** | per-surface `origin` + `u_axis` / `v_axis`, in tile metres | `SurfaceAnalysisResult.surfaces[...]` — results, never inputs |

**Two things in one payload are in degrees, not metres.** `vegetation` and `ground_materials` stay
WGS84 lon/lat while `buildings` alongside them is in metres. Verified on a live fetch: a tree comes
back as `{"geometry": {"type": "Point", "coordinates": [11.575942, 48.199694]}}`. Passing metre
vertices to `vegetation` puts every tree off the coast of Africa without complaint.

### Who converts, and when

- `client.buildings.get_area(polygon)` fetches per tile, deduplicates, and hands everything back in **polygon-bbox-SW** — one frame for the whole area, whichever tile a building came from.
- `run_area()` / `run_area_and_wait()` do the **polygon-bbox-SW → tile-local** step for you, per tile: they subtract that tile's inference SW offset from `buildings`, `context_geometry` and `ground_geometry`. You never write this transform.
- `client.analyses.execute()` does **not**. It is a single-tile primitive, so whatever you put in `payload.geometries` and `sensor_points` is already read as tile-local.

That is the whole split: **go through `run_area*` and you speak polygon-bbox-SW; drop to the job
primitives and you speak tile-local.** The failure is mixing the two — building a payload by hand
from `area.buildings` and posting it through `analyses.execute()` offsets the entire scene by the
tile's position within the polygon, and both the request and the result look completely normal.

### The frame rule

The SDK reads every mesh coordinate you pass to `run_area*` as **metres from the polygon's bbox SW corner** — it never re-anchors your geometry to the polygon — and every result, the merged grid raster **and** `SurfaceAnalysisResult` surfaces alike, comes back **in the frame you submitted**. So the polygon and the geometry must agree on one point: **the polygon's SW corner is submitted `(0, 0)`.**

- **Choose the corner, then express every vertex relative to it.** The natural choice is the geometry's min (x, y): build the polygon there and submit `vertex − (x_min, y_min)`. If your model origin already *is* that corner (the ArchiCAD exports measured here had their terrain min at exactly `(0, 0)`), submit as-is.
- **Pad only to the north-east.** The NE edge is free (the grid is NE-padded anyway); the SW corner is not. A pad to the **south-west** of submitted `(0, 0)` moves the whole scene geographically by that pad while your model does not — measured on a single-tile ArchiCAD site (2026-09-02, two independent checks): a 10 m SW pad dropped the footprint-mask IoU from **0.55 to 0.38** and the terrain-disc IoU from **0.992 to 0.921**. It looked entirely plausible until overlaid on the buildings.
- With the corner right, cell `(j, i)` of the grid sits at `(i + 0.5, j + 0.5)` in your own metres (plus the corner, if you subtracted one), and surface `origin` / `cell_tris` need no shift at all — on the corrected frame the `cell_tris` bbox of a building matched its submitted mesh to within half a cell.
- **Verify before you measure anything.** Overlay the result on the submitted footprints. A uniform offset is invisible in the numbers.

Recipe D below builds the polygon this way.

### Negative coordinates are correct — do not filter them

In **both** metre frames, negative x/y is normal and load-bearing:

- Out of `get_area`, buildings are collected from tiles covering a margin around the polygon, so ones south or west of the bbox corner have negative coordinates. Measured on a 200 m Munich polygon: 505 buildings spanning `x ∈ [-133.1, 394.1]`, `y ∈ [-174.3, 390.0]`.
- Per tile, a building pulled in by the 128 m solar context margin sits outside the 0–512 m inference range by construction.

A tidy-up pass that drops negatives deletes exactly the neighbours that were there to cast shadow
into your site. The result stays plausible and gets brighter.

### Vertical datum

`z` is metres up, and it is **relative** — the SDK asserts no geoid, no ellipsoid, no vertical EPSG.
Only the internal agreement between your terrain and your buildings matters.

`client.buildings.get_area()` returns every building **based at exactly `z = 0`** (verified: 505 of
505 on a live fetch). They carry height, not elevation. So if you pair fetched buildings with a DEM
in real orthometric or ellipsoidal heights, the two disagree by the site elevation — a few hundred
metres in most of Europe. That is what `terrain_alignment` is for:

| Mode | Behaviour |
|---|---|
| `"auto-align"` (default) | Re-bases every solid in `geometries` / `context_geometry` / `vegetation` onto the terrain below it before inference, with a 0.5 m skirt. Absorbs the mismatch silently — which is why fetched buildings plus an absolute DEM "just work". |
| `"assume-aligned"` | Moves nothing — a validator, not a fixer. Any base outside the seated band is a **422 for the whole job**, naming the offenders with residuals. Use it when you have prepped geometry against this exact DEM and want a mismatch to be loud. |
| `"as-is"` | Trusts your geometry exactly: no seating, no check. For BIM/CAD exports already placed on their terrain. Admitted by the SDK `Literal` from **0.5.2**; on 0.5.1 it fails client-side. |

None of the three moves the sensor grid — it always drapes onto `ground_geometry`. With no `ground_geometry` the setting is inert and you get a **flat plane at z = 0** — not an error,
and a result that looks entirely normal. Full treatment: [`analyses/09-facade-terrain.md`](analyses/09-facade-terrain.md#terrain_alignment--how-your-geometry-meets-the-ground).

### Surface UV frames (results)

Each `SurfaceSensorGrid` carries `origin`, `u_axis`, `v_axis` in tile metres. The frame is
**right-handed: the outward normal is `u_axis × v_axis`, in that order** — the server builds it as
`u = ẑ × n`, `v = n × u`, so outward-wound shells (everything `client.buildings` returns) give
outward normals. Because `+x` is east and `+y` north, the compass bearing is
`degrees(atan2(n[0], n[1])) % 360`.

Cross-checked on a live 21 June direct-sun-hours run over a 200 m Munich block: the cross product
points away from its own building on **1,526 of 1,538** vertical facades, and area-weighted mean sun
hours by bearing came out **S 7.73 h, E 6.11 h, W 5.64 h, N 4.78 h** — an ordering only produced if
the normal points outward and the bearing is measured this way. `s.is_vertical` agreed with
`|n_z| ≤ 0.5` on all 1,538.

Cell-centre maths, texture mapping and `cell_tris` live in
[`surface-results-integration.md`](surface-results-integration.md), which is canonical for the UV
frame — don't re-derive it here.

## Diagnostic — "my geometry is in the wrong place"

Nothing below raises. Work down the table.

| Symptom | Likely frame error |
|---|---|
| Result is over open water, farmland, or another country | Polygon is not WGS84, or is `[lat, lon]`. Run the preflight below. |
| Everything mirrored about the diagonal | `[lat, lon]` swap specifically — or `pyproj` without `always_xy=True`. |
| Buildings offset by a whole multiple of 512 m (or 256 m on wind) | Polygon-bbox-SW geometry posted straight to `analyses.execute()`, which expects tile-local. |
| Only the SW tile looks right; other tiles are bare | Same cause, seen across a multi-tile run. |
| Trees or ground materials nowhere near the site | Metre vertices passed where lon/lat was expected. |
| Site is unexpectedly bright; distant blocks cast no shadow | Negative-coordinate buildings filtered out, or a >128 m occluder that is simply out of tile context. |
| Buildings float above or sink into the terrain | `ground_geometry` on an absolute vertical datum against `z = 0` buildings — see above. |
| Grid **and** surfaces sit a constant few metres off the buildings, uniformly | Polygon SW corner is not at submitted `(0, 0)` — padded SW of the geometry, or geometry not re-expressed relative to the corner. See *The frame rule*. |
| Terrain shading vanished after upgrading to 0.5.1 | Terrain is now sliced per tile; pass distant relief as `context_geometry`. |
| Heatmap overlay is squashed toward the SW | Placed with `polygon.bounds` instead of `result.bounds` (which is NE-padded to the grid). |
| Exported GeoTIFF is upside down | SDK row 0 is south, GeoTIFF row 0 is north — `np.flipud`. |

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

## Getting to WGS84 — recipes A–D

Recipes A–D below are the canonical reprojection recipes for the SDK; other references link here
rather than repeating them.

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

BIM models live in a local metre frame anchored to some site origin. Derive the polygon **from the model's own extent** — the frame rule above — so that the polygon's SW corner lands on the geometry's min (x, y), pad NE only, and submit every vertex relative to that corner. One WGS84 anchor for the model's `(0, 0)` is the only constant.

```python
import math
import numpy as np

# Site anchor in WGS84 (from the model's "true north / site location" metadata): the model's (0, 0)
ANCHOR_LON, ANCHOR_LAT = 11.5755, 48.1975

def polygon_around_model(all_xyz, anchor_lon, anchor_lat, ne_margin_m=10.0):
    """Polygon whose bbox SW corner == the geometry's min (x, y). Pads NE only.
    Returns (polygon, corner); submit every mesh as vertex - corner."""
    v = np.asarray(all_xyz, dtype=float).reshape(-1, 3)
    x0, y0 = v[:, 0].min(), v[:, 1].min()                  # SW pinned — no pad here
    x1, y1 = v[:, 0].max() + ne_margin_m, v[:, 1].max() + ne_margin_m
    m_per_deg_lat = 111_320.0                              # inverse of the SDK's tangent plane
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(anchor_lat))
    ll = lambda x, y: [anchor_lon + x / m_per_deg_lon, anchor_lat + y / m_per_deg_lat]
    ring = [ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1), ll(x0, y0)]
    return {"type": "Polygon", "coordinates": [ring]}, (float(x0), float(y0))

def shift(mesh, corner):
    """Re-express one {coordinates, indices} mesh relative to the polygon corner."""
    v = np.asarray(mesh["coordinates"], dtype=float).reshape(-1, 3)
    v[:, 0] -= corner[0]; v[:, 1] -= corner[1]
    return {**mesh, "coordinates": v.ravel().tolist()}

polygon, corner = polygon_around_model(every_vertex_you_will_submit, ANCHOR_LON, ANCHOR_LAT)
buildings = {k: shift(m, corner) for k, m in model_buildings.items()}   # same for context / terrain
```

Feed `polygon_around_model` **every** vertex you will submit (buildings, terrain, occluders), so nothing lies south or west of the corner; if the corner comes out at `(0, 0)`, `shift` is a no-op and you can submit as-is. The **buildings** payload then stays in metres — the SDK reads DotBim coordinates as polygon-bbox-SW (X = east, Y = north, Z = up), see [`byo-inputs.md`](byo-inputs.md) — and `corner` is the only number you need to map results back: grid cell `(j, i)` → `corner + (i + 0.5, j + 0.5)`; surface `origin` / `cell_tris` → `+ corner`. Good to ~50 km spans; not for |lat| > 70°.

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
- [05-area-api.md](05-area-api.md) — the per-tile transform step by step, context margin, `AreaResult.bounds`
- [surface-results-integration.md](surface-results-integration.md) — **canonical** for the surface UV frame: cell centres, `cell_tris`, texture mapping
- [analyses/09-facade-terrain.md](analyses/09-facade-terrain.md) — `ground_geometry`, `terrain_alignment`, per-tile terrain slicing
- [interpretation/grid-conventions.md](interpretation/grid-conventions.md) — GeoTIFF export, row 0 = south
- [Infrared-QGIS plugin](https://github.com/Infrared-city/Infrared-QGIS) — production reference implementation of the QGIS → UTM → SDK conversion chain
