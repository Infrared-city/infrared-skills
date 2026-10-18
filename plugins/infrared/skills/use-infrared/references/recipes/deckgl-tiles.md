# deck.gl: Infrared tiles in your own app

Infrared gives you the data as standard tiles. This recipe is the last step: show the tiles in your deck.gl app.
Tested with deck.gl 9.3.4 and loaders.gl 4.4.3. The export needs the SDK release that adds `export_3d_tiles`.
For CesiumJS, see [cesium-tiles](cesium-tiles.md).

## 1. Make the folder (Python)

```python
from infrared_sdk import export_3d_tiles

export_3d_tiles(result, "out/", "svf", schedule=schedule)  # result: a facade or roof result
```

The folder holds `manifest.json` (`analyses[]` with `facades.tileset`, `legend`, `stats`, `height`, `value`),
`g/<sha256>.bin` (shared geometry) and `analyses/<id>/facades/tileset.json` with the GLB tiles.
Serve it from any static host (see the last section).

## Read `analysis.json` (what the UI needs)

Every analysis has `analyses/<id>/analysis.json`. The same entry is in `manifest.json` (`analyses[]`). Read these fields:

| Field | Use |
|---|---|
| `id`, `label`, `units` | The switcher text and the unit after a value |
| `facades.tileset` | Path to the tileset, relative to the manifest |
| `facades.legend.vmin`, `vmax` | The value range of the whole analysis (not of the view) |
| `facades.legend.config` | `colors` (stops, 0 to 255), `unit`, `info`, `colorInterpolation`, `legendType`, `legendMinHandling`, `legendMaxHandling` |
| `facades.value` | `offset`, `scale`, `noData` (65535) for the click decoder |
| `facades.stats` | `mean`, `p10`, `p50`, `p90`, `histogram` (20 bins) |
| `facades.height` | The base height of the run |

Legend format: `legendType: "equal_ranges"` splits `vmin..vmax` in equal steps. `colorInterpolation: "binned"` gives
one flat colour to each step (no blend between stops). `legendMinHandling` and `legendMaxHandling` are `closed`:
a value equal to `vmin` or `vmax` stays in the first or last step. Draw a legend from these fields; do not guess the steps.

No-data rule: a cell with no value has code `65535` and alpha `0` in the value page. Show it as "no value" and keep it
out of your own statistics.

## 2. 3D tiles with Tile3DLayer

**Use these exact versions.** deck.gl 9.1 with loaders.gl 4.3 fails on these tiles.
If you use npm, install the same pair: `deck.gl@9.3.4` and `@loaders.gl/3d-tiles@4.4.3`.

```html
<script src="https://unpkg.com/deck.gl@9.3.4/dist.min.js"></script>
<script src="https://unpkg.com/@loaders.gl/3d-tiles@4.4.3/dist/dist.min.js"></script>
```

```js
const url = new URL(analysis.facades.tileset, manifestUrl).href; // analysis: one entry of manifest.json
const d = new deck.Deck({
  initialViewState: { longitude: 114.17, latitude: 22.3, zoom: 15 }, controller: true,
  layers: [new deck.Tile3DLayer({
    id: "infrared", data: url, loader: loaders.Tiles3DLoader,
    loadOptions: {
      "3d-tiles": { loadGLTF: true },
      tileset: { maximumScreenSpaceError: 0 },
      gltf: { excludeExtensions: { EXT_structural_metadata: false } },
    },
    onTilesetLoad: (ts) => d.setProps({ initialViewState: {
      longitude: ts.cartographicCenter[0], latitude: ts.cartographicCenter[1], zoom: 14.6, pitch: 50 } }),
  })],
});
```

**The `excludeExtensions` flag must be `false`.** With `true` the tab freezes. This is the result of the test.
The reason is not known. Do not change it.

Load `tileset.json` only. The deck.gl loader does not read `.gltf` tiles. The export uses GLB.
Tested: every tile loaded and the console showed no error. The default look is the baked colour page.

