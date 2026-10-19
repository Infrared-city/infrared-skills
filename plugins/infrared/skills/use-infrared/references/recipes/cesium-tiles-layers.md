# CesiumJS: ground, terrain and trees from the same folder

Add these layers to the facade page of [cesium-tiles](cesium-tiles.md). Same page, same `viewer`, same `manifest`.
Tested with CesiumJS 1.146.0 and pmtiles 3.2.1 in a headless Chromium (SwiftShader) on synthetic data. All 12 spike checks passed.
Each layer exists only when the export wrote it. Check the manifest before you build it.

## Make the layers (Python)

The easy way is one run. `TileExport` writes the facades, the ground, the terrain and the trees:

```python
from infrared_sdk import TileExport

export = TileExport(
    "out/",
    ids={0: "svf", 1: "svf_ground"},        # a facade payload and a ground payload of one type: key by index
    terrain=payload.ground_geometry,        # terrain/*, one for each folder
    trees=vegetation,                       # trees/<key>/*
    h0_orthometric_m=0.0,                   # one base height for all parts
)
client.run_area_and_wait([facade_payload, ground_payload], polygon, buildings=buildings,
                         vegetation=vegetation, export=export)
```

For results you already hold, call the parts one by one with the same `h0_orthometric_m`:

```python
from infrared_sdk import export_ground_tiles, export_terrain_tiles, export_trees

export_ground_tiles(area_result, "out/", "svf_ground")                           # analyses/svf_ground/ground/*
export_terrain_tiles(payload.ground_geometry, "out/", site_origin=(lon, lat))    # terrain/*
export_trees(vegetation, "out/", site_origin=(lon, lat), terrain=payload.ground_geometry)  # trees/<key>/*
```

`site_origin` is the south-west corner of the bounding box of the run polygon: `(min lon, min lat)` of its ring.
`TileExport` takes it from the run. A wrong value moves the terrain by metres with no error.
Ground and facades of one run are two ids (for example `svf` and `svf_ground`).
Each layer exists only when you exported it. A block run (`area_blocks`) writes one ground overview at the root of the
analysis (low zoom levels over all blocks, no COG). `ground.parts[]` in `analysis.json` lists the full-resolution
files of each block, each with its `key`.

## 1. Ground layer (2D PMTiles as imagery)

`analyses/<id>/analysis.json` has a `ground` object: `files` (`value`, `colour`, `cog`: paths from the folder root),
`kind`, `minzoom`, `maxzoom`, `bounds` (`[west, south, east, north]`), `encoding`, `lo`, `step`, `stats`, `legend`.
`files.colour` (display) and `files.value` (numbers) are 512 px PNG tiles in Web Mercator. PMTiles needs HTTP Range
requests, so use the `pmtiles` library. The key names of `files` are from the export code; the viewer code below is
the spike code, not run again on a final export.

```html
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
```

```js
const g = (await (await fetch(new URL(`analyses/${id}/analysis.json`, manifestUrl))).json()).ground;
const colour = new pmtiles.PMTiles(new URL(g.files.colour, manifestUrl).href);
const value = new pmtiles.PMTiles(new URL(g.files.value, manifestUrl).href);
const empty = Object.assign(document.createElement("canvas"), { width: 1, height: 1 });
const prov = new Cesium.UrlTemplateImageryProvider({
  url: "pmtiles://{z}/{x}/{y}", tilingScheme: new Cesium.WebMercatorTilingScheme(), tileWidth: 512, tileHeight: 512,
  minimumLevel: g.minzoom, maximumLevel: g.maxzoom, rectangle: Cesium.Rectangle.fromDegrees(...g.bounds),
});
prov.requestImage = async (x, y, z) => { // a custom provider; z, x, y as PMTiles getZxy
  const t = await colour.getZxy(z, x, y);
  return t ? createImageBitmap(new Blob([t.data], { type: "image/png" })) : empty;
};
viewer.imageryLayers.addImageryProvider(prov);
```

This is the tested spike code. Tested without terrain on the globe only in the ground part; with terrain on, an earlier
project note says to return a canvas drawn from the bitmap, not the `ImageBitmap` (gaps in 1.146). Untested here.

**Click value.** Take the tile at `g.maxzoom`, the pixel that holds the point (NEAREST), no interpolation:

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
new Cesium.ScreenSpaceEventHandler(viewer.canvas).setInputAction(async (m) => {
  const hit = viewer.scene.globe.pick(viewer.camera.getPickRay(m.position), viewer.scene);
  if (!hit) return;
  const c = Cesium.Cartographic.fromCartesian(hit);
  console.log(await valueAt(Cesium.Math.toDegrees(c.longitude), Cesium.Math.toDegrees(c.latitude)));
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
```

Tested: 8 real mouse clicks, largest error 0.046 (limit 0.0501 = step / 2). The facade value decoder has the
opposite byte order (R is LOW). Do not copy one decoder to the other.

## 2. Terrain

Use manifest `terrain` (the folder has one terrain). `terrain.cesium` is the path of `layer.json` (`terrain/layer.json`)
of the `heightmap-1.0` pyramid, which has the tiles `{z}/{x}/{y}.terrain` beside it. `fromUrl` wants the FOLDER of
`layer.json`, so cut the file name off:

```js
const layerUrl = new URL(manifest.terrain.cesium, manifestUrl).href;
viewer.terrainProvider = await Cesium.CesiumTerrainProvider.fromUrl(new URL(".", layerUrl).href);
viewer.scene.globe.depthTestAgainstTerrain = true;
const facades = await Cesium.Cesium3DTileset.fromUrl(facadeUrl); // as in the facade recipe
viewer.scene.primitives.add(facades);
```

Tested (synthetic terrain): 5 hill points, terrain vs source model at most 0.064 m (limit 0.5 m); 5 building bases vs
terrain at most 0.080 m (the `heightmap-1.0` step is 0.2 m). Read heights with `Cesium.sampleTerrainMostDetailed`.
Serve `.terrain` as `application/octet-stream` with no `Content-Encoding`. The spike path was a bare `terrain/`
folder; the cut of `manifest.terrain.cesium` to its folder is not run in a browser.

## 3. Trees (i3dm tileset)

Manifest `trees.tileset` is the path of `trees/<key>/tileset.json`; `trees.count` is the number of trees. It loads like the
facade tileset:

```js
const trees = await Cesium.Cesium3DTileset.fromUrl(new URL(manifest.trees.tileset, manifestUrl).href);
viewer.scene.primitives.add(trees);
```

Tested on a spike tileset of 100 trees: all 100 instances load (`content.featuresLength`), the batch property
`height` reads (`getFeature(5).getProperty("height")` was 11), and picks on a tree axis and above its apex fit
position, up axis and scale. No console error. The trees from `export_trees` or `TileExport(trees=...)` are not run in a browser.

## Silent traps

- Ground value bytes: R is HIGH. Facade value bytes: R is LOW.
- Ground `value.pmtiles`: NEAREST pixel only, no premultiply, no colour conversion.
- Terrain and facades need the same base height (`h0_orthometric_m`). Another base: buildings float or sink.
- The folder has one terrain. Another terrain, or another base, is refused by the SDK.
- `manifest.terrain.cesium` is the path of `layer.json`; `CesiumTerrainProvider.fromUrl` wants its folder.
