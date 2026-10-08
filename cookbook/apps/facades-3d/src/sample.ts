// Read values out of a facade/roof result: pick, sample at points, stats, export.
// Works on the SDK `SurfaceColumns` (typed arrays, one entry per surface or cell).
// No three.js import: the pick helper takes the raycast hit and the mesh geometry.
//
// Ids: a surface id is "<building id>/<n>", so the building id is the part before the last "/".

import { surfaceId, surfaceValuesF32, type SurfaceColumns } from "@infrared-city/infrared-sdk-ts";
import { cellIndex } from "./surface-mesh.ts";

export interface CellInfo { cell: number; row: number; surfaceId: string; buildingId: string; value: number }

/** The surface row that owns cell k (binary search in `cellOffsets`). */
export function rowOfCell(c: SurfaceColumns, k: number): number {
  let lo = 0, hi = c.surfaceCount - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (c.cellOffsets[mid] <= k) lo = mid; else hi = mid - 1;
  }
  return lo;
}

/** Cell k with its ids. `values` = surfaceValuesF32(c), made once (NaN = no value). */
export function cellInfo(c: SurfaceColumns, values: Float32Array, k: number): CellInfo {
  const row = rowOfCell(c, k);
  const id = surfaceId(c, row);
  return { cell: k, row, surfaceId: id, buildingId: id.slice(0, id.lastIndexOf("/")), value: values[k] };
}

// ---- 1. Pick: raycast hit -> cell index (the same rule as the shader) ----
type Attr = { getX(i: number): number; getY(i: number): number; getZ(i: number): number };
type Hit = { faceIndex?: number | null; barycoord?: { x: number; y: number; z: number } | null };

/** Cell index under a three.js raycast hit on the surface mesh, or -1. */
export function cellFromHit(hit: Hit, geometry: { getAttribute(name: string): Attr }): number {
  if (hit.faceIndex == null || !hit.barycoord) return -1;
  const cell = geometry.getAttribute("cell"), frame = geometry.getAttribute("frame");
  const v0 = 3 * hit.faceIndex, w = [hit.barycoord.x, hit.barycoord.y, hit.barycoord.z];
  // (s, t) of the hit point = barycentric mix of the three corners' cell coordinates.
  let s = 0, t = 0;
  for (let i = 0; i < 3; i += 1) { s += w[i] * cell.getX(v0 + i); t += w[i] * cell.getY(v0 + i); }
  return cellIndex(frame.getX(v0), frame.getY(v0), frame.getZ(v0), s, t);
}

// ---- 2. Sample at 3D points (run frame: metres from the polygon's SW corner, z up) ----
/**
 * For each point, the cell whose surface plane is nearest (within `maxDist` m) and
 * whose grid contains the point. Returns one cell index per point, -1 = no surface.
 * `origin` is the centre of cell (0, 0); the axes are unit vectors; one cell = gridSize.
 */
export function cellsAtPoints(c: SurfaceColumns, points: ArrayLike<number>, maxDist = 0.5): Int32Array {
  const n = points.length / 3, out = new Int32Array(n).fill(-1), best = new Float64Array(n).fill(maxDist);
  for (let r = 0; r < c.surfaceCount; r += 1) {
    const o = c.origin.subarray(3 * r, 3 * r + 3), u = c.uAxis.subarray(3 * r, 3 * r + 3), v = c.vAxis.subarray(3 * r, 3 * r + 3);
    const nx = u[1] * v[2] - u[2] * v[1], ny = u[2] * v[0] - u[0] * v[2], nz = u[0] * v[1] - u[1] * v[0]; // plane normal
    const g = c.gridSize[r], nu = c.nu[r], nv = c.nv[r];
    for (let p = 0; p < n; p += 1) {
      const dx = points[3 * p] - o[0], dy = points[3 * p + 1] - o[1], dz = points[3 * p + 2] - o[2];
      const d = Math.abs(dx * nx + dy * ny + dz * nz);
      if (d >= best[p]) continue;
      const s = (dx * u[0] + dy * u[1] + dz * u[2]) / g + 0.5;  // +0.5: origin is a cell centre
      const t = (dx * v[0] + dy * v[1] + dz * v[2]) / g + 0.5;
      if (s < 0 || t < 0 || s >= nu || t >= nv) continue;
      best[p] = d;
      out[p] = c.cellOffsets[r] + Math.floor(t) * nu + Math.floor(s);
    }
  }
  return out;
}

