# Map app: ground grid on MapLibre + deck.gl

Runnable app: [cookbook/apps/map-grid](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/map-grid)
(Vite + TypeScript, no framework). Copy it, then change the analysis and the area.
API detail: [Results and legend](https://infrared.city/docs/sdk/1.0/api/typescript/results-and-legend/),
[Tiling](https://infrared.city/docs/sdk/1.0/api/typescript/tiling/).

What it does: light basemap, draw a polygon (or a default one), job and token
preview, **Run**, the result as a `BitmapLayer`, a legend with units, progress text.

## Setup in the browser

```ts
import coreUrl from "@infrared-city/infrared-sdk-ts/core.wasm?url";   // Vite: WASM as a URL
import { InfraredClient, initializeCore } from "@infrared-city/infrared-sdk-ts";
import { relayUrl } from "./proxy";   // from cookbook/apps/cloudflare-proxy/src/proxy.ts

await initializeCore({ url: new URL(coreUrl, location.href) });       // once, before any SDK call
const client = new InfraredClient({
  baseUrl: `${location.origin}/api/ir`,  // your proxy adds the API key
  auth: async () => ({}),                // no credential in the browser
  fetch: (input, init) => fetch(input instanceof Request ? input : relayUrl(String(input)), init),
});
```

- The key stays in the proxy. In dev, the Vite server is the proxy (`vite.config.ts`
  in the app). In production, a Worker: [cloudflare-proxy.md](cloudflare-proxy.md).
- The custom `fetch` sends the presigned result download through the proxy relay.
  Without it the browser blocks the download (no CORS on the results bucket).
- Vite: `optimizeDeps.exclude: ["@infrared-city/infrared-sdk-ts"]` and `build.target: "es2022"`.

## Preview, then run

```ts
const polygon = { type: "Polygon", coordinates: [ring] };     // ring: [lon, lat][] , closed
const p = client.previewArea(polygon, { analysisType: "sky-view-factors" }); // free, local
status(`${p.tileCount} tile(s), about ${p.estimatedCostTokens} tokens`);     // show before Run

// On Run. Own meshes first; public buildings are the fallback.
const buildings = await client.buildings.getBuildingsInArea(polygon, { analysisType: "sky-view-factors" });
const result = (await client.runAreaAndWait({ analysisType: "sky-view-factors" }, polygon, {
  buildings,
  onProgress: (s) => status(`${s.completedCount} of ${s.totalCount} tiles done`),
})) as AreaResult;
```

`previewArea` throws over the 100-tile limit: show its message. It names the
`maxTilesOverride` that would run the area.

## Grid → image → BitmapLayer

```ts
const [rows, cols] = result.gridShape;
const values = areaGridValuesF32(result);               // real units, NaN = no value
const range = legendRange(result, "exact") ?? [0, 100]; // or "trimmed" (2nd to 98th percentile)
const image = ctx.createImageData(cols, rows);
for (let y = 0; y < rows; y += 1) {
  const src = rows - 1 - y;                              // row 0 is SOUTH: flip for north-up
  for (let x = 0; x < cols; x += 1) {
    const v = values[src * cols + x];
    if (Number.isNaN(v)) continue;                       // transparent (buildings, outside the area)
    image.data.set([...colour(v, range), 255], (y * cols + x) * 4);
  }
}
new BitmapLayer({
  id: "grid", image: canvas, opacity: 0.85,
  bounds: result.bounds as [number, number, number, number],     // [west, south, east, north]
  textureParameters: { minFilter: "nearest", magFilter: "nearest" },
});
```

- Use the flat `[w, s, e, n]` bounds. Do not pass four corners.
- Check alignment: the NaN holes must sit on the basemap's buildings.
- `colour` is your own ramp between the legend bounds (the app has a viridis
  table in `src/ramp.ts`). The SDK has no value-to-colour function.
- No canvas code? `await renderGridPng(grid2d, { analysisType, reverseRows: true })` gives a PNG
  (a `Uint8Array`) coloured with the Infrared registry; `grid2d` is `rows` arrays of `cols` values.
  `reverseRows: true` puts row 0 (south) at the bottom; no-data cells are transparent.
  Use `URL.createObjectURL(new Blob([png]))` as the layer `image`.

## Legend and units

Title with units, a gradient bar, min / mid / max. Units: SVF in %, solar radiation
in kWh/m² over the period, UTCI in °C, wind speed in m/s, sun hours in h.
Pedestrian wind comfort is classes: use `result.legend`, not a ramp. See
[grid-conventions.md](../interpretation/grid-conventions.md).

## Other analyses

Change `analysisType`. Wind models use a 256 m tile grid with overlap, so the same area
has more tiles: preview again.

Wind speed: always merge with the directional blend. The default merge crops each
tile at its centre and leaves visible seams in a wind field:

```ts
const input = { analysisType: "wind-speed", windSpeed: 5, windDirection: 270 } as const;
const schedule = await client.runArea(input, polygon, { buildings });
while (!(await client.checkAreaState(schedule)).isComplete) await new Promise((r) => setTimeout(r, 1000));
const result = await client.mergeAreaJobs(schedule, { strategy: "directional_blend", windDirectionDeg: input.windDirection });
```

`mergeAreaJobs` throws when a tile failed: you never get a map with holes. Weather analyses also need `weatherData`,
`latitude`, `longitude` and `dateFilters` (see [facades-3d.md](facades-3d.md)).
