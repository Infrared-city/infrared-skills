# Sample facade values in three.js

Read values out of a facade and roof result: pick a cell, sample at your own
points, get statistics per building or surface, and export them.
Copy `src/sample.ts` from
[cookbook/apps/facades-3d](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/facades-3d).
It works on the SDK `SurfaceColumns` (typed arrays) and has no three.js import.
Drawing the result: [facades-3d.md](facades-3d.md).

## What you need to know

- A surface is one flat wall or roof part with a grid of `nu` x `nv` cells.
  Surface row `r` owns cells `cellOffsets[r]` to `cellOffsets[r + 1] - 1`.
- A surface id is `"<building id>/<n>"`. The building id is the part before the
  last `/`. Get the id with `surfaceId(columns, row)`.
- `surfaceValuesF32(columns)` gives the physical values (NaN = no value). Make it
  once and keep it. Never read `columns.values` yourself.
- Positions use the run frame: metres from the polygon's south-west corner,
  x east, y north, z up. `origin` of a surface is the centre of its cell (0, 0).

## 1. Pick: raycast hit → value and ids

```ts
import { cellFromHit, cellInfo } from "./sample";

const values = surfaceValuesF32(columns);                 // once per result
const hit = raycaster.intersectObject(mesh)[0];
const k = hit ? cellFromHit(hit, mesh.geometry) : -1;     // -1 = no cell
if (k >= 0 && surfaceHasValue(columns, k)) {
  const { value, surfaceId, buildingId } = cellInfo(columns, values, k);
}
```

`cellFromHit` mixes the `cell` attribute of the three triangle corners with
`hit.barycoord`, then uses the same cell rule as the shader. `cellInfo` finds the
surface row with a binary search in `cellOffsets`.

## 2. Sample at your own 3D points

```ts
import { cellsAtPoints } from "./sample";

// points: x, y, z, x, y, z, ... in the run frame (for example sensors or clicked points)
const cells = cellsAtPoints(columns, points, 0.5);       // -1 = no surface within 0.5 m
const sampled = Array.from(cells, (k) => (k >= 0 && surfaceHasValue(columns, k) ? values[k] : NaN));
```

For each point, the helper finds the nearest surface plane within the distance
and the cell of that surface's grid that holds the point. `hit.point` of a
three.js raycast is already in this frame, because the mesh sits at `buffers.anchor`.

## 3. Statistics per building or per surface

```ts
import { surfaceStats } from "./sample";

const perBuilding = surfaceStats(columns, "building");   // [{ id, area, mean, min, max, p90 }]
const perSurface = surfaceStats(columns, "surface");
```

- One pass over the typed arrays, then one sort by group and value. No object per cell.
  A result with 217,000 cells takes about 0.2 s in Node.
- `mean` and `p90` are area-weighted. Cells with no value do not count.
- By default every cell counts in full. Then `area` and `mean` equal the SDK's
  own `columns.area`, `columns.mean` and `columns.aggregates.buildings`.
- `surfaceStats(columns, "building", true)` weights each cell by the part of it
  that the wall covers (`columns.cellArea`, 0 to 1). Use it when you need the
  true wall area, for example kWh per m² of real facade. On small buildings the
  two ways can differ a lot.

## 4. Export

```ts
import { download, toCsv, toJson } from "./sample";

download("buildings.csv", toCsv(perBuilding));
download("buildings.json", toJson(perBuilding), "application/json");
```

`toCsv` writes a header from the keys of the first row. Both write NaN as an
empty cell or `null`. In Node, write the text with `fs.writeFileSync`.

## Tested

Offline, on a saved solar radiation result (909 buildings, 10,031 surfaces,
217,083 cells), no API call:

- `surfaceStats(columns, "building")` (the default) equals `aggregates.buildings`
  (area, mean, peak) for all 909 buildings. Per surface it equals `columns.mean`.
- 2,158 picks at triangle centres: `cellsAtPoints` at the same 3D points gave the
  same cell for 2,155 and the same value for 2,151 of 2,154 cells with a value.
  The rest sit where two surfaces meet.