// ---- 3. Stats per surface or per building, from the columns in one pass ----
export interface GroupStats { id: string; area: number; mean: number; min: number; max: number; p90: number }

/**
 * Area-weighted mean and p90, min and max of the cells with a value, per group.
 * Weight of a cell = gridSize² x its covered fraction (`cellArea`, 0..1; a cell cut by
 * the wall outline covers less). With `cutCells = false` every cell counts in full:
 * then `area` and `mean` equal the SDK's own `columns.area`/`mean` and `aggregates`.
 */
export function surfaceStats(c: SurfaceColumns, by: "surface" | "building", cutCells = true): GroupStats[] {
  const values = surfaceValuesF32(c);
  const cells = c.cellOffsets[c.surfaceCount];
  // Group index per surface row, then per cell.
  const ids: string[] = [], index = new Map<string, number>(), rowGroup = new Int32Array(c.surfaceCount);
  for (let r = 0; r < c.surfaceCount; r += 1) {
    const sid = surfaceId(c, r), key = by === "surface" ? sid : sid.slice(0, sid.lastIndexOf("/"));
    let gi = index.get(key);
    if (gi === undefined) { gi = ids.length; ids.push(key); index.set(key, gi); }
    rowGroup[r] = gi;
  }
  const group = new Int32Array(cells), weight = new Float64Array(cells);
  for (let r = 0; r < c.surfaceCount; r += 1) {
    const g2 = c.gridSize[r] ** 2;
    for (let k = c.cellOffsets[r]; k < c.cellOffsets[r + 1]; k += 1) {
      group[k] = rowGroup[r];
      const f = cutCells ? c.cellArea?.[k] : undefined;  // covered fraction; NaN = not sent
      weight[k] = Number.isNaN(values[k]) ? 0 : f !== undefined && Number.isFinite(f) ? f * g2 : g2;
    }
  }
  // Sort valid cells by (group, value); then one walk gives every statistic.
  const order = Uint32Array.from({ length: cells }, (_, k) => k).filter((k) => weight[k] > 0);
  order.sort((a, b) => group[a] - group[b] || values[a] - values[b]);
  const out: GroupStats[] = [];
  for (let i = 0; i < order.length;) {
    const g = group[order[i]];
    let j = i, area = 0, sum = 0;
    while (j < order.length && group[order[j]] === g) { area += weight[order[j]]; sum += weight[order[j]] * values[order[j]]; j += 1; }
    let acc = 0, p90 = values[order[j - 1]];
    for (let q = i; q < j; q += 1) { acc += weight[order[q]]; if (acc >= 0.9 * area) { p90 = values[order[q]]; break; } }
    out.push({ id: ids[g], area, mean: sum / area, min: values[order[i]], max: values[order[j - 1]], p90 });
    i = j;
  }
  return out;
}

// ---- 4. Export ----
/** CSV with a header row from the object keys. Quotes text that holds a comma or quote. */
export function toCsv(rows: readonly object[]): string {
  if (rows.length === 0) return "";
  const cell = (x: unknown) => {
    const s = typeof x === "number" ? (Number.isNaN(x) ? "" : String(+x.toFixed(3))) : String(x);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const keys = Object.keys(rows[0]);
  return [keys.join(","), ...rows.map((r) => keys.map((k) => cell((r as Record<string, unknown>)[k])).join(","))].join("\n");
}

/** JSON with NaN as null (JSON has no NaN). */
export const toJson = (rows: readonly object[]) =>
  JSON.stringify(rows, (_, x) => (typeof x === "number" && Number.isNaN(x) ? null : x));

/** Browser download of a text file. */
export function download(name: string, text: string, type = "text/csv"): void {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  a.click();
  URL.revokeObjectURL(a.href);
}
