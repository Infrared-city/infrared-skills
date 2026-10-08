# Python: your own buildings, trees and ground

Your own model is the main input. A run on your design shows your design.
Public data is a fallback for when you have no model (last section).

Docs: guide chapter "Your inputs" (<https://infrared.city/docs/sdk/1.0/sdk.md>), and the pages
[Buildings](https://infrared.city/docs/sdk/1.0/python/buildings/index.md),
[Vegetation](https://infrared.city/docs/sdk/1.0/python/vegetation/index.md),
[Ground materials](https://infrared.city/docs/sdk/1.0/python/ground_materials/index.md),
[Geometry](https://infrared.city/docs/sdk/1.0/python/geometry/index.md).

## The three layers

| Layer | Shape | Frame |
|---|---|---|
| `buildings` | `{id: {"coordinates": [x, y, z, ...], "indices": [i, j, k, ...]}}` | metres, origin = south-west corner of the polygon bounding box |
| `vegetation` | `{id: GeoJSON Point Feature}` with `genus`, `height`, `crownDiameter` | lon/lat |
| `ground_materials` | `{material: GeoJSON FeatureCollection}`, materials: `asphalt`, `concrete`, `soil`, `vegetation`, `water` | lon/lat |

Rules that the SDK cannot check for you:

- x east, y north, z up. Metres. Each building is one closed solid with a bottom face.
- The origin is the south-west corner of the polygon bounding box, not the centre.
- Lat and lon swapped is caught only when the latitude is above 90. Check the order.
- A tree with no `height` or `crownDiameter` gets 6 m and 4 m, with no warning.
- Ground materials change only the thermal results. Terrain and far shade go on the request:
  [surfaces-and-sensors.md](surfaces-and-sensors.md).

## Footprints (GeoJSON) to building meshes

Plans give footprints and heights. This helper extrudes them into closed solids. It needs `shapely` 2.1 or later.

```python
import math
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

lon0, lat0 = 16.371, 48.208                      # south-west corner of the polygon

def ll(dx, dy):                                  # lon/lat point, offset in steps of 0.0001 degrees
    return [lon0 + dx * 0.0001, lat0 + dy * 0.0001]

def ring(*pts):                                  # GeoJSON Polygon from offsets
    return {"type": "Polygon", "coordinates": [[ll(*p) for p in (*pts, pts[0])]]}

polygon = ring((0, 0), (40, 0), (40, 30), (0, 30))

# Local conversion from lon/lat to metres from the corner. Good for a site of a few km.
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(lat0))

def to_metres(lon, lat):
    return (lon - lon0) * M_LON, (lat - lat0) * M_LAT

def extrude(footprint: dict, height: float, base_z: float = 0.0) -> dict:
    """Closed solid from a GeoJSON Polygon (lon/lat) and a height in metres."""
    ring = [to_metres(*p) for p in footprint["coordinates"][0][:-1]]
    poly = orient(Polygon(ring), 1.0)                       # counter-clockwise
    ring = list(poly.exterior.coords)[:-1]
    slot = {p: i for i, p in enumerate(ring)}               # vertex -> index
    n = len(ring)
    coords = [c for z in (base_z, base_z + height) for x, y in ring for c in (x, y, z)]
    idx = []
    # Roof and floor: triangles that cover the footprint (also if concave).
    for tri in shapely.constrained_delaunay_triangles(poly).geoms:
        a, b, c = [slot[p] for p in list(tri.exterior.coords)[:3]]
        (xa, ya), (xb, yb), (xc, yc) = ring[a], ring[b], ring[c]
        if (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya) < 0:   # make it counter-clockwise
            b, c = c, b
        idx += [n + a, n + b, n + c]                        # roof, faces up
        idx += [a, c, b]                                    # floor, faces down
    # Walls: two triangles per edge, faces out.
    for i in range(n):
        j = (i + 1) % n
        idx += [i, j, n + j, i, n + j, n + i]
    return {"coordinates": coords, "indices": idx}

# Footprints with a height, for example from a planning GeoJSON.
footprints = {
    "block-a": (ring((10, 8), (14, 8), (14, 11), (10, 11)), 24.0),
    "block-b": (ring((20, 10), (26, 10), (26, 12), (23, 12), (23, 15), (20, 15)), 15.0),  # L-shape
}
buildings = {name: extrude(fp, h) for name, (fp, h) in footprints.items()}
xyz = np.array(buildings["block-a"]["coordinates"]).reshape(-1, 3)
print("block-a x from", xyz[:, 0].min().round(1), "to", xyz[:, 0].max().round(1), "m")   # metres, small
```

A model from Rhino, IFC or glTF gives the same dict. Check the axes (Y-up is a trap).
`infrared_sdk.geometry.clean_mesh(coordinates, indices)` welds vertices and fixes the winding.
Clean each building on its own.

## Trees and ground

```python
# Trees: one GeoJSON Point Feature each. `genus` sets the crown shape.
trees = {
    f"tree-{i}": {"type": "Feature", "geometry": {"type": "Point", "coordinates": ll(17 + i, 6)},
                  "properties": {"genus": "tilia", "height": 12.0, "crownDiameter": 7.0}}
    for i in range(4)
}

# Ground: one FeatureCollection per material. Layers must not overlap.
def layer(*polygons):
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": p} for p in polygons]}

ground_materials = {
    "asphalt": layer(ring((0, 0), (40, 0), (40, 5), (0, 5))),                 # a road strip
    "vegetation": layer(ring((15, 5), (30, 5), (30, 9), (15, 9))),            # a park
}
```

Overlapping material layers can give the wrong material. Cut them so that each point has one material.

## Run with your layers

```python
from infrared_sdk import InfraredClient, SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

client = InfraredClient()
request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)
result = client.run_area_and_wait(request, polygon, buildings=buildings,
                                  vegetation=trees, ground_materials=ground_materials)
print(float(np.nanmin(result.physical_grid())))
```

## No model yet: public data as a fallback

Use this for a first look, a demo, or the context around your design. Buildings come from the
Infrared city overlay where it exists, else from Overture Maps. Heights are partly estimated.

```python
# Needs: pip install "infrared-sdk[geodata]"
area_b = client.buildings.get_area(polygon)          # AreaBuildings, keeps its origin
area_t = client.vegetation.get_area(polygon)         # trees (GeoJSON)
area_g = client.ground_materials.get_area(polygon)   # ground layers
print(len(area_b.buildings), "buildings", area_t.total_trees, "trees")

# Pass the whole buildings object, not area_b.buildings: it records its frame.
public = client.run_area_and_wait(request, polygon, buildings=area_b,
                                  vegetation=area_t.features, ground_materials=area_g.layers)
```

To mix both, merge the dicts (`{**area_b.buildings, **buildings}`) only when both use the same
frame: the south-west corner of the same polygon. Limits: see the Buildings page above.
