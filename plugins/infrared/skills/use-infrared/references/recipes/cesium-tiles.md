# CesiumJS: Infrared tiles in your own app

Infrared gives you the data as standard tiles. This recipe is the last step: show the tiles in your CesiumJS app.
Tested with CesiumJS 1.146 and a static host. The export needs `infrared-sdk` with `TileExport` and `export_tiles`.
For deck.gl, see [deckgl-tiles](deckgl-tiles.md).

## 1. Make the folder (Python)

**Size rule.** Up to about 50 km²: one call. Above about 50 km², or when the area result does not fit in memory:
one run for each block (blocks of about 4 km² by default). This is guidance, not a limit. A run over 100 tiles needs
`max_tiles_override=` (the refusal names the value). For a block loop the cap counts the WHOLE area (all blocks):
pass `max_tiles_override=` once, to `area_blocks`.

**One call.** The results go to the folder while the run goes on.

```python
from infrared_sdk import TileExport

export = TileExport("out/", ids={0: "svf"})          # or an S3Target, see "Hosting"
client.run_area_and_wait(payload, polygon, buildings=buildings, export=export)
print(export.summaries["svf"].files)
```

A streamed analysis gives `None` in the result list. Its summary is in `export.summaries[analysis_id]`.

**Block loop (above about 50 km²): one run for each block, one layer in the viewer.** Tiles appear block by block.

```python
from infrared_sdk import TileExport, area_blocks

export = TileExport("out/")
blocks = area_blocks(polygon, analysis_type=payload.analysis_type,  # about 4 km² each
                     max_tiles_override=1200)  # the price of the whole area, once
for block in blocks:
    buildings = client.buildings.get_area(block.context_polygon(600))  # the window + 600 m
    client.run_area_and_wait(payload, block, buildings=buildings, export=export)
```

Pass the `Block` as it is. `area_blocks` refuses an area over `max_tiles_override` (default 100 tiles, the count of
the whole area) before anything is sent, and the blocks carry the price: the block runs need no override. A block
run needs the buildings of its window plus a margin of at least `context_reach_m` (default 600 m):
`block.context_polygon(600)`. The ground of the loop is the ground of one run, wind included.
A block that the folder or bucket holds is never written again. Run it again with the same results (for example
after a failed root rebuild): no file of the block is written and the call is a success. Other results for a held
block raise `ValueError` ("exists with other results") and change no file: export the blocks into a new id. Run the
blocks of one id one after the other, from one process (the root is rebuilt after each block). Give
`TileExport(trees=...)` the trees of the whole area: the first block writes them, the later blocks write nothing,
and `manifest.trees.tileset` is one tileset of the whole area.

