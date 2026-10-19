# deck.gl: ground, terrain and trees from the same folder

Add these layers to the facade page of [deckgl-tiles](deckgl-tiles.md). Same `manifest`, same `Deck`.
Tested with deck.gl 9.3.4, loaders.gl 4.4.3 and pmtiles 3.2.1 in a headless Chromium (SwiftShader) on synthetic data.
Each layer exists only when the export wrote it. Check the manifest before you build it.
For the Python calls that write the layers (`TileExport(terrain=, trees=)`, `export_tiles(result, ..., terrain=, trees=)`), see [cesium-tiles-layers](cesium-tiles-layers.md) (same folder, same calls).

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

**The ground follows the selected analysis.** A ground is its own analysis id (`svf_ground`), with its own
`ground.legend`; a facade analysis (`svf`) has no `ground`. When the user selects an analysis, build the ground layer
from the ground that belongs to it, and set `visible: false` (or leave the layer out) when there is none, or the page
shows the ground of another analysis under the new facades. The manifest has no link from a facade id to a ground
id: name them so that your app can pair them (for example `<id>` and `<id>_ground`). Draw the ground legend from
`ground.legend` (`vmin`, `vmax`, `config`): the colour tiles are painted with it.
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

**A block analysis (a block loop): the overview chunks and one layer per block.** The root `ground` has no `files`:
`ground.overview[]` is the overview (low zooms over all blocks) in chunks of the area, about 8 km on a side, and
`ground.parts[]` has the full-resolution `ground` object of each block (`key`, `files`, `minzoom`, `maxzoom`,
`bounds`, `lo`, `step`). Make one `TileLayer` as above for each chunk and one for each part, the parts last (drawn
above), each with its own `minZoom`, `maxZoom` and `extent`, and read a click from the part whose `bounds` hold the
point, else the chunk. Each chunk and each block has its own value codec (`lo`, `step`); the colours use one range for the whole analysis:

```js
// groundLayerOf(s, id): the TileLayer above as a function of its source s (s in place of g) and its layer id.
const sources = [...(g.overview ?? [g]).map((c) => [c, `overview-${c.key ?? 0}`]), ...(g.parts ?? []).map((p) => [p, `part-${p.key}`])];
const groundLayers = sources.map(([s, id]) => groundLayerOf(s, id));
const inside = (list, lon, lat) => (list ?? []).find(({ bounds: [w, s, e, n] }) => lon >= w && lon <= e && lat >= s && lat <= n);
const sourceAt = (lon, lat) => inside(g.parts, lon, lat) ?? inside(g.overview, lon, lat) ?? g;
```

Tested (deck.gl 9.3.4, pmtiles 3.2.1, a synthetic export of 25 blocks: 4 overview chunks of maxzoom 12, blocks of
maxzoom 16): at zoom 16 over the centre of each block, the layer of that block loaded 6 tiles of zoom 16 (the other
blocks 0, the chunk under it 1 tile of zoom 12), 0 failed, and the value at the centre decoded from the block's value
tiles (the same value as in CesiumJS).

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

**A flat plane around the site is normal.** The terrain covers the box of the terrain mesh of the run, and the export
does not clip it to the site. `TerrainLayer` draws whole tiles, and a tile at `maxzoom` is larger than a small site
(zoom 14 is about 2.4 km wide at the equator). Outside the terrain box the tile is flat at the base height.
`extent` only limits which tiles load, not the mesh inside a tile. Test result: a 1 km synthetic hill showed a brown
flat plane of about 4.5 km around it (2 x 2 tiles of zoom 14).

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
The trees from `export_tiles(trees=...)` or `TileExport(trees=...)` are not run in a browser.

**Trees of a block loop.** Give the trees of the whole area to every block: the first block writes them, the later
blocks write nothing. `manifest.trees.tileset` is one tileset of the whole area: load it in ONE `Tile3DLayer` as above,
with a view that holds the area (tiles out of the view do not load).

## Silent traps

- `TerrainLayer` with `worker: false`: fails. The worker comes from a CDN.
- Ground value bytes: R is HIGH. Facade value bytes: R is LOW.
- Ground `value.pmtiles`: NEAREST pixel only.
- Terrain and facades need the same base height (`h0_orthometric_m`).
- `manifest.terrain.rgb` is a `{z}/{x}/{y}` template. `new URL(...)` escapes the braces; join the strings.
