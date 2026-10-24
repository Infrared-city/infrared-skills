# deck.gl: ground, terrain and trees from the same folder

Add these layers to the page of [deckgl-tiles](deckgl-tiles.md): same `manifest`, same `Deck`. Shared code (`groundOf`, `valueAt`):
[tiles-folder](tiles-folder.md). Make the layers with `TileExport(terrain=, trees=)` or `export_tiles(..., terrain=, trees=)`.
Tested with deck.gl 9.3.4, loaders.gl 4.4.3 and pmtiles 3.2.1 on synthetic data. A layer exists only when the export wrote it.

## 1. Ground (2D PMTiles)

Colour tiles need `ground_files=("colour",)` at export. Make one `TileLayer` per overview chunk and one per part (parts last, drawn above).

```html
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
```

```js
const g = groundOf(analysis);                     // null: no ground for this analysis (leave the layers out)
const groundLayerOf = (s, id) => {
  const colour = new pmtiles.PMTiles(s.files.colour);
  return new deck.TileLayer({
    id, tileSize: 512, minZoom: s.minzoom, maxZoom: s.maxzoom, extent: s.bounds,   // without these deck asks for tiles outside the archive
    getTileData: async ({ index: { x, y, z } }) => {                              // y from the NORTH, as PMTiles: no flip
      const t = await colour.getZxy(z, x, y);
      return t ? createImageBitmap(new Blob([t.data], { type: "image/png" })) : null;
    },
    renderSubLayers: (p) => {
      const [[west, south], [east, north]] = p.tile.boundingBox;
      return p.data && new deck.BitmapLayer(p, { data: null, image: p.data, bounds: [west, south, east, north],
        textureParameters: { minFilter: "nearest", magFilter: "nearest" } });
    },
  });
};
const groundLayers = [...g.overview.map((c) => groundLayerOf(c, `overview-${c.name}`)),
                      ...g.parts.map((p) => groundLayerOf(p, `part-${p.key}`))];
```

Draw the legend from `g.legend`. A ground is its own analysis id: build the layers for the analysis the user picked, or leave them out.
**Click value:** `onClick: async (info) => ...` with `info.coordinate` = `[lon, lat]`; pick the source (`ground.merged`, else part, else chunk)
and call `valueAt` ([tiles-folder](tiles-folder.md)), as in [cesium-tiles-layers](cesium-tiles-layers.md) (`sourceAt`). Tested: 8 clicks, largest error 0.046.

## 2. Terrain (TerrainLayer, terrain-RGB)

`manifest.terrain.rgb` is a `{z}/{x}/{y}.png` TEMPLATE. Join strings; `new URL(...)` escapes the braces. Height = -10000 + (R*65536 + G*256 + B) * 0.1.

```js
const root = manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
const terrain = new deck.TerrainLayer({
  id: "terrain", elevationData: root + manifest.terrain.rgb,
  elevationDecoder: { rScaler: 6553.6, gScaler: 25.6, bScaler: 0.1, offset: -10000 },
  tileSize: 256, minZoom: manifest.terrain.minzoom, maxZoom: manifest.terrain.maxzoom, extent: manifest.terrain.bounds,
  meshMaxError: 0.1, color: [150, 140, 120],
});   // layers: [terrain, facadesTile3DLayer]
```

A flat plane around the site is normal: the terrain covers the run mesh box and `TerrainLayer` draws whole tiles. Keep the worker on
(`worker: false` fails: "no parser found"); it loads from a CDN. Do not use a depth pick as a height source (errors up to 1.2 m).

## 3. Trees (i3dm tileset)

```js
const trees = new deck.Tile3DLayer({ id: "trees", data: new URL(manifest.trees.tileset, manifestUrl).href,
  loader: loaders.Tiles3DLoader, pickable: true, loadOptions: { "3d-tiles": { loadGLTF: true } } });
```

100 instances load; the property `height` reads. Tree picking is not proven. For a block loop, `manifest.trees.tileset` is one tileset: one `Tile3DLayer`.

## Silent traps

- `TerrainLayer` with `worker: false` fails.
- `manifest.terrain.rgb` is a template: join strings.
- Ground value bytes: R is HIGH. Facade value bytes: R is LOW.
