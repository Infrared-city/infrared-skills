# deck.gl: Infrared tiles in your own app

Infrared gives you the data as standard tiles. This recipe is the last step: show the tiles in your deck.gl app.
Put `<link rel="icon" href="data:,">` in the `<head>` of the page, or the browser asks for `/favicon.ico` and logs a 404.
Tested with deck.gl 9.3.4 and loaders.gl 4.4.3. The export needs `infrared-sdk` with `TileExport` and `export_3d_tiles`.
For CesiumJS, see [cesium-tiles](cesium-tiles.md).

## 1. Make the folder (Python)

**Size rule.** Up to about 50 km²: one call. Above about 50 km², or when the area result does not fit in memory:
one run for each block (blocks of about 4 km² by default). This is guidance, not a limit. A run over 100 tiles needs
`max_tiles_override=` (the refusal names the value). For a block run the cap counts the WHOLE area (all blocks), so
pass `max_tiles_override=block.area_tiles`: the loop asks once for the price of the whole area.

**One call.**

```python
from infrared_sdk import TileExport

export = TileExport("out/", ids={0: "svf"})          # or an S3Target, see "Hosting"
client.run_area_and_wait(payload, polygon, buildings=buildings, export=export)
```

**Block loop (above about 50 km²): one run for each block, one layer in the viewer.** Tiles appear block by block.

```python
from infrared_sdk import TileExport, area_blocks

export = TileExport("out/")
for block in area_blocks(polygon, analysis_type=payload.analysis_type):  # about 4 km² each
    buildings = client.buildings.get_area(context_box(block))  # the block box + 600 m
    client.run_area_and_wait(payload, block, buildings=buildings, export=export,
                             max_tiles_override=block.area_tiles)  # tiles of the whole area
```

Pass the `Block` as it is. A block run needs the buildings of its window plus a margin of at least `context_reach_m`
(default 600 m); `get_area` adds only its own read margin, so `context_box` (yours; the code is in the Python SDK
README) widens the lon/lat box of `block.polygon` by 600 m on each side. A streamed analysis gives `None` in the result list; its summary is in
`export.summaries[analysis_id]`. For a saved result, a crash (`export_run`), ground, terrain and trees, see the
Python SDK README, section "Export to 3D Tiles", and [cesium-tiles](cesium-tiles.md) (section 1; it also has the
rules of a block that the target holds, and of the trees of a block loop).

The folder holds `manifest.json` (`analyses[]` with `facades.tileset`, `legend`, `stats`, `height`, `value`; and
`terrain`, `trees`), `analyses/<id>/analysis.json` (written last: no file, no analysis), `g/<sha256>.bin`
(shared geometry) and `analyses/<id>/facades/tileset.json` with the GLB tiles. A block run adds
`analyses/<id>/parts/<block key>/`; `facades.tileset` is the one root over all parts (one external tileset per block).
Load that one in ONE `Tile3DLayer`: loaders.gl loads the block tilesets by itself. Tested (deck.gl 9.3.4, loaders.gl
4.4.3, a synthetic 2-block export of 4 km x 2 km, `scripts/export3d/viewer_check.mjs` of infrared-core): 50 of 50 GLB
tiles load at zoom 13.6. At zoom 14.6 on the centre 42 of 50 loaded: tiles out of the view do not load, as for any
tileset, so start with a view that holds the area. `onTileLoad` is also called for a block tile (its `contentUrl`
ends with `.json`): count only the other tiles.
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

**One legend for each layer.** Each analysis has its own legend: `facades.legend` for a facade analysis,
`ground.legend` for a ground analysis (the ground colour tiles are painted with `ground.legend.vmin`, `vmax` and
`config`). Draw one legend for each visible layer from its own entry; never show the facade legend for the ground.

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

These layers are in [deckgl-tiles-layers](deckgl-tiles-layers.md): the ground layer with a click value, terrain from manifest `terrain`, and trees from manifest `trees.tileset`. They are in the folder when you pass `terrain=` and `trees=` to `TileExport`, or call `export_ground_tiles`, `export_terrain_tiles` and `export_trees`.

## 5. Hosting

- A bucket: pass `S3Target(client, bucket, prefix)` as the target (`client` is a boto3 S3 client; R2, S3 and MinIO work).
  `TileExport(S3Target(client, "my-bucket", "tiles/site1"))` writes the run to it. `S3Target` sets `ContentType` and
  `CacheControl` on each object, and writes `analysis.json` last, only when the key is absent (conditional write),
  so of two writers of one id one wins. CORS is a bucket setting, not a key setting: set it yourself.
- A plain host that ignores `_headers` sends no `Cache-Control` for `manifest.json`: a browser can show an old list
  for a while. Set `no-cache` for `manifest.json` on that host.
- `_headers` works on Cloudflare Pages (put the folder in the deploy root).
- R2 and S3 do not read `_headers`. `S3Target` sets the two header fields per object; the bucket CORS stays by hand:
  - CORS: allow `GET` and `HEAD` from your page origin, allow the header `Range`, expose `ETag`.
  - `Content-Type` (`S3Target` sets it): `.glb` `model/gltf-binary`; `.bin`, `.pmtiles`, `.terrain` and `.i3dm` `application/octet-stream`; `.png` `image/png`; `.tif` `image/tiff`.
  - `Cache-Control` (`S3Target` sets it): `g/` and `trees/` `public, max-age=31536000, immutable` (named by content);
    `analyses/`, `terrain/` and `manifest.json` `no-cache` (named by position).
- Any other host must answer `206` with `Accept-Ranges: bytes` if you use PMTiles.
- The page must run on `http(s)`, not `file://`.

## Add an analysis later

No code change in the app. Export a new id into the same folder (or the same `S3Target`). The export rebuilds
`manifest.json`; the app reads it again and lists the new entry. `manifest.json` is `no-cache`, so a reload sees it.

```python
export_3d_tiles(result2, "out/", "utci")                       # a live result: no other argument
export_3d_tiles(columns2, "out/", "utci", layout=layout)       # a saved result: add the saved layout
# or a new run into the same folder:
# client.run_area_and_wait(payload, polygon, buildings=buildings, export=TileExport("out/", ids={0: "utci"}))
```

An id that exists is refused before any tile is written (`ValueError`), also with the same data, and a published id is
never reused: its files are cached. To replace an analysis in a folder, delete `analyses/<id>/` and export again, or
use a new id. An export that was killed leaves no analysis (no `analysis.json`) and blocks no id. The `terrain` and
`trees` entries stay in the manifest.

**A nightly job.** Put the date in the id: `f"solar-{day:%Y-%m-%d}"`. The manifest lists every id; the app takes the
newest of a prefix (ISO dates sort as text):

```js
const newest = manifest.analyses.map((a) => a.id).filter((id) => id.startsWith("solar-")).sort().at(-1);
```

Delete `analyses/<old id>/` after the new id is published; the next export drops it from `manifest.json`.

## Silent traps

- Wrong version pair (deck.gl 9.1 with loaders.gl 4.3): the tiles fail.
- `excludeExtensions: { EXT_structural_metadata: true }`: the tab freezes.
- `.gltf` tiles: not read. The export uses GLB.
- Interpolated sampling of value tiles: the numbers mean nothing. Use NEAREST.
- Tile y: deck.gl and PMTiles both count from the north. A flip puts tiles in the wrong place.
- `tile.boundingBox` is `[[west, south], [east, north]]`, not an object.