Not yet covered, because no test ran:
- Your own palette on the 3D tiles. `Tile3DLayer` has no `CustomShader`. Show the baked colour for now.
- Terrain from the export. deck.gl `TerrainLayer` reads other formats than the export (`heightmap-1.0`).

### Click to value on the 3D tiles

`Tile3DLayer` has no metadata pick. Decode the value from the GLB of the clicked tile. This is the method of the
Cesium recipe, with the same decoder:

1. Pick: `info.object` is the clicked `Tile3D`; `info.coordinate` is `[lon, lat, alt]`. The tile GLB url is
   `info.object.contentUrl` (check the field name in your loaders.gl 4.4.3 console).
2. Move the point into the tile frame. The tileset root `transform` is ENU to ECEF and each GLB has a node
   translation. Take the ECEF point of the click, apply the inverse of `tileset.transform * tile.transform`,
   then change axes: tile frame (z up) to glTF (y up) is `(x, y, z) -> (x, z, -y)`.
3. Fetch the GLB and its `g/<sha256>.bin` buffer (cache both). Read `POSITION`, `TEXCOORD_0` and the value PNG.
4. Find the triangle at the point, get its uv, read the nearest texel with data.
5. Decode: code `= R + 256 * G` (R is the LOW byte); value `= offset + scale * code / 65535`, with `offset` and
   `scale` from `analysis.facades.value`. No data: code `65535` or alpha `0`.
6. Decode the PNG with `premultiplyAlpha: "none"` and `colorSpaceConversion: "none"`.

Use `readGlb`, `decodeValues` and `lookup` from section 4 of [cesium-tiles](cesium-tiles.md) unchanged. They do not
need Cesium. Only steps 1 and 2 are deck.gl specific:

```js
// ecef(lon, lat, alt) -> ECEF metres (WGS84); tileWorld = tileset.transform * tile.transform (4x4)
const l = applyMatrix(invert(tileWorld), ecef(...info.coordinate)); // point in the tile frame (z up)
const value = lookup(await readGlbCached(info.object.contentUrl), l[0], l[2], -l[1]);
console.log(value === null ? "no value here" : `${value} ${analysis.units}`);
```

Not tested in deck.gl: the `contentUrl` field and the matrix chain. The decoder is the tested one (about 45 clicks
inside one codec step). If the chain is wrong, `lookup` returns `null` for every click (no triangle within 2 m).
Check a few values against `analysis.facades.stats` (`p10` to `p90`).

## 3. Base height

The tiles carry `extras.height` (`root.extras.height` of the tileset). The base height is the EGM2008 geoid
height N plus `h0`. For Hong Kong N is about -2.3 m. The tiles stand at ellipsoidal height. A basemap with no terrain
shows them at that base height. Use the DTM of the same run for terrain, not a provider DEM:
the datum and the resolution of a provider DEM differ, and buildings float or sink.
Not tested with a viewer: the fit on a deck.gl basemap.

## 4. Ground layers (2D PMTiles)

Ground layers exist only when the export wrote them. A 3D-only folder has no ground manifest and no PMTiles.
Check that the file exists before you build this layer.

A ground layer is two PMTiles archives: `colour.pmtiles` (display) and `value.pmtiles` (numbers).
Both are 512 px PNG tiles in Web Mercator. Read them with the `pmtiles` library (HTTP Range requests).

```html
<script src="https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js"></script>
```

