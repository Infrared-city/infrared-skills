# Facades and roofs in three.js

Runnable app: [cookbook/apps/facades-3d](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/facades-3d)
(Vite + TypeScript + three.js). Copy `src/surface-mesh.ts`: it turns the SDK render
buffers into one mesh with one exact colour per cell.
Guide: [Facade and roof runs](https://infrared.city/docs/sdk/1.0/#facade-and-roof-runs),
[Draw facade and roof results fast](https://infrared.city/docs/sdk/1.0/#draw-facade-and-roof-results-fast).

## Run on surfaces

Solar radiation, sky view factor, direct sun hours and daylight availability can
run on surfaces. Set `analysisSurfaces` to `"facades"`, `"roofs"` or `"all"`. The
ground grid is then not computed.

```ts
const stations = await client.weather.getWeatherFileFromLocation(lat, lon, 100); // km, nearest first
const period = { start: { month: 6, day: 1, hour: 6 }, end: { month: 8, day: 31, hour: 20 } };
const weatherData = await client.weather.filterWeatherData(stations[0].uuid, { period });

const input = {
  analysisType: "solar-radiation", analysisSurfaces: "all", surfaceGridSize: 3, // cell size, m
  latitude: lat, longitude: lon, dateFilters: { period }, weatherData,
};
const preview = await client.previewAreaBatches(input, polygon, { buildings }); // free, local
// show preview.plannedJobCount, preview.sensorCount, preview.estimatedCostTokens before Run
const columns = (await client.runAreaAndWait(input, polygon, { buildings, onProgress })) as SurfaceColumns;
const buffers = surfaceRenderBuffers(columns);
const values = surfaceValuesF32(columns);                // kWh/m², NaN = no value (tooltips)
const range = legendRange(values, "trimmed") ?? [buffers.valueMin, buffers.valueMax];
```

- A facade run bills per building batch (at most 250,000 sensors per job). Use
  `previewAreaBatches`; `previewArea` counts too few jobs.
- Sensors go on the target buildings of each tile the polygon touches, not only
  inside the polygon. A bigger `surfaceGridSize` means fewer sensors and fewer jobs.
- Merge in the client that submitted the run: the outline lives in that client.
  `runAreaAndWait` does this. To draw later or elsewhere, save a `FacadeLayout`
  (see the guide, "Save, reload and free").

## Render buffers → BufferGeometry

```ts
// One vertex per outline corner. Positions are relative to buffers.anchor.
const frames = b.dims.length / 3;
const position = new Float32Array(b.outline.length / 2 * 3);
const frame = new Float32Array(b.outline.length / 2 * 3);   // nu, nv, cellStart per vertex
for (let f = 0; f < frames; f += 1) {
  const [cx, cy, cz, ux, uy, uz, vx, vy, vz] = b.frames.subarray(9 * f, 9 * f + 9);
  for (let v = 3 * b.outlineOffsets[f]; v < 3 * b.outlineOffsets[f + 1]; v += 1) {
    const s = b.outline[2 * v], t = b.outline[2 * v + 1];  // cell units
    position.set([cx + s * ux + t * vx, cy + s * uy + t * vy, cz + s * uz + t * vz], 3 * v);
    frame.set(b.dims.subarray(3 * f, 3 * f + 3), 3 * v);
  }
}
geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
geometry.setAttribute("cell", new THREE.BufferAttribute(b.outline, 2));   // (s, t)
geometry.setAttribute("frame", new THREE.BufferAttribute(frame, 3));
mesh.position.set(b.anchor[0], b.anchor[1], b.anchor[2]);  // keep the f64 anchor in the transform
```

Fragment shader (GLSL3 `ShaderMaterial`, `side: DoubleSide`):

```glsl
int j = clamp(int(floor(vCell.x)), 0, nu - 1);
int i = clamp(int(floor(vCell.y)), 0, nv - 1);
int k = cellStart + i * nu + j;                       // the cell under this pixel
ivec2 p = ivec2(k % W, k / W);                        // 2D texture: W = 4096 texels per row
if (texelFetch(uValid, p, 0).r > 0.5)                 // validity expanded to one byte per cell
  color = texture(uRamp, vec2((texelFetch(uValues, p, 0).r - lo) / (hi - lo), 0.5)).rgb;
```

- `values` with `valueDtype === "f16"` is a `Uint16Array` of half-float bits. Upload it
  as `DataTexture(data, W, H, RedFormat, HalfFloatType)`: no conversion. For `"f32"`
  use `FloatType`.
- A cell with no value has `values[k] = 0` and a clear validity bit. Test the bit,
  never the value. The app expands the bits to bytes once (`R8` texture).
- Declare `out vec4 fragColor;` in a GLSL3 shader (three.js has no `gl_FragColor` there).
- Frame data as float attributes is exact up to 16.7 million cells per mesh.
- Per-vertex colours are the wrong tool: an outline triangle spans many cells.

## Scene frame

Buildings, `anchor` and frames use one frame: metres from the polygon's south-west
corner, x east, y north, z up. Set `camera.up.set(0, 0, 1)` before `OrbitControls`.
Draw the building meshes in grey with `polygonOffset` behind the result, so the
colours win on the same walls.

## Hover value

Raycast the mesh. `hit.faceIndex` gives the 3 vertices; mix their `cell` attribute
with `hit.barycoord` to get `(s, t)`, then `k` with the same rule as the shader.
Show `values[k]` from `surfaceValuesF32` when the validity bit is set.
The app's `src/sample.ts` does this (`cellFromHit`, `cellInfo`). It also samples
at your own points and gives statistics per building:
[facades-sampling.md](facades-sampling.md).

## Checks that passed (real run, 217,083 cells)

- Render-buffer values equal `surfaceValuesF32`, validity equals `surfaceHasValue`.
- `corner + anchor` is half a cell (u and v) from the column `origin` (the first cell
  centre); `uStep`/`vStep` equal `uAxis`/`vAxis` x `gridSize`.
- 99.9 % of the frame centres lie inside a building's bounding box.

## Memory

`buffers.outline` is the same array as `columns.outline`: do not change it. Call
`client.jobs.captures.forgetSchedule(schedule)` for a run you do not merge, and
`layout.free()` for each `FacadeLayout`.
