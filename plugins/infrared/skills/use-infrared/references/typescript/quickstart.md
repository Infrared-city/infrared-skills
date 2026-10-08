# TypeScript quick start (Node)

Package: `@infrared-city/infrared-sdk-ts` 1.0.0, on the public npm registry.
API detail: [TypeScript reference](https://infrared.city/docs/sdk/1.0/api/typescript/).
Guide: [Quickstart](https://infrared.city/docs/sdk/1.0/#quickstart),
[What comes back](https://infrared.city/docs/sdk/1.0/#what-comes-back).

## Install

```bash
npm install @infrared-city/infrared-sdk-ts
npm install hyparquet hyparquet-compressors   # only to read public Overture buildings
npm install -D tsx
```

If a global `~/.npmrc` maps `@infrared-city` to another registry, add a local
`.npmrc` with `@infrared-city:registry=https://registry.npmjs.org`.

## The whole flow

Save as `quickstart.ts`, set `"type": "module"` in `package.json`, run
`INFRARED_API_KEY=... npx tsx quickstart.ts`.

```ts
import {
  InfraredClient, initializeCore, areaGridValuesF32, legendRange, type AreaResult,
} from "@infrared-city/infrared-sdk-ts";

// 1. Start the WASM core once per process (Node loads the packaged file).
await initializeCore();

// 2. One client per process. Keep the key on the server, never in a browser.
const client = new InfraredClient({ apiKey: process.env.INFRARED_API_KEY });

// 3. The area (GeoJSON, lon/lat) and your own buildings (metres, origin = SW corner of the area).
const lon = 16.371, lat = 48.208;
const polygon = { type: "Polygon" as const, coordinates: [[
  [lon, lat], [lon + 0.004, lat], [lon + 0.004, lat + 0.003], [lon, lat + 0.003], [lon, lat]] as [number, number][]] };
const xy = [[100, 100], [120, 100], [120, 120], [100, 120]];
const coordinates = [0, 30].flatMap((z) => xy.flatMap(([x, y]) => [x, y, z]));
const indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
                 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7];
const buildings = { tower: { coordinates, indices } };
// No model? Public data: const buildings = await client.buildings.getBuildingsInArea(polygon);

// 4. Preview: local, free. One tile = one billed job.
const preview = client.previewArea(polygon, { analysisType: "sky-view-factors" });
console.log(`${preview.tileCount} tile(s), about ${preview.estimatedCostTokens} tokens`);

// 5. Run: tiles, upload, submit, poll and merge in one call.
const result = (await client.runAreaAndWait({ analysisType: "sky-view-factors" }, polygon, {
  buildings,
  onProgress: (s) => console.log(`${s.completedCount}/${s.totalCount} tiles done`),
})) as AreaResult;

// 6. Read real values with the helper (never the raw mergedGrid). NaN = no value.
const values = areaGridValuesF32(result);
const [rows, cols] = result.gridShape;           // row 0 = SOUTH edge
console.log({ rows, cols, bounds: result.bounds, range: legendRange(result, "exact") });
const finite = values.filter((v) => !Number.isNaN(v));
console.log(`mean SVF ${(finite.reduce((a, b) => a + b, 0) / finite.length).toFixed(1)} %`);
```

Tested output (1 tile): `rows: 512, cols: 512`, `bounds` = the tile in degrees,
`range: [50.5, 100]`. The grid covers the tile; cells outside the polygon are NaN.

## Rules

- **`initializeCore()` first.** Node loads the packaged WASM. In a browser pass a URL
  (`initializeCore({ url })`), see [map-grid.md](map-grid.md).
- **Preview before every run.** `previewArea(polygon, { analysisType })` for a ground
  grid. For a facade or roof run use `await client.previewAreaBatches(input, polygon, { buildings })`
  (`plannedJobCount`, `sensorCount`): it bills per building batch, not per tile.
- **Use the helpers.** f16 grids hold half-float bits. `areaGridValuesF32(result)` and
  `surfaceValuesF32(columns)` give real values, NaN = no value.
- **Grid orientation.** `gridShape = [rows, cols]`, row 0 = south, `bounds = [w, s, e, n]`.
  Flip the rows for an image (north up).
- **Do not poll yourself.** `runAreaAndWait` batches status calls and backs off.
  For long runs: `runArea` (returns a schedule) + `checkAreaState` + `mergeAreaJobs`.
- **Own data first.** Pass your meshes as `buildings` (`{ id: { coordinates, indices } }`,
  flat arrays, metres, z up). Public `getBuildingsInArea(polygon)` is the fallback;
  pass the whole returned object, so the SDK can check its frame and read margin.
- **Weather analyses** (`solar-radiation`, `thermal-comfort-index`) take hours from
  `client.weather.filterWeatherData(stationUuid, { period })` as `weatherData`, plus
  `latitude`, `longitude` and `dateFilters: { period }`. See [facades-3d.md](facades-3d.md).
- `runAreaAndWait` returns `AreaResult | SurfaceColumns`: narrow it with `as`.

## Next

- Map app with a Run button: [map-grid.md](map-grid.md)
- Facades and roofs in three.js: [facades-3d.md](facades-3d.md)
- Production key handling: [cloudflare-proxy.md](cloudflare-proxy.md)
- Runnable apps: [cookbook/apps](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps)
