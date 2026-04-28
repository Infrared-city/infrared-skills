# Bring-your-own buildings, vegetation, ground materials

**This is the default workflow.** Most SDK users — architects, urban planners, sustainability consultants — start from data they already have (BIM/Rhino/IFC models, GeoJSON footprints from a planning department, proposed-scenario landscape designs) and want to run microclimate analyses against *that*. The fetch-from-API path (`client.buildings.get_area(...)`) is for quick prototyping over an unknown city block, not for real project work.

When advising a user, always ask first whether they have their own buildings / trees / ground-material data. Default to BYO; fall back to fetched data only when nothing is provided.

## How to pass them

```python
result = client.run_area_and_wait(
    request,
    polygon,
    buildings=my_buildings,         # dict[str, DotBimMesh]
    vegetation=my_vegetation,       # dict[str, GeoJSON Feature]
    ground_materials=my_layers,     # dict[material_name, GeoJSON FeatureCollection]
)
```

All three are **opt-in**: `None` (default) or `{}` means "skip — no data of this type injected". A non-empty dict means "use this".

## Buildings (`AreaBuildings`)

Format: `dict[str, DotBimMesh]` — keyed by stable building id; each mesh has flat XYZ coordinates and face-triplet indices.

**Coordinate frame:** local meter-space, polygon-bbox-SW corner = origin. X = east, Y = north, Z = height. The SDK transforms each building from this frame to the per-tile frame internally — you don't need to do it.

The fetch path returns this shape directly:

```python
area = client.buildings.get_area(polygon)
my_buildings = area.buildings   # ready to pass through
```

For true BYO from a BIM model (Rhino/Revit/IFC → DotBim), you build the same dict yourself. The DotBim format is documented at <https://github.com/paireks/dotbim>; each entry needs `coordinates: list[float]` (flat XYZ, length = 3 × N vertices), `indices: list[int]` (flat triangulation, length = 3 × N faces), and a few metadata fields.

## Vegetation (`AreaVegetation`)

Format: `dict[str, GeoJSON Feature]` — keyed by dedup id (e.g. OSM tree id); each Feature is a Point with `geometry.coordinates = [lon, lat]` and `properties` carrying tree attributes (species, crown radius, height, etc.).

```python
area_veg = client.vegetation.get_area(polygon)
my_trees = area_veg.features
# or: my_trees = {"my_tree_1": {"type": "Feature", "geometry": {...}, "properties": {...}}}
```

**Coordinate frame:** lon/lat (EPSG:4326). Projection is handled server-side.

Note (changed 2026-04): vegetation features used to be converted to DotBim meshes before submission; that's now handled at the inference layer. Pass GeoJSON Points, not meshes.

## Ground materials (`AreaGroundMaterials`)

Format: `dict[str, GeoJSON FeatureCollection]` — keyed by **material name**, each value a FeatureCollection of polygons in lon/lat.

Supported material keys: `asphalt`, `concrete`, `vegetation`, `water`, `soil`, `building`.

```python
area_gm = client.ground_materials.get_area(polygon)
my_layers = area_gm.layers
# {"asphalt": {"type": "FeatureCollection", "features": [...]},
#  "vegetation": {"type": "FeatureCollection", "features": [...]}, ... }
```

To override a layer, replace just that key:

```python
my_layers = {**area_gm.layers, "vegetation": my_custom_park_polygons}
```

## When each layer is needed

| Analysis | Buildings | Vegetation | Ground materials |
|---|---|---|---|
| `wind-speed`, `pedestrian-wind-comfort` | required | optional | optional |
| `sky-view-factors` | required | usually skip | usually skip |
| `daylight-availability`, `direct-sun-hours` | required | optional | optional |
| `solar-radiation` | required | recommended | recommended |
| `thermal-comfort-index` (UTCI), `thermal-comfort-statistics` (TCS) | required | recommended | recommended |

For wind/SVF you can pass `vegetation={}` and `ground_materials={}` to skip injection. For thermal/solar, omitting them produces a less realistic surface energy balance.

## Mixing fetched + BYO

The cookbook's recipe 04 shows fetch-once-reuse. The same pattern lets you fetch some layers and override others — e.g. keep fetched buildings + vegetation, override ground materials with a proposed redesign:

```python
area = client.buildings.get_area(polygon)
area_veg = client.vegetation.get_area(polygon)
area_gm = client.ground_materials.get_area(polygon)

my_layers = {**area_gm.layers, "vegetation": my_proposed_park_polygons}

result = client.run_area_and_wait(
    request, polygon,
    buildings=area.buildings,
    vegetation=area_veg.features,
    ground_materials=my_layers,
)
```

## Pitfalls

- **`{}` = skip, not "use empty"** — passing an empty dict is the same as `None`.
- **Coordinate frames differ across the three layer types** — buildings are local meters (polygon-bbox-SW); vegetation and ground materials are lon/lat. Do not pass lon/lat-style vertices to `buildings`.
- **Polygon order: `[lon, lat]`** for all GeoJSON (RFC 7946). Lat-first is the most common bug.
- **Large ground-material sets hit request-size limits** — if `total_features` > ~5000, pre-filter or pass `ground_materials={}`.
- **Material keys must match the supported set** above; arbitrary keys are silently dropped.
- **Only one polygon** — `polygon` must be a single GeoJSON `Polygon` (not `MultiPolygon`), CCW outer ring, no self-intersection, no holes.
- **Building coordinates are flat lists**, not nested per-vertex — `[x0, y0, z0, x1, y1, z1, ...]`, not `[[x, y, z], ...]`.