**Export again after a crash, with no new job.** Save `schedule.to_dict()` as JSON (temp file, fsync, rename) right
after `client.run_area(...)`. Later: `client.export_run(payload, polygon, "out/", schedule=AreaSchedule.from_dict(saved),
buildings=buildings)` with the same inputs as the run. Pass `on_accepted=lambda job_id, tile_key: ...` to `run_area`
to log each accepted job at once: if the process stops before the schedule is saved, the log names the billed jobs.
The log is not a schedule, and `export_run` cannot use it. The server keeps results about 24 hours: run `export_run`
within a day. For a later re-export, keep your own copy of the results (the Python SDK README, "Save and reload a
facade result"); else the analysis needs a new run.

**A saved result (notebook).** `export_tiles(columns, "out/", "svf", layout=layout, schedule=svf_schedule,
config=config)`, with `columns` from `SurfaceColumns.from_bytes`, `layout` from `FacadeLayout.from_bytes(data,
schedule=<the schedule of the run that made the layout>)`, `schedule` from `AreaSchedule.from_dict`. One layout
serves all analyses of a run. With no network, `config=` is the colour entry; an export that read the registry keeps
it in `analysis.json` as `facades.legend.config` (or `ground.legend.config`): save it. The Python SDK README,
section "Export to 3D Tiles" ("Save, reload, add an analysis later"), has the full recipe.

The folder holds (format `infrared-3d-export/2`):
- `manifest.json`: `analyses[]`, `terrain`, `trees`. Each analysis has `facades.tileset`, `legend`, `stats`, `height` and `value`.
- `analyses/<id>/analysis.json`: the same entry. It is written last, so a folder without it is no analysis.
- `g/<sha256>.bin`: shared geometry. A new analysis on the same buildings writes no new geometry.
- `analyses/<id>/facades/tileset.json` and the GLB tiles. A block run has `analyses/<id>/parts/<block key>/`
  for each block; `facades.tileset` of the analysis is the root that points to all of them (one external tileset per
  block). Load that one with `Cesium3DTileset.fromUrl`, as below: CesiumJS loads the block tilesets by itself.
  Tested (CesiumJS 1.146, a synthetic 2-block export, `scripts/export3d/viewer_check.mjs` of infrared-core): 50 of
  50 GLB tiles of the two blocks load, 36 facade clicks give the value of the GLB, 0 wrong, the picks of section 3
  work unchanged. A block tile has the `tileLoad` event too (its content is a `tileset.json`): count GLB tiles only.
- `analyses/<id>/ground/`, `terrain/`, `trees/<key>/` when you exported them (sections 6 and below).

## 2. Load the tileset

Load the CSS too, or the canvas is 300 x 150. Add the empty icon, or the browser asks for `/favicon.ico` and logs a
404 in the console.

```html
<link rel="icon" href="data:,">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/cesium@1.146.0/Build/Cesium/Widgets/widgets.css">
<script src="https://cdn.jsdelivr.net/npm/cesium@1.146.0/Build/Cesium/Cesium.js"></script>
```

```js
const viewer = new Cesium.Viewer("view", {
  baseLayer: false, baseLayerPicker: false, geocoder: false, // no ion widgets
  animation: false, timeline: false, homeButton: false, navigationHelpButton: false,
});
const manifestUrl = new URL("manifest.json", document.baseURI).href;
const manifest = await (await fetch(manifestUrl)).json();
const analysis = manifest.analyses.find((a) => a.id === "svf");
const tileset = await Cesium.Cesium3DTileset.fromUrl(new URL(analysis.facades.tileset, manifestUrl).href);
tileset.infrared = analysis;
viewer.scene.primitives.add(tileset);
await viewer.zoomTo(tileset, new Cesium.HeadingPitchRange(0, -0.5, tileset.boundingSphere.radius * 2.2));
```

The default look is the baked colour page. You need no more code to show the result.

**Ion.** The tiles need no ion token. But `baseLayer: false` alone is not enough: in a test with 1.146 the page still
showed ion imagery and the banner "default ion access token". The default `baseLayerPicker` and `geocoder` use ion.
Turn them off as above, and give a base layer of your own if you want one
(`baseLayer: new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({ url: "https://your.tiles/{z}/{x}/{y}.png" }))`).
Not tested with this exact option set: open the network tab and check that no request goes to `cesium.com`.
A test with this option set and no token found no request to an ion host, but the Cesium ion logo stays in the credit
bar (bottom left). That is normal: the logo is part of the CesiumJS credit display, not an ion request. Keep the credit
bar; the credits of your own layers show there too.

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

## 3. Your own palette

Each tile has a value page with the property `value`. Cesium applies the offset and scale,
so `fsInput.metadata.value` is already in the units of the analysis. Use a `CustomShader`.
The stops are `[[r, g, b], ...]` (0 to 255). The range is fixed per analysis, not per view.
The legend of the analysis gives defaults: `analysis.facades.legend.config.colors`, `vmin` and `vmax`.

```js
function paletteShader(palette, [lo, hi]) {
  const n = palette.length;
  const stops = palette.map((c) => `vec3(${c.map((v) => (v / 255).toFixed(5)).join(",")})`).join(",");
  return new Cesium.CustomShader({
    lightingModel: Cesium.LightingModel.UNLIT,
    fragmentShaderText: `void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
      const vec3 S[${n}] = vec3[${n}](${stops});
      float t = clamp((float(fsInput.metadata.value) - ${lo.toFixed(6)}) / ${(hi - lo || 1).toFixed(6)}, 0.0, 1.0) * ${n - 1}.0;
      int i = int(min(floor(t), ${n - 2}.0));
      vec3 c = mix(S[i], S[i + 1], t - float(i)); // blended as sRGB colours; the shader writes linear
      material.diffuse = mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
    }`,
  });
}
const { vmin, vmax, config } = analysis.facades.legend;
const tileset = await Cesium.Cesium3DTileset.fromUrl(url, { customShader: paletteShader(config.colors, [vmin, vmax]) });
```

Cells without data keep the alpha of the colour page, so they stay cut out.
CesiumJS 1.146 cannot draw a tile with two value pages (shader compile error: one uniform for each texture).
Use the baked colour for such a tile.

## 4. Click to value

