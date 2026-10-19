# deck.gl: ground, terrain and trees from the same folder

Add these layers to the facade page of [deckgl-tiles](deckgl-tiles.md). Same `manifest`, same `Deck`.
Tested with deck.gl 9.3.4, loaders.gl 4.4.3 and pmtiles 3.2.1 in a headless Chromium (SwiftShader) on synthetic data.
Each layer exists only when the export wrote it. Check the manifest before you build it.
For the Python calls that write the layers (`TileExport(terrain=, trees=)`, `export_ground_tiles`, `export_terrain_tiles`, `export_trees`), see [cesium-tiles-layers](cesium-tiles-layers.md) (same folder, same calls).

## 1. Ground layer (2D PMTiles)

`analyses/<id>/analysis.json` has a `ground` object: `files` (`value`, `colour`, `cog`: paths from the folder root),
`minzoom`, `maxzoom`, `bounds` (`[west, south, east, north]`), `encoding`, `lo`, `step`.
`files.colour` and `files.value` are 512 px PNG tiles in Web Mercator. The key names of `files` are from the export
code. For a block run the root files are an overview; `ground.parts[]` lists the full-resolution files of each block.

```html
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
```

```js
const g = (await (await fetch(new URL(`analyses/${id}/analysis.json`, manifestUrl))).json()).ground;
const colour = new pmtiles.PMTiles(new URL(g.files.colour, manifestUrl).href);
const value = new pmtiles.PMTiles(new URL(g.files.value, manifestUrl).href);

const ground = new deck.TileLayer({
  id: "ground", tileSize: 512, minZoom: g.minzoom, maxZoom: g.maxzoom, extent: g.bounds,
  // deck tile y counts from the NORTH, the same as PMTiles getZxy(z, x, y). No flip.
  getTileData: async ({ index: { x, y, z } }) => {
    const t = await colour.getZxy(z, x, y);
    return t ? createImageBitmap(new Blob([t.data], { type: "image/png" })) : null;
  },
  renderSubLayers: (p) => {
    const [[west, south], [east, north]] = p.tile.boundingBox; // an array in 9.3.4 (the spike read p.tile.bbox)
    return p.data && new deck.BitmapLayer(p, { data: null, image: p.data, bounds: [west, south, east, north],
      textureParameters: { minFilter: "nearest", magFilter: "nearest" } });
  },
  onClick: async (info) => info.coordinate && console.log(await valueAt(...info.coordinate)), // [lon, lat]
});
```

Set `minZoom`, `maxZoom` and `extent` from `ground`. Without them deck.gl asks for tiles outside the archive.
The spike passed with `p.tile.bbox.west` and so on; the `boundingBox` array form comes from the facade page test.

**Click value.** Use the NEAREST pixel of the `value.pmtiles` tile at `g.maxzoom`:

| Item | Value |
|---|---|
| Value | `g.lo + g.step * (R * 256 + G)` (R is the HIGH byte) |
| No data | alpha `0` |

```js
async function valueAt(lon, lat, size = 512) {
  const m = 2 ** g.maxzoom, fx = (lon + 180) / 360 * m, fy = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * m;
  const x = Math.floor(fx), y = Math.floor(fy), t = await value.getZxy(g.maxzoom, x, y);
  if (!t) return null;
  const bmp = await createImageBitmap(new Blob([t.data], { type: "image/png" }), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
  const cx = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d", { willReadFrequently: true });
  cx.drawImage(bmp, 0, 0);
  const [r, gr, , a] = cx.getImageData(Math.floor((fx - x) * size), Math.floor((fy - y) * size), 1, 1).data;
  return a === 0 ? null : g.lo + g.step * (r * 256 + gr);
}
```

Tested: 8 real mouse clicks, largest error 0.046 (limit 0.0501 = step / 2). Cache decoded tiles in a real app.
The facade value decoder has the opposite byte order (R is LOW). Do not copy one to the other.

## 2. Terrain (TerrainLayer, terrain-RGB)

Use manifest `terrain`: `terrain.rgb` (the path TEMPLATE of the terrain-RGB PNG pyramid, 256 px, XYZ: `terrain/rgb/{z}/{x}/{y}.png`),
`terrain.minzoom`, `terrain.maxzoom`, `terrain.bounds`. The code is Mapbox: height = -10000 + (R * 65536 + G * 256 + B) * 0.1.
Use the ellipsoidal base of the run, the same as the facades.

```js
// Do not pass the template through `new URL`: it escapes the braces. Join the strings.
const root = manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
const terrain = new deck.TerrainLayer({
  id: "terrain", elevationData: root + manifest.terrain.rgb, // a {z}/{x}/{y}.png template
  elevationDecoder: { rScaler: 6553.6, gScaler: 25.6, bScaler: 0.1, offset: -10000 },
  tileSize: 256, minZoom: manifest.terrain.minzoom, maxZoom: manifest.terrain.maxzoom, extent: manifest.terrain.bounds,
  meshMaxError: 0.1, color: [150, 140, 120],
});
// layers: [terrain, facadesTile3DLayer]
```

Tested (synthetic terrain): 5 hill points, terrain vs source at most 0.050 m (limit 0.5 m); 5 building bases vs
terrain at most 0.020 m. The spike read `{z}/{x}/{y}` with a path in the page folder; the use of `manifest.terrain.rgb` as the template is
not run in a browser (the export code stores a template).

- **The worker loads from a CDN.** `TerrainLayer` needs its worker loader. With `loadOptions: { worker: false }`
  it fails with "terrain loader - no parser found and worker is disabled". The worker comes from unpkg, so the page
  needs access to it. Do not turn the worker off.
- The mesh vertices are float32 in Web Mercator common space. Horizontal step is about 2.2 m at this latitude.
  Heights are not affected; on steep terrain a height can move by slope x 1 m.
- A depth pick (`pickObject({ unproject3D: true })`) on the terrain gave errors up to 1.2 m on the hill and one miss.
  Do not use it as a height source.

## 3. Trees (i3dm tileset)

Manifest `trees.tileset` is the path of `trees/<key>/tileset.json`; `trees.count` is the number of trees. It loads like the
facade tileset, through `Tile3DLayer`:

```js
const trees = new deck.Tile3DLayer({
  id: "trees", data: new URL(manifest.trees.tileset, manifestUrl).href, loader: loaders.Tiles3DLoader, pickable: true,
  loadOptions: { "3d-tiles": { loadGLTF: true } },
});
```

Tested on a spike tileset of 100 trees: 100 instances load, the batch property `height` reads (`height[5]` was 11),
and the instance matrices that deck draws with put base, apex and crown edge at the expected points (errors under
6 mm). No console error. Not proven: picking of the trees. `pickObject` found no tree after a view change.
The trees from `export_trees` or `TileExport(trees=...)` are not run in a browser.

## Silent traps

- `TerrainLayer` with `worker: false`: fails. The worker comes from a CDN.
- Ground value bytes: R is HIGH. Facade value bytes: R is LOW.
- Ground `value.pmtiles`: NEAREST pixel only.
- Terrain and facades need the same base height (`h0_orthometric_m`).
- `manifest.terrain.rgb` is a `{z}/{x}/{y}` template. `new URL(...)` escapes the braces; join the strings.
