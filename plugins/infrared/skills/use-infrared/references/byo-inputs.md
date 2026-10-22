# Bring your own buildings, trees and ground

Your own model is the main input. Ask first what the user has: BIM, Rhino, IFC, GeoJSON footprints,
a proposed landscape. Use public data only when there is nothing else, and say so.
Code: [python/own-data.md](python/own-data.md). To put files into the platform, see
[platform-byo-upload.md](platform-byo-upload.md).

## Shapes

```python
result = client.run_area_and_wait(
    request, polygon,
    buildings=my_buildings,        # {id: {"coordinates": [x, y, z, ...], "indices": [i, j, k, ...]}}
    vegetation=my_trees,           # {id: GeoJSON Point Feature}
    ground_materials=my_layers,    # {material: GeoJSON FeatureCollection}
)
```

`None` or `{}` sends nothing for that layer.

### Buildings

- Metres. Origin = south-west corner of the polygon bounding box. x east, y north, z up.
- Flat lists: `[x0, y0, z0, x1, ...]`, not `[[x, y, z], ...]`. Each entry needs `coordinates` and `indices`.
  The service drops a mesh without `indices` without any error.
- Each building is one closed solid with a bottom face. Open meshes give wrong shade.
- Public data: `client.buildings.get_area(polygon)` returns an `AreaBuildings` object that records its
  frame. Pass the **object**, not `.buildings`. A bare map is read as "in the frame of the run polygon".
  If you fetch for polygon A and run polygon B with the bare map, the city moves by the distance between
  the two corners.
- A DotBim file has the same fields ([dotbim](https://github.com/paireks/dotbim)).

### Facade materials

- Optional `material` on each `geometries` entry, one entry per building, keyed by the building id:
  `{"version": 1, "preset": "brick"}`. In Python: `DotBimMesh.material`.
- Presets: `default`, `masonry`, `brick`, `concrete`, `light-paint`, `dark-paint`, `metal` (painted),
  `wood`, `glass`, the green facades (`green-climbing`, `green-modular`, `green-living-wall`) and `pv`.
  Or set `rho-solar` (0 to 1), `emissivity` (0 to 1) and `pv-efficiency` (0 to 0.4). A field beats the preset.
- `glass` is an opaque, diffuse equivalent. It does not predict a curtain wall.
- An unknown or invalid value is removed or set to `default`, with a warning. The run does not fail.
- UTCI and TCS (`standard`) read it. The model includes the shortwave that a wall reflects.
- Preview, in the next SDK release: `roof-material` (same object) on the entry sets the roof, and the
  `installations` group (below) holds thin pieces.

### Trees

- `{id: Feature}` with a Point in lon/lat. Properties: `genus`, `height` (m), `crownDiameter` (m).
- An unknown `genus` is a broadleaf. A tree with no size gets 6 m and 4 m, with no warning.
  Crown keys are the **diameter**, not the radius. A radius makes every tree half as wide.
  Other property names (`crown_radius`, `treeHeight`) are ignored. The SDK warns when a size-like key
  holds a number but is not read.
- Leaf-off: north of 23.5 N, trees are bare from November to March. This changes the three sun
  analyses. SVF always uses leaf-on. Set `"transmissivity-leaf-off"` (0 to 1) in the properties of
  one tree to change it.

### Ground materials

- One FeatureCollection in lon/lat for each material: `asphalt`, `concrete`, `soil`, `vegetation`, `water`.
  An unknown name raises. A UUID key is refused.
- UTCI, TCS and solar radiation read them. Solar radiation uses the ground reflectance of each
  material (0.2 without one).
- A feature can carry `albedo` (0 to 1) and `dt-max` (0 to 50 K) in its properties. They beat the
  value of the material for that feature. `irrigated: true` or `soil-moisture` marks a wet ground
  surface (preview, in the next SDK release). `ground_albedo` on the request sets one value for the
  whole run. An invalid value is ignored with a warning. The run does not fail.
- Make layers mutually exclusive. If two overlap, the model picks the top one and a tie can turn
  a lake into asphalt. Fetched layers come pre-cleaned. When you override, replace one key:
  `{**area_g.layers, "vegetation": my_park}`.

## Which layers each analysis needs

| Analysis | Buildings | Trees | Ground materials |
|---|---|---|---|
| wind speed, pedestrian wind comfort | required | optional | no effect |
| sky view factor | required | optional | no effect |
| daylight availability, direct sun hours | required | optional | no effect |
| solar radiation | required | recommended | optional (ground reflectance) |
| UTCI, TCS | required | recommended | recommended |

## Fetched buildings: know the source

With no `buildings`, you can fetch public ones (`[geodata]` extra). A few cities come from curated
survey data with measured heights. Elsewhere the source is Overture footprints, and heights are partly
inferred. The response never says which source you got. Two cities compared this way compare two
data classes. Pass your own buildings when you have them.

## Mixed

```python
area_b = client.buildings.get_area(polygon)            # neighbours, public
my_layers = {**client.ground_materials.get_area(polygon).layers, "vegetation": my_park}
result = client.run_area_and_wait(request, polygon, buildings=area_b,
                                  vegetation=client.vegetation.get_area(polygon).features,
                                  ground_materials=my_layers)
```

## Terrain, context and installations


`ground_geometry` (terrain) and `context_geometry` (far shade) go on the request, in the building
frame. Never put terrain in `buildings`.
See [analyses/11-terrain-and-context.md](analyses/11-terrain-and-context.md).

Preview, in the next SDK release: `installations` takes thin pieces, such as green panels, window
strips, fins, roof PV and PV canopies, in the same mesh shape (`material` allowed). They shade the
sun and light analyses, SVF and UTCI (every tier). They get no sensors. Wind ignores them.
Python request models take `installations` directly. A `pv` piece adds `pv_yield` to the area or
surface result, grouped by entry id and side.

## Meshes from OBJ, glTF and BIM: weld first

Exporters write triangle soup: three vertices for each triangle, nothing shared. Round to
1 cm, then weld: the upload gets smaller. A request over 64 MiB is refused (413).

```python
import numpy as np
from infrared_sdk.geometry import clean_mesh

# Round first. clean_mesh joins only vertices at the exact same position,
# so rounding after it would leave near-equal vertices split.
rounded = np.round(np.asarray(mesh["coordinates"], dtype=float), 2)
cleaned = clean_mesh(rounded.ravel().tolist(), mesh["indices"])   # welds, drops bad triangles, orients outward
mesh = {"coordinates": cleaned.coordinates.tolist(),
        "indices": cleaned.indices.tolist()}
print(cleaned.report)
```

Clean each building alone: two touching objects must stay apart.

## Dense or photogrammetric models

The batch estimator for facades is `area / grid_size^2`. On finely triangulated meshes, each small
facet rounds up to one cell, so the estimate is too low and the run is refused (422).
Halve `max_sensors_per_job`, or raise `surface_grid_size`.

## Pitfalls

- `[lat, lon]` instead of `[lon, lat]`. The SDK catches it only when the latitude is above 90.
- Y-up models, centimetres, an origin at the polygon centre: all silent. Look at the model in a viewer first.
- One polygon only: a `Polygon`, not a `MultiPolygon`, one ring, no holes.
- Coordinates must stay below 100,000 m. UTM values are refused.
- Overlapping solids (a coarse block and its detailed mesh, a cap, a pedestal) give facades at 0:
  [geometry-pitfalls.md](geometry-pitfalls.md).
- Large ground sets work. Pass the real layers. Never drop them to save size: you lose the materials.