**Do not use `scene.pickMetadata`.** In CesiumJS 1.146 it returns wrong values for this `UINT16` property.
Read the value from the GLB of the clicked tile:

1. Pick the tile and the 3D point. Move the point into the tile frame.
2. Fetch the GLB (and its `g/<sha256>.bin` buffer). Read positions, `TEXCOORD_0` and the value PNG.
3. Find the triangle at the point and get its uv. Read the nearest texel with data.
4. Decode the texel (see the table).

| Item | Value |
|---|---|
| Code | `R + 256 * G` (R is the LOW byte) |
| Value | `offset + scale * code / 65535`; `offset` and `scale` come from `analysis.facades.value` |
| No data | code `65535`, or alpha `0` |

The byte order is the opposite of the ground tiles below. Do not copy one decoder to the other.

Decode the PNG with `premultiplyAlpha: "none"` and `colorSpaceConversion: "none"`. Without them the codes change.

```js
async function decodeValues(png, prop, cls) { // prop: property texture entry; cls: class property (offset, scale, noData)
  const bmp = await createImageBitmap(new Blob([png], { type: "image/png" }), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
  const cv = new OffscreenCanvas(bmp.width, bmp.height), cx = cv.getContext("2d", { willReadFrequently: true });
  cx.drawImage(bmp, 0, 0);
  const px = cx.getImageData(0, 0, bmp.width, bmp.height).data;
  const [c0, c1] = prop.channels ?? [0, 1];
  const value = new Float32Array(bmp.width * bmp.height);
  for (let i = 0; i < value.length; i++) {
    const code = px[i * 4 + c0] + 256 * px[i * 4 + c1];
    value[i] = px[i * 4 + 3] === 0 || code === cls.noData ? NaN : cls.offset + cls.scale * code / 65535;
  }
  return { value, w: bmp.width, h: bmp.height };
}
```

The pick, as tested (about 45 clicks agreed with an independent decode within one codec step):

