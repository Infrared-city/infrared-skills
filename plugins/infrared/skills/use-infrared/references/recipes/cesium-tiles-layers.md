# CesiumJS: ground, terrain and trees from the same folder

Add these layers to the page of [cesium-tiles](cesium-tiles.md): same `viewer`, same `manifest`. Shared code (`groundOf`, `valueAt`):
[tiles-folder](tiles-folder.md). Make the layers with `TileExport(terrain=, trees=)` or `export_tiles(..., terrain=, trees=)`.
Tested with CesiumJS 1.146.0 and pmtiles 3.2.1 on synthetic data. A layer exists only when the export wrote it: check the manifest.

## 1. Ground (PMTiles imagery)

Colour tiles need `ground_colour=True` at export. The ground has overview chunks (low zooms over all blocks) and parts
(full resolution). Add one imagery layer per chunk, then one per part above them.

```html
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
```

```js
const g = groundOf(analysis);                     // null: no ground for this analysis (hide the layer)
const empty = Object.assign(document.createElement("canvas"), { width: 1, height: 1 });
// Return a decoded Image: Cesium 1.146 does not draw an ImageBitmap here, and a canvas premultiplies (dark part edges).
const tileImage = async (data) => { const u = URL.createObjectURL(new Blob([data], { type: "image/png" }));
  const img = new Image(); try { img.src = u; await img.decode(); } finally { URL.revokeObjectURL(u); } return img; };
const layerOf = (s) => {
  const colour = new pmtiles.PMTiles(s.files.colour);
  const p = new Cesium.UrlTemplateImageryProvider({ url: "pmtiles://{z}/{x}/{y}",
    tilingScheme: new Cesium.WebMercatorTilingScheme(), tileWidth: 512, tileHeight: 512,
    minimumLevel: s.minzoom, maximumLevel: s.maxzoom, rectangle: Cesium.Rectangle.fromDegrees(...s.bounds) });
  p.requestImage = async (x, y, level) => { const t = await colour.getZxy(level, x, y);   // PMTiles wants (z, x, y)
    return t ? tileImage(t.data) : empty; };
  return viewer.imageryLayers.addImageryProvider(p);
};
const groundLayers = [...g.overview, ...g.parts].map(layerOf);   // an area of one block has one part and one chunk
```

Draw the legend from `g.legend` (`vmin`, `vmax`, `config`). A ground is its own analysis id: when the user picks another analysis, remove the
layers and build the new ground, or hide them when it has none.

**Click value.** Pick the globe point, then read the value archive with `valueAt` ([tiles-folder](tiles-folder.md)).
For a city read `ground.merged` (a part can have no data where the merged archive has a value); else the part whose `bounds` hold the point, else the chunk. Each source has its own `lo`, `step`, `encoding`.

```js
const sourceAt = (lon, lat) => { const inside = (l) => l.find(({ bounds: [w, s, e, n] }) => lon >= w && lon <= e && lat >= s && lat <= n);
  return g.merged ?? inside(g.parts) ?? inside(g.overview) ?? g; };
new Cesium.ScreenSpaceEventHandler(viewer.canvas).setInputAction(async (m) => {
  const hit = viewer.scene.globe.pick(viewer.camera.getPickRay(m.position), viewer.scene);
  if (!hit) return;
  const c = Cesium.Cartographic.fromCartesian(hit), lon = Cesium.Math.toDegrees(c.longitude), lat = Cesium.Math.toDegrees(c.latitude);
  const s = sourceAt(lon, lat);
  console.log(await valueAt(new pmtiles.PMTiles(s.files.value), s, lon, lat));
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
```

Cache the `PMTiles` objects. Tested: 8 clicks, largest error 0.046 (limit step / 2).

## 2. Terrain

Use `manifest.terrain` (one terrain per folder). `terrain.cesium` is the path of `layer.json`; `fromUrl` wants its FOLDER.

```js
const layerUrl = new URL(manifest.terrain.cesium, manifestUrl).href;
viewer.terrainProvider = await Cesium.CesiumTerrainProvider.fromUrl(new URL(".", layerUrl).href);
viewer.scene.globe.depthTestAgainstTerrain = true;
```

The terrain covers the box of the run mesh only; outside it the terrain is flat at the base height. That flat area is normal.
Tested (synthetic): terrain vs source at most 0.064 m; building bases vs terrain at most 0.080 m.

## 3. Trees (i3dm tileset)

```js
const trees = await Cesium.Cesium3DTileset.fromUrl(new URL(manifest.trees.tileset, manifestUrl).href);
viewer.scene.primitives.add(trees);       // properties: height, crown_diameter, genus
```

For a block loop give `TileExport(trees=)` the trees of the whole area: `manifest.trees.tileset` is then one tileset.

## Silent traps

- Ground value bytes: R is HIGH. Facade value bytes: R is LOW.
- `manifest.terrain.cesium` is `layer.json`; `CesiumTerrainProvider.fromUrl` wants its folder.
- The root `ground` has no `files`: use `groundOf`.
