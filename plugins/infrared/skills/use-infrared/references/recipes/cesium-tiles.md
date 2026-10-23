# CesiumJS: Infrared tiles in your own app

Make and host the folder with the SDK (guide: [3D Tiles](https://infrared.city/docs/sdk/#3d-tiles-from-a-run-to-a-viewer)).
Shared code: [tiles-folder](tiles-folder.md). Tested with CesiumJS 1.146 and a static host. For deck.gl see [deckgl-tiles](deckgl-tiles.md).

## 1. Load the tileset

```html
<link rel="icon" href="data:,">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/cesium@1.146.0/Build/Cesium/Widgets/widgets.css">
<script src="https://cdn.jsdelivr.net/npm/cesium@1.146.0/Build/Cesium/Cesium.js"></script>
```

```js
const viewer = new Cesium.Viewer("view", {
  baseLayer: false, baseLayerPicker: false, geocoder: false,          // all three: else ion imagery and a banner
  animation: false, timeline: false, homeButton: false, navigationHelpButton: false,
});
// manifest, analysis, tilesetUrl: see tiles-folder. No tilesetUrl (no facades): skip the tileset.
const tileset = await Cesium.Cesium3DTileset.fromUrl(tilesetUrl);
tileset.infrared = analysis;
viewer.scene.primitives.add(tileset);
await viewer.zoomTo(tileset, new Cesium.HeadingPitchRange(0, -0.5, tileset.boundingSphere.radius * 2.2));
```

The tiles need no ion token. The ion logo stays in the credit bar. The default look is the baked colour page.
Load the CSS (else the canvas is 300 x 150) and the empty icon (else a 404 for `/favicon.ico`).

## 2. Your own palette

`fsInput.metadata.value` is in the units of the analysis. The range is fixed per analysis (`analysis.legend`).

```js
function paletteShader(palette, [lo, hi]) {          // palette: [[r, g, b], ...] 0 to 255
  const n = palette.length;
  const stops = palette.map((c) => `vec3(${c.map((v) => (v / 255).toFixed(5)).join(",")})`).join(",");
  return new Cesium.CustomShader({
    lightingModel: Cesium.LightingModel.UNLIT,
    fragmentShaderText: `void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
      const vec3 S[${n}] = vec3[${n}](${stops});
      float t = clamp((float(fsInput.metadata.value) - ${lo.toFixed(6)}) / ${(hi - lo || 1).toFixed(6)}, 0.0, 1.0) * ${n - 1}.0;
      int i = int(min(floor(t), ${n - 2}.0));
      vec3 c = mix(S[i], S[i + 1], t - float(i)); // sRGB stops; the shader writes linear
      material.diffuse = mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
    }`,
  });
}
const { vmin, vmax, config } = analysis.legend;
const styled = await Cesium.Cesium3DTileset.fromUrl(tilesetUrl, { customShader: paletteShader(config.colors, [vmin, vmax]) });
```

One tile with two value pages does not compile in 1.146: use the baked colour for it.

## 3. Click to value

Use `pickMetadata` of the property `code_bytes` (not `value`: it loses the high byte). Decode: `value = offset + scale * (x + 256 * y) / 65535`
with `offset` and `scale` from `analysis.facades.value`; `x = y = 255` is no data.

```js
const { offset, scale } = analysis.facades.value;
new Cesium.ScreenSpaceEventHandler(viewer.canvas).setInputAction((m) => {
  const [x, y] = viewer.scene.pickMetadata(m.position, "infrared_surface", "cell", "code_bytes") ?? [];
  console.log(x === undefined || (x === 255 && y === 255) ? "no value" : offset + scale * (x + 256 * y) / 65535, analysis.units);
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
```

`pickMetadata` fails while the grey layer is on screen (its tiles have no metadata). Hide the grey tileset around the call.
Needs a tileset exported with the current SDK (the `code_bytes` property). Not run in a browser by this recipe: check one click against `analysis.facades.value` and `stats.p10` to `p90`.

## 4. Terrain and height

Tiles stand at the geoid height N plus `h0` (`root.extras.height`). Use the terrain of the same export: see
[cesium-tiles-layers](cesium-tiles-layers.md). A provider terrain has another datum: buildings float or sink.

## Silent traps

- `baseLayer: false` alone still shows ion imagery. Set the three options.
- Two value pages in one tile: shader compile error in 1.146.
- Others: [tiles-folder](tiles-folder.md).
