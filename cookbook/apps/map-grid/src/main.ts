// Sky view factor on a map: Infrared TypeScript SDK + MapLibre + deck.gl.
//
// Flow: start the WASM core -> pick an area (default or drawn) -> preview the
// jobs (free, local) -> "Run" -> merged ground grid -> BitmapLayer + legend.

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { BitmapLayer, PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import coreUrl from "@infrared-city/infrared-sdk/core.wasm?url";
import { InfraredClient, initializeCore, legendRange, type AreaResult } from "@infrared-city/infrared-sdk";
import type { Polygon } from "@infrared-city/infrared-sdk/tiling";
import { relayUrl } from "../../cloudflare-proxy/src/proxy.ts";
import { gridToCanvas } from "./grid-image.ts";
import { VIRIDIS, rampTable, renderLegend } from "./ramp.ts";

const ANALYSIS = "sky-view-factors";          // no weather needed: fast and cheap
type Ring = [number, number][];

const $ = (id: string) => document.getElementById(id)!;
const status = (text: string) => ($("status").textContent = text);

// ---- SDK client. The browser has no API key: the same-origin proxy adds it. ----
// An empty `auth` is accepted; without it (and without apiKey/token/getToken) the constructor throws.
// `fetch` sends the presigned result download through the proxy relay (that bucket has no CORS).
await initializeCore({ url: new URL(coreUrl, location.href) });
const client = new InfraredClient({
  baseUrl: `${location.origin}/api/ir`,
  auth: async () => ({}),
  fetch: (input, init) => fetch(input instanceof Request ? input : relayUrl(String(input)), init),
});

// ---- Map with a light basemap (OpenFreeMap: free, no key) ----
let ring: Ring = [[16.3695, 48.2065], [16.3755, 48.2065], [16.3755, 48.2105], [16.3695, 48.2105], [16.3695, 48.2065]];
const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  bounds: [ring[0], ring[2]],
  fitBoundsOptions: { padding: { top: 60, bottom: 60, left: 380, right: 60 } },
  attributionControl: { compact: false },
});
const overlay = new MapboxOverlay({ layers: [] });
map.addControl(overlay);

let draft: Ring | undefined;                     // vertices while drawing
let gridLayer: Layer | undefined;                // the result image

function redraw(): void {
  const layers: Layer[] = [];
  if (gridLayer) layers.push(gridLayer);
  layers.push(new PolygonLayer({
    id: "area", data: [{ polygon: ring }], getPolygon: (d: { polygon: Ring }) => d.polygon,
    filled: false, stroked: true, getLineColor: [29, 36, 51, 220], lineWidthUnits: "pixels", getLineWidth: 2,
  }));
  if (draft) {
    layers.push(new PathLayer({ id: "draft-line", data: [draft], getPath: (d: Ring) => d,
      getColor: [217, 72, 15], widthUnits: "pixels", getWidth: 2 }));
    layers.push(new ScatterplotLayer({ id: "draft-points", data: draft, getPosition: (d: [number, number]) => d,
      getFillColor: [217, 72, 15], radiusUnits: "pixels", getRadius: 4 }));
  }
  overlay.setProps({ layers });
}

// Preview is local and free: tile count and the token estimate, before anything is billed.
function showPreview(): void {
  try {
    const p = client.previewArea(polygon(), { analysisType: ANALYSIS });
    status(`${p.tileCount} tile(s) = ${p.tileCount} job(s), about ${p.estimatedCostTokens} tokens.\nPress Run.`);
    $("run").removeAttribute("disabled");
  } catch (error) {
    status((error as Error).message);            // e.g. over the 100-tile limit
    $("run").setAttribute("disabled", "");
  }
}
const polygon = (): Polygon => ({ type: "Polygon", coordinates: [ring] });

// ---- Draw: click to add points, double-click to finish, Esc to cancel ----
$("draw").addEventListener("click", () => {
  draft = [];
  $("draw").classList.add("active");
  map.doubleClickZoom.disable();
  status("Click to add points. Double-click to finish.");
});
map.on("click", (e) => {
  if (!draft) return;
  draft.push([e.lngLat.lng, e.lngLat.lat]);
  redraw();
});
map.on("dblclick", () => {
  if (!draft || draft.length < 3) return;
  ring = [...draft, draft[0]];
  draft = undefined;
  gridLayer = undefined;
  $("draw").classList.remove("active");
  map.doubleClickZoom.enable();
  redraw();
  showPreview();
});
addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !draft) return;
  draft = undefined;
  $("draw").classList.remove("active");
  map.doubleClickZoom.enable();
  redraw();
  showPreview();
});

// ---- Run ----
$("run").addEventListener("click", async () => {
  $("run").setAttribute("disabled", "");
  const t0 = performance.now();
  try {
    // Public buildings as the fallback. With your own model, pass your
    // { id: { coordinates, indices } } map (metres, polygon's south-west corner = origin).
    status("Reading buildings...");
    const buildings = await client.buildings.getBuildingsInArea(polygon(), { analysisType: ANALYSIS });
    status("Submitting...");
    // runAreaAndWait tiles, uploads, submits, polls (batched) and merges. No own poll loop.
    const result = (await client.runAreaAndWait({ analysisType: ANALYSIS }, polygon(), {
      buildings,
      onProgress: (s) => status(`Running: ${s.completedCount} of ${s.totalCount} tile(s) done`),
    })) as AreaResult;

    const range = legendRange(result, "exact") ?? [0, 100];
    gridLayer = new BitmapLayer({
      id: "grid",
      image: gridToCanvas(result, rampTable(VIRIDIS), range),
      bounds: result.bounds as [number, number, number, number], // [west, south, east, north]
      opacity: 0.85,
      textureParameters: { minFilter: "nearest", magFilter: "nearest" }, // crisp 1 m cells
    });
    redraw();
    renderLegend($("legend"), VIRIDIS, range, "Sky view factor (%)");
    $("legend").hidden = false;
    const [rows, cols] = result.gridShape;
    status(`Done in ${((performance.now() - t0) / 1000).toFixed(1)} s · ${cols} x ${rows} cells of 1 m`);
  } catch (error) {
    status(`Run failed: ${(error as Error).message}`);
  } finally {
    $("run").removeAttribute("disabled");
  }
});

map.on("load", () => {
  redraw();
  showPreview();
});
