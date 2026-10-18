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
Terrain: see [deckgl-tiles-layers](deckgl-tiles-layers.md) (section 2). Not tested: the fit on a deck.gl basemap with no terrain.

## 4. Ground, terrain and trees

These layers are in [deckgl-tiles-layers](deckgl-tiles-layers.md): the ground layer with a click value, terrain from manifest `terrain`, and trees from manifest `trees.tileset`.

## 5. Hosting

- A bucket: pass `S3Target(client, bucket, prefix)` as the target (`client` is a boto3 S3 client; R2 and MinIO work too).
  It sets `ContentType` and `CacheControl` on each object. CORS is a bucket setting, not a key setting: set it yourself.
- `_headers` works on Cloudflare Pages (put the folder in the deploy root).
- R2 and S3 do not read `_headers`. `S3Target` sets the two header fields per object; the bucket CORS stays by hand:
  - CORS: allow `GET` and `HEAD` from your page origin, allow the header `Range`, expose `ETag`.
  - `Content-Type` (`S3Target` sets it): `.glb` `model/gltf-binary`; `.bin` and `.pmtiles` `application/octet-stream`.
  - `Cache-Control` (`S3Target` sets it): `manifest.json` `no-cache`; `g/` and `analyses/` `public, max-age=31536000, immutable`.
- Any other host must answer `206` with `Accept-Ranges: bytes` if you use PMTiles.
- The page must run on `http(s)`, not `file://`.

## Add an analysis later

No code change in the app. Export a new id into the same folder (or the same `S3Target`). The export rebuilds
`manifest.json`; the app reads it again and lists the new entry. `manifest.json` is `no-cache`, so a reload sees it.

```python
export_3d_tiles(result2, "out/", "utci", schedule=schedule)   # or: S3Target(client, bucket, prefix)
```

An id that exists is refused. The old `terrain` and `trees` entries stay in the manifest.

## Silent traps

- Wrong version pair (deck.gl 9.1 with loaders.gl 4.3): the tiles fail.
- `excludeExtensions: { EXT_structural_metadata: true }`: the tab freezes.
- `.gltf` tiles: not read. The export uses GLB.
- Interpolated sampling of value tiles: the numbers mean nothing. Use NEAREST.
- Tile y: deck.gl and PMTiles both count from the north. A flip puts tiles in the wrong place.
- `tile.boundingBox` is `[[west, south], [east, north]]`, not an object.
