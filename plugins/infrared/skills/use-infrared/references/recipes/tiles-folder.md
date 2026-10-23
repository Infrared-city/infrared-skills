# Infrared tiles folder: what both viewers share

The folder is written by the SDK (`TileExport`, `export_tiles`) and read by CesiumJS or deck.gl. The guide owns
the how-to: [3D Tiles: from a run to a viewer](https://infrared.city/docs/sdk/#3d-tiles-from-a-run-to-a-viewer)
(make the folder, host it, the manifest), [a whole city and changes](https://infrared.city/docs/sdk/#3d-tiles-a-whole-city-and-changes)
and [read the files](https://infrared.city/docs/sdk/#3d-tiles-read-the-files) (decode formulas, byte order, no data).
This page keeps only the code that both viewer pages use.
Viewers: [cesium-tiles](cesium-tiles.md), [deckgl-tiles](deckgl-tiles.md). Change a city: [update-tool](update-tool.md).

## Read the manifest

```js
const manifestUrl = new URL("manifest.json", document.baseURI).href;   // serve over http(s), not file://
const manifest = await (await fetch(manifestUrl)).json();               // format infrared-3d-export/4
const analysis = manifest.analyses.find((a) => a.id === "svf");
if (!analysis?.facades) { /* no buildings: no facade layer; show the ground only */ }
const tilesetUrl = analysis.facades && new URL(analysis.facades.tileset, manifestUrl).href;  // a facade or roof analysis
```

Per analysis: `legend` (`vmin`, `vmax`, `config`), `height`, `units`, `facades.{tileset,value}`, `ground`, `stale`.
`facades` is absent when the analysis has no buildings; a part can be `empty: true` (no layer): skip both.
`stats` and `run` are in `analyses/<id>/analysis.json`, not in the manifest. A nightly job puts the date in the id; the
app takes the newest id of a prefix: `ids.filter((id) => id.startsWith("solar-")).sort().at(-1)`.

## Ground: expand the parts

A part is `{...ground.part, ...parts[i]}`, a chunk is `{...ground.chunk, ...overview[i]}`. The file paths come from
`manifest.paths.part` and `manifest.paths.chunk`. The root `ground` has no `files`.

```js
const fill = (t, v) => t.replace(/\{(\w+)\}/g, (_, k) => v[k]);
function groundOf(a) {                                  // a: an entry of manifest.analyses; null without ground
  const g = a.ground; if (!g) return null;
  const urls = (tpl, v, e) => Object.fromEntries(Object.entries(e.files).map(([kind, file]) =>
    [kind, new URL(fill(tpl, { ...v, file }), manifestUrl).href]));
  const overview = (g.overview ?? []).map((c) => { const e = { ...g.chunk, ...c };
    return { ...e, files: urls(manifest.paths.chunk, { id: a.id, name: c.name }, e) }; });
  const parts = (g.parts ?? []).map((p) => { const e = { ...g.part, ...p };
    return { ...e, files: urls(manifest.paths.part, { id: a.id, key: p.key, rev: p.rev }, e) }; });
  return { ...g, legend: g.legend ?? a.legend, overview, parts };
}
```

For a click value on a city, read `ground.merged` (one value archive: `new URL(g.merged.files.value, manifestUrl)`, with
its own `minzoom`, `maxzoom`, `encoding`, `lo`, `step`). Colour tiles (`files.colour`) exist only when the export
was made with `ground_colour=True`; CesiumJS imagery needs them.

```js
// Value at (lon, lat) from a PMTiles value archive `pm` (pmtiles lib), source s = merged, a part or a chunk.
async function valueAt(pm, s, lon, lat, size = 512) {
  const m = 2 ** s.maxzoom, fx = (lon + 180) / 360 * m;
  const fy = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * m;
  const x = Math.floor(fx), y = Math.floor(fy), t = await pm.getZxy(s.maxzoom, x, y);
  if (!t) return null;
  const bmp = await createImageBitmap(new Blob([t.data], { type: "image/png" }),
    { premultiplyAlpha: "none", colorSpaceConversion: "none" });
  const cx = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d", { willReadFrequently: true });
  cx.drawImage(bmp, 0, 0);
  const [r, g, , a] = cx.getImageData(Math.floor((fx - x) * size), Math.floor((fy - y) * size), 1, 1).data;
  const u8 = s.encoding === "value_u8_l";
  if (u8 ? r === 255 : a === 0) return null;                 // no data
  return s.lo + s.step * (u8 ? r : 256 * r + g);             // ground: R is the HIGH byte
}
```

## Hosting traps

- A bucket needs CORS: allow `GET`, `HEAD` and the header `Range`; expose `ETag` and `Content-Range`. PMTiles needs `Range`.
- A host that ignores `_headers` must send `no-cache` for `manifest.json`, or a browser shows an old list.
- Serve `.terrain` as `application/octet-stream` with no `Content-Encoding`.

## Silent traps

- Facade value bytes: R is LOW. Ground value bytes: R is HIGH. Never share a decoder.
- Sample value tiles with NEAREST. Interpolated codes mean nothing.
- Terrain and facades need one base height. Use the terrain of the same export, not a provider terrain.
- An id that exists is refused (`ValueError`), also with the same data. Use a new id.
