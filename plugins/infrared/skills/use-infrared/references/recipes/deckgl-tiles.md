# deck.gl: Infrared tiles in your own app

Make and host the folder with the SDK (guide: [3D Tiles](https://infrared.city/docs/sdk/#3d-tiles-from-a-run-to-a-viewer)).
Shared code: [tiles-folder](tiles-folder.md). Put `<link rel="icon" href="data:,">` in the page head (else a 404 for `/favicon.ico`).
Tested with deck.gl 9.3.4 and loaders.gl 4.4.3. For CesiumJS see [cesium-tiles](cesium-tiles.md).

## 1. 3D tiles with Tile3DLayer

Use exactly these versions. deck.gl 9.1 with loaders.gl 4.3 fails. With npm: `deck.gl@9.3.4`, `@loaders.gl/3d-tiles@4.4.3`.

```html
<script src="https://unpkg.com/deck.gl@9.3.4/dist.min.js"></script>
<script src="https://unpkg.com/@loaders.gl/3d-tiles@4.4.3/dist/dist.min.js"></script>
```

```js
// manifest, analysis, tilesetUrl: see tiles-folder
const d = new deck.Deck({
  initialViewState: { longitude: 114.17, latitude: 22.3, zoom: 15 }, controller: true,
  layers: [new deck.Tile3DLayer({
    id: "infrared", data: tilesetUrl, loader: loaders.Tiles3DLoader,
    loadOptions: {
      "3d-tiles": { loadGLTF: true },
      tileset: { maximumScreenSpaceError: 0 },
      gltf: { excludeExtensions: { EXT_structural_metadata: false } },   // true freezes the tab; do not change
    },
    onTilesetLoad: (ts) => d.setProps({ initialViewState: {
      longitude: ts.cartographicCenter[0], latitude: ts.cartographicCenter[1], zoom: 14.6, pitch: 50 } }),
  })],
});
```

Load `tileset.json` only (GLB tiles; `.gltf` tiles are not read). A block tile has a `.json` content url: count other tiles only.
Tiles out of the view do not load: start with a view that holds the area. The default look is the baked colour page.
`Tile3DLayer` has no `CustomShader`: your own palette on the facades is not available.

## 2. Click to value on the 3D tiles

`Tile3DLayer` has no metadata pick. Read the value from the GLB of the clicked tile: `info.object.contentUrl`, then find
the triangle at the point and decode the value texture with the formula in the guide
([read the files](https://infrared.city/docs/sdk/#3d-tiles-read-the-files)). This path is NOT tested in deck.gl.
If you need a tested click value on facades, use [cesium-tiles](cesium-tiles.md). For the ground use
[deckgl-tiles-layers](deckgl-tiles-layers.md): it is tested.

## 3. Base height

Tiles stand at the geoid height N plus `h0` (`root.extras.height`). Use the terrain of the same export
([deckgl-tiles-layers](deckgl-tiles-layers.md)), not a provider DEM. Not tested: the fit on a basemap with no terrain.

## Silent traps

- Wrong version pair (deck.gl 9.1 with loaders.gl 4.3): the tiles fail.
- `excludeExtensions: { EXT_structural_metadata: true }`: the tab freezes.
- Tile y: deck.gl and PMTiles both count from the north. No flip.
- `tile.boundingBox` is `[[west, south], [east, north]]`, not an object.
- Others: [tiles-folder](tiles-folder.md).