```js
// m: one layer of the ground manifest (minzoom, maxzoom, bounds, encoding, lo, step, file, colour_file)
const colour = new pmtiles.PMTiles(new URL(m.colour_file, dataBase).href);
const value = new pmtiles.PMTiles(new URL(m.file, dataBase).href);

const layer = new deck.TileLayer({
  id: "ground", tileSize: 512, minZoom: m.minzoom, maxZoom: m.maxzoom, extent: m.bounds,
  // deck tile index {x, y, z}: y counts from the NORTH, the same as PMTiles getZxy(z, x, y). No flip.
  getTileData: async ({ index: { x, y, z }, signal }) => {
    const r = await colour.getZxy(z, x, y, signal);
    return r ? createImageBitmap(new Blob([r.data], { type: "image/png" })) : null;
  },
  renderSubLayers: (p) => {
    const [[west, south], [east, north]] = p.tile.boundingBox; // an array in 9.3.4, not an object
    return p.data ? new deck.BitmapLayer(p, { data: null, image: p.data, bounds: [west, south, east, north],
      textureParameters: { minFilter: "nearest", magFilter: "nearest" } }) : null;
  },
  onClick: async (info) => console.log(await valueAt(info.coordinate)), // [lon, lat]
});
```

Set `minZoom`, `maxZoom` and `extent` from the manifest. Without them deck.gl asks for tiles outside the archive.

Click to value: read the `value.pmtiles` tile at the maximum zoom. Decode without premultiply or colour conversion,
and take the NEAREST pixel.

| Item | Value |
|---|---|
| Value | `lo + step * (R * 256 + G)` (R is the HIGH byte) |
| No data | alpha `0` |
| Sampling | NEAREST. Never interpolate value tiles |

```js
const cache = new Map();
function pixels(x, y) {
  const key = `${x}/${y}`;
  if (!cache.has(key)) cache.set(key, (async () => {
    const r = await value.getZxy(m.maxzoom, x, y);
    if (!r) return null;
    const bmp = await createImageBitmap(new Blob([r.data], { type: "image/png" }), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
    const g = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d", { willReadFrequently: true });
    g.drawImage(bmp, 0, 0);
    return { w: bmp.width, d: g.getImageData(0, 0, bmp.width, bmp.height).data };
  })());
  return cache.get(key);
}
async function valueAt([lon, lat]) {
  const n = 2 ** m.maxzoom, fx = (lon + 180) / 360 * n, fy = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n;
  const x = Math.floor(fx), y = Math.floor(fy), t = await pixels(x, y);
  if (!t) return null;
  const px = Math.min(t.w - 1, Math.floor((fx - x) * t.w)), py = Math.min(t.w - 1, Math.floor((fy - y) * t.w)), i = (py * t.w + px) * 4;
  if (t.d[i + 3] === 0) return null;                 // no data
  return m.lo + m.step * (t.d[i] * 256 + t.d[i + 1]);
}
```

Tested: 20 of 20 clicks inside the codec error, 2 of 2 no-data clicks returned null, with data on the same origin and on
another origin.

The byte order of the 3D tiles is the opposite (R is the LOW byte: `offset + scale * (R + 256 * G) / 65535`).
Do not copy one decoder to the other.

## 5. Hosting

- `_headers` works on Cloudflare Pages (put the folder in the deploy root).
- R2 and S3 do not read `_headers`. Set these by hand:
  - CORS: allow `GET` and `HEAD` from your page origin, allow the header `Range`, expose `ETag`.
  - `Content-Type`: `.glb` `model/gltf-binary`; `.bin` and `.pmtiles` `application/octet-stream`.
  - `Cache-Control`: `manifest.json` `no-cache`; `g/` and `analyses/` `public, max-age=31536000, immutable`.
- Any other host must answer `206` with `Accept-Ranges: bytes` if you use PMTiles.
- The page must run on `http(s)`, not `file://`.

## Add an analysis later

See the SDK docs.

## Silent traps

- Wrong version pair (deck.gl 9.1 with loaders.gl 4.3): the tiles fail.
- `excludeExtensions: { EXT_structural_metadata: true }`: the tab freezes.
- `.gltf` tiles: not read. The export uses GLB.
- Interpolated sampling of value tiles: the numbers mean nothing. Use NEAREST.
- Tile y: deck.gl and PMTiles both count from the north. A flip puts tiles in the wrong place.
- `tile.boundingBox` is `[[west, south], [east, north]]`, not an object.
