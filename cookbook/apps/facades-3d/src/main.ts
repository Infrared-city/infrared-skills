// Facade + roof solar radiation viewer: Infrared TypeScript SDK + three.js.
//
// Flow: start the WASM core -> read buildings and weather -> preview the jobs
// (free, local) -> "Run" -> render buffers -> one three.js mesh, coloured per cell.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import coreUrl from "@infrared-city/infrared-sdk-ts/core.wasm?url";
import {
  InfraredClient, initializeCore, legendRange, surfaceRenderBuffers, surfaceValuesF32,
  type SurfaceColumns, type SurfaceRenderBuffers,
} from "@infrared-city/infrared-sdk-ts";
import type { Polygon } from "@infrared-city/infrared-sdk-ts/tiling";
import { createContextMesh } from "./context-mesh.ts";
import { cellIndex, cellIsValid, createSurfaceMesh } from "./surface-mesh.ts";
import { SOLAR, rampTable, renderLegend } from "./ramp.ts";
import { relayUrl } from "../../cloudflare-proxy/src/proxy.ts";

// ---- The site: a small box in central Vienna. Change it with ?lon=..&lat=.. ----
const params = new URLSearchParams(location.search);
const lon = Number(params.get("lon") ?? 16.3712);
const lat = Number(params.get("lat") ?? 48.2078);
const polygon: Polygon = {
  type: "Polygon",
  coordinates: [[[lon, lat], [lon + 0.002, lat], [lon + 0.002, lat + 0.0013], [lon, lat + 0.0013], [lon, lat]]],
};
// Summer, daytime hours. One window; it may also wrap the year (Dec-Feb).
const period = { start: { month: 6, day: 1, hour: 6 }, end: { month: 8, day: 31, hour: 20 } };

const $ = (id: string) => document.getElementById(id)!;
const status = (text: string) => ($("status").textContent = text);
$("site").textContent = `${lat.toFixed(4)} N, ${lon.toFixed(4)} E · June to August · 3 m cells`;

// ---- three.js scene: Z is up, x = east, y = north, metres from the polygon's SW corner ----
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
$("scene").appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf4f5f7);
const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 1, 5000);
camera.up.set(0, 0, 1);
camera.position.set(640, -420, 520);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(250, 250, 0);
controls.update();
scene.add(new THREE.HemisphereLight(0xffffff, 0xb0b4bb, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.position.set(300, -400, 600);
scene.add(sun);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000), new THREE.MeshLambertMaterial({ color: 0xeceef1 }));
ground.position.set(250, 250, -0.05);
scene.add(ground);
addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
renderer.setAnimationLoop(() => renderer.render(scene, camera));

// ---- SDK client. The browser has no API key: the same-origin proxy adds it. ----
// `auth` returns no header here. Without `auth` (and without apiKey/token/getToken)
// the constructor throws, so an empty `auth` is the way to say "the proxy signs".
// `fetch` sends the presigned result download through the proxy relay (no CORS on that bucket).
await initializeCore({ url: new URL(coreUrl, location.href) });
const client = new InfraredClient({
  baseUrl: `${location.origin}/api/ir`,
  auth: async () => ({}),
  fetch: (input, init) => fetch(input instanceof Request ? input : relayUrl(String(input)), init),
});

// Public data as the fallback: your own building meshes go into the same `buildings` option.
const buildings = await client.buildings.getBuildingsInArea(polygon);
scene.add(createContextMesh(buildings.buildings as never));
const stations = await client.weather.getWeatherFileFromLocation(lat, lon, 100);
const weatherData = await client.weather.filterWeatherData(stations[0].uuid, { period });

const input = {
  analysisType: "solar-radiation",
  analysisSurfaces: "all",        // facades and roofs; the ground grid is not computed
  surfaceGridSize: 3,             // cell size in metres: bigger = fewer sensors = fewer jobs
  latitude: lat, longitude: lon, dateFilters: { period }, weatherData,
} as const;

// Preview is local and free. For a facade run use previewAreaBatches, not previewArea.
const preview = await client.previewAreaBatches(input as never, polygon, { buildings });
status(`${preview.plannedJobCount} job(s) · ${preview.sensorCount?.toLocaleString()} sensors\n`
  + `about ${preview.estimatedCostTokens} tokens. Press Run.`);
$("run").removeAttribute("disabled");

let shown: { buffers: SurfaceRenderBuffers; values: Float32Array; mesh: THREE.Mesh } | undefined;

$("run").addEventListener("click", async () => {
  $("run").setAttribute("disabled", "");
  const t0 = performance.now();
  try {
    status("Submitting...");
    // runAreaAndWait polls in batches; do not write your own poll loop.
    const columns = (await client.runAreaAndWait(input as never, polygon, {
      buildings,
      onProgress: (s) => status(`Running: ${s.completedCount} of ${s.totalCount} job(s) done`),
    })) as SurfaceColumns;
    const buffers = surfaceRenderBuffers(columns);
    const values = surfaceValuesF32(columns);           // physical kWh/m2, for the tooltip
    const range = legendRange(values, "trimmed") ?? [buffers.valueMin, buffers.valueMax];
    const mesh = createSurfaceMesh(buffers, rampTable(SOLAR), range);
    if (shown) scene.remove(shown.mesh);
    scene.add(mesh);
    shown = { buffers, values, mesh };
    renderLegend($("legend"), SOLAR, range, "Solar radiation, June to August (kWh/m²)");
    $("legend").hidden = false;
    status(`Done in ${((performance.now() - t0) / 1000).toFixed(1)} s · `
      + `${buffers.values.length.toLocaleString()} cells on ${(buffers.dims.length / 3).toLocaleString()} surfaces`);
  } catch (error) {
    status(`Run failed: ${(error as Error).message}`);
  } finally {
    $("run").removeAttribute("disabled");
  }
});

// ---- Hover: show the value of the cell under the pointer ----
const raycaster = new THREE.Raycaster();
renderer.domElement.addEventListener("pointermove", (event) => {
  const tip = $("tip");
  if (!shown) return;
  const ndc = new THREE.Vector2((event.clientX / innerWidth) * 2 - 1, -(event.clientY / innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hit = raycaster.intersectObject(shown.mesh)[0];
  if (!hit || hit.faceIndex == null || !hit.barycoord) return void (tip.hidden = true);
  // (s, t) of the hit point = barycentric mix of the 3 corners' cell coordinates.
  const geo = shown.mesh.geometry;
  const cell = geo.getAttribute("cell");
  const frame = geo.getAttribute("frame");
  const v0 = 3 * hit.faceIndex;
  const w = [hit.barycoord.x, hit.barycoord.y, hit.barycoord.z];
  const s = w.reduce((sum, wi, i) => sum + wi * cell.getX(v0 + i), 0);
  const t = w.reduce((sum, wi, i) => sum + wi * cell.getY(v0 + i), 0);
  const k = cellIndex(frame.getX(v0), frame.getY(v0), frame.getZ(v0), s, t);
  tip.textContent = cellIsValid(shown.buffers, k) ? `${shown.values[k].toFixed(0)} kWh/m²` : "no value";
  tip.style.left = `${event.clientX}px`;
  tip.style.top = `${event.clientY}px`;
  tip.hidden = false;
});