```js
async function readGlb(url) { // returns one entry per mesh primitive: { pos, uv, value, w, h }
  const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer());
  const dv = new DataView(bytes.buffer), jl = dv.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jl)));
  const bin = bytes.subarray(28 + jl);
  const buffers = await Promise.all(json.buffers.map(async (b) =>
    b.uri ? new Uint8Array(await (await fetch(new URL(b.uri, url).href)).arrayBuffer()) : bin));
  const view = (i) => { const v = json.bufferViews[i]; return buffers[v.buffer].subarray(v.byteOffset ?? 0, (v.byteOffset ?? 0) + v.byteLength); };
  const floats = (i, n) => {
    const a = json.accessors[i], v = view(a.bufferView), from = v.byteOffset + (a.byteOffset ?? 0);
    return new Float32Array(v.buffer.slice(from, from + a.count * n * 4));
  };
  const meta = json.extensions.EXT_structural_metadata, cls = Object.values(meta.schema.classes)[0].properties.value;
  const pages = [];
  for (const node of json.nodes) {
    if (node.mesh === undefined) continue;
    const t = node.translation ?? [0, 0, 0];
    for (const prim of json.meshes[node.mesh].primitives) {
      const pos = Float64Array.from(floats(prim.attributes.POSITION, 3)), uv = floats(prim.attributes.TEXCOORD_0, 2);
      for (let i = 0; i < pos.length; i += 3) for (let c = 0; c < 3; c++) pos[i + c] += t[c];
      const prop = meta.propertyTextures[prim.extensions.EXT_structural_metadata.propertyTextures[0]].properties.value;
      const png = view(json.images[json.textures[prop.index].source].bufferView);
      pages.push({ pos, uv, ...(await decodeValues(png, prop, cls)) });
    }
  }
  return pages;
}

// Point (x, y, z) in glTF coordinates: nearest triangle within 2 m, barycentric uv, nearest texel with data.
function lookup(pages, x, y, z) {
  let best = 2, g = null, u = 0, v = 0;
  for (const page of pages) {
    const P = page.pos, U = page.uv;
    for (let i = 0; i < P.length; i += 9) {
      const e1 = [P[i + 3] - P[i], P[i + 4] - P[i + 1], P[i + 5] - P[i + 2]], e2 = [P[i + 6] - P[i], P[i + 7] - P[i + 1], P[i + 8] - P[i + 2]];
      const n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
      const n2 = n[0] * n[0] + n[1] * n[1] + n[2] * n[2];
      if (n2 < 1e-12) continue;
      const d = [x - P[i], y - P[i + 1], z - P[i + 2]];
      const dist = Math.abs(d[0] * n[0] + d[1] * n[1] + d[2] * n[2]) / Math.sqrt(n2);
      if (dist >= best) continue;
      const b = (d[0] * (n[2] * e2[1] - n[1] * e2[2]) + d[1] * (n[0] * e2[2] - n[2] * e2[0]) + d[2] * (n[1] * e2[0] - n[0] * e2[1])) / n2;
      const c = (e1[0] * (d[1] * n[2] - d[2] * n[1]) + e1[1] * (d[2] * n[0] - d[0] * n[2]) + e1[2] * (d[0] * n[1] - d[1] * n[0])) / n2;
      const a = 1 - b - c;
      if (a < -0.03 || b < -0.03 || c < -0.03) continue;
      const k = (i / 3) * 2;
      best = dist; g = page;
      u = a * U[k] + b * U[k + 2] + c * U[k + 4];
      v = a * U[k + 1] + b * U[k + 3] + c * U[k + 5];
    }
  }
  if (!g) return null;
  const tx = Math.min(g.w - 1, Math.max(0, Math.floor(u * g.w))), ty = Math.min(g.h - 1, Math.max(0, Math.floor(v * g.h)));
  for (let r = 0; r <= 2; r++) for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
    const xx = tx + dx, yy = ty + dy;
    if (Math.max(Math.abs(dx), Math.abs(dy)) !== r || xx < 0 || yy < 0 || xx >= g.w || yy >= g.h) continue;
    const val = g.value[yy * g.w + xx];
    if (Number.isFinite(val)) return val;
  }
  return null;
}

async function pickValue(viewer, windowPosition) {
  const scene = viewer.scene, picked = scene.pick(windowPosition), p = scene.pickPosition(windowPosition);
  const tile = picked?.content?.tile ?? picked?.primitive?.content?.tile;
  if (!p || !tile?.content?.url || !tile.tileset?.infrared) return null;
  const world = Cesium.Matrix4.multiply(tile.tileset.modelMatrix, tile.computedTransform, new Cesium.Matrix4());
  const l = Cesium.Matrix4.multiplyByPoint(Cesium.Matrix4.inverse(world, new Cesium.Matrix4()), p, new Cesium.Cartesian3());
  return lookup(await readGlb(tile.content.url), l.x, l.z, -l.y); // tile frame (z up) -> glTF frame (y up)
}

new Cesium.ScreenSpaceEventHandler(viewer.canvas).setInputAction(async (m) => {
  const value = await pickValue(viewer, m.position);
  console.log(value === null ? "no value here" : `${value} ${analysis.units ?? ""}`);
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
```

Cache the result of `readGlb` for each tile URL in a real app. The test page did, and kept the last 8.

## 5. Terrain and height

- The tiles carry `extras.height` (`root.extras.height` of the tileset). The base height of the tiles is the EGM2008
  geoid height N plus `h0`. For Hong Kong N is about -2.3 m. A flat base of 0 puts the tiles on the ellipsoid,
  not on the ground.
- Use the terrain of the same run, not a provider terrain. The terrain export is a `heightmap-1.0` folder with
  `layer.json`. It has the same base height as the tiles, so walls meet the ground.

The terrain code and the test result are in [cesium-tiles-layers](cesium-tiles-layers.md) (section 2).
A provider terrain such as world terrain has another datum and another resolution. Buildings then float or sink.
Serve `.terrain` files as `application/octet-stream` with no `Content-Encoding`.

## 6. Ground, terrain and trees

These layers are in [cesium-tiles-layers](cesium-tiles-layers.md): the ground layer as PMTiles imagery with a click value, terrain from manifest `terrain`, and trees from manifest `trees.tileset`. They are in the folder when you pass `terrain=` and `trees=` to `TileExport` or to `export_tiles` (a grid result gives the ground).

## 7. Hosting

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
export_tiles(result2, "out/", "utci")                       # a live result: no other argument
export_tiles(columns2, "out/", "utci", layout=layout)       # a saved result: add the saved layout
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

- `scene.pickMetadata` returns wrong values for this property in 1.146. Decode the GLB.
- Two value pages in one tile: shader compile error in 1.146. Use the baked colour.
- Interpolated sampling of value tiles gives codes that mean nothing. Use NEAREST.
- Ground tiles and 3D tiles have different byte order (HIGH-first and LOW-first).
- A base height of 0 or a provider terrain: tiles float or sink.
