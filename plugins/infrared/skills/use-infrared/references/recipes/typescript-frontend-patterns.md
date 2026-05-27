# Recipe: Frontend Patterns for Showing Infrared Results (TypeScript / React)

Four small, copy-pasteable patterns for hackathon-grade UIs that show a simulation result without rebuilding production architecture.

**These are display patterns, not a data layer.** Pair them with either [`typescript-direct-api.md`](typescript-direct-api.md) (Node API route) or [`python-fastapi-railway.md`](python-fastapi-railway.md) (Python backend) for the fetch side.

## Target Stack

- React 18+ with Vite or Next.js (App Router fine).
- `zustand` for state (4 KB, no provider boilerplate).
- `maplibre-gl` for the map (Mapbox GL JS works the same).
- `@tanstack/react-query` for the fetch layer (optional but assumed).
- Tailwind for styling — snippets use Tailwind classes but translate to plain CSS one-to-one.

---

## Pattern A — Simulation registry

**Use when:** you have 2+ analyses (sun, wind, UTCI…) and want a single source of truth for "what can the user run, what does each cost, what icon does it have."

**Skip when:** you only have one analysis. A hardcoded button is fine.

For richer products you might end up with two parallel registries — **Workflows** (bundles of multiple analyses, marketing-oriented) and **IndividualSims** (leaf analyses). For hackathon scope, the leaf version below is enough.

```ts
// src/data/sim-registry.ts
export type SimId = "sun-hours" | "pwc" | "utci";

export interface Sim {
  id: SimId;
  analysisId: string;          // matches the kebab-case wire value: see typescript-direct-api.md
  name: string;
  icon: string;                // emoji is fine for hackathons; production design systems usually pass Lucide / Heroicons names
  description: string;
  pricePerTile: number;        // for cost display only — backend is source of truth
}

export const SIMS: readonly Sim[] = [
  { id: "sun-hours", analysisId: "direct-sun-hours",
    name: "Sun hours", icon: "☀️",
    description: "Hours of direct sun at street level over a season.",
    pricePerTile: 1 },
  { id: "pwc", analysisId: "pedestrian-wind-comfort",
    name: "Wind comfort", icon: "🌬️",
    description: "Lawson criteria for pedestrian-level wind.",
    pricePerTile: 2 },
  { id: "utci", analysisId: "thermal-comfort-index",
    name: "Thermal comfort", icon: "🌡️",
    description: "UTCI — feels-like temperature for outdoor comfort.",
    pricePerTile: 4 },
] as const;

export function useSimRegistry(): readonly Sim[] {
  // Future: useQuery(["sims"], () => fetch("/sims").then(r => r.json()))
  return SIMS;
}

export function getSim(id: SimId): Sim | undefined {
  return SIMS.find((s) => s.id === id);
}
```

Why a hook (not a constant import) — the day you move pricing to the server, the call sites don't change. They already call `useSimRegistry()`.

---

## Pattern B — Canvas heatmap overlay on MapLibre

**Use when:** you have a single result grid (one tile, one analysis) and want it on a basemap fast.

**Skip when:** you're rendering 20+ tiles at once or need GPU picking. Then reach for deck.gl's `BitmapLayer` — but that's a 2x time investment.

A standalone MapLibre pattern — paint to an offscreen `<canvas>`, register as an `image` source, add as a raster layer. (Production apps with many tiles or GPU picking reach for deck.gl's `BitmapLayer` instead; for a single result the MapLibre primitive is simpler.)

```tsx
// src/components/HeatmapLayer.tsx
import { useEffect } from "react";
import maplibregl from "maplibre-gl";

type Result = {
  grid: number[][];            // [rows][cols]
  bounds: [number, number, number, number]; // [w, s, e, n]
  minLegend: number | null;
  maxLegend: number | null;
};

function colorRamp(t: number): [number, number, number] {
  // t in [0,1] — simple yellow→red, swap for d3-scale or your design system
  const r = 255;
  const g = Math.round(255 * (1 - t));
  const b = 0;
  return [r, g, b];
}

function gridToDataUrl(r: Result): string {
  const rows = r.grid.length;
  const cols = r.grid[0].length;
  const canvas = document.createElement("canvas");
  canvas.width = cols; canvas.height = rows;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(cols, rows);
  const flat = r.grid.flat();
  const min = r.minLegend ?? flat.reduce((a, b) => (a < b ? a : b), Infinity);
  const max = r.maxLegend ?? flat.reduce((a, b) => (a > b ? a : b), -Infinity);
  const span = max - min || 1;
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const t = (r.grid[y][x] - min) / span;
      const [R, G, B] = colorRamp(Math.max(0, Math.min(1, t)));
      const i = (y * cols + x) * 4;
      img.data[i] = R; img.data[i+1] = G; img.data[i+2] = B; img.data[i+3] = 180;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL("image/png");
}

export function HeatmapLayer({ map, result, id = "heatmap" }: {
  map: maplibregl.Map; result: Result; id?: string;
}) {
  useEffect(() => {
    const apply = () => {
      const url = gridToDataUrl(result);
      const [w, s, e, n] = result.bounds;
      if (map.getSource(id)) return;
      map.addSource(id, { type: "image", url, coordinates: [[w, n], [e, n], [e, s], [w, s]] });
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": 0.7 } });
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
    return () => {
      if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(id)) map.removeSource(id);
    };
  }, [map, result, id]);
  return null;
}
```

The `result.bounds` field (added in SDK 0.4.4 and present in the REST response under `"bounds"`) is **what you place the image at** — not your polygon bounds. The grid has a NE padding margin that `result.bounds` already accounts for.

---

## Pattern C — KPI cards (3-col grid)

**Use when:** you want to show 3–6 summary numbers from a result. Same shape works for any analysis.

**Skip when:** you need delta vs baseline (then add a second value + colour).

A standalone 3-col grid; doesn't try to match the platform's `KpiCard` data shape — keep your summary flat for hackathon scope.

```tsx
// src/components/KpiCards.tsx
type Summary = Record<string, { mean: number; min: number; max: number; unit: string }>;

const fmt = (n: number) => n.toFixed(1);

export function KpiCards({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {Object.entries(summary).map(([key, s]) => (
        <div key={key} className="rounded border border-slate-200 p-3 bg-white">
          <div className="text-xs uppercase tracking-wide text-slate-500">{key}</div>
          <div className="text-lg font-medium text-slate-900">
            {fmt(s.mean)} <span className="text-xs text-slate-500">{s.unit}</span>
          </div>
          <div className="text-xs text-slate-400">{fmt(s.min)} – {fmt(s.max)}</div>
        </div>
      ))}
    </div>
  );
}
```

Compute `summary` on the client from `result.grid` — for a hackathon there's no reason to push that to the backend:

```ts
function summarise(grid: number[][], unit: string) {
  const flat = grid.flat().filter(Number.isFinite);
  const mean = flat.reduce((a, b) => a + b, 0) / flat.length;
  return {
    mean,
    min: flat.reduce((a, b) => (a < b ? a : b), Infinity),
    max: flat.reduce((a, b) => (a > b ? a : b), -Infinity),
    unit,
  };
}

const summary = { "Sun hours": summarise(result.grid, "h/day") };
```

---

## Pattern D — Scenario switcher with Zustand

**Use when:** you have 2–4 preset variants (Baseline / Hot day / Cold day / Proposed design) and want the run trigger to re-fire on change.

**Skip when:** you have more than 4 scenarios or each scenario has many tunable parameters. For 2–4 scenarios a `<select>` is enough. If you need tabbed cards with parameter tweaks per scenario, build it; that's a 2-day feature, not a 2-hour one.

```ts
// src/stores/scenario.ts
import { create } from "zustand";

export type ScenarioId = "baseline" | "hot" | "cold";

interface ScenarioState {
  scenario: ScenarioId;
  setScenario: (s: ScenarioId) => void;
}

export const useScenario = create<ScenarioState>()((set) => ({
  scenario: "baseline",
  setScenario: (scenario) => set({ scenario }),
}));
```

```tsx
// src/components/ScenarioPicker.tsx
import { useScenario } from "@/stores/scenario";

const LABELS: Record<string, string> = {
  baseline: "Baseline (today)",
  hot: "Hot summer day",
  cold: "Cold winter day",
};

export function ScenarioPicker() {
  const { scenario, setScenario } = useScenario();
  return (
    <select
      value={scenario}
      onChange={(e) => setScenario(e.target.value as any)}
      className="rounded border border-slate-300 px-2 py-1 text-sm"
    >
      {Object.entries(LABELS).map(([id, label]) => (
        <option key={id} value={id}>{label}</option>
      ))}
    </select>
  );
}
```

And in your query layer, key the cache on scenario so React Query re-fetches on switch:

```ts
const { scenario } = useScenario();
const result = useQuery({
  queryKey: ["sun-hours", lat, lon, scenario],
  queryFn: () => fetchSunHours({ lat, lon, scenario }),
});
```

The backend translates scenario → time-period / weather / geometry overrides.

---

## Putting it together — minimal app shape

```tsx
// outline only — wire `result`, `summary`, `map`, `mapContainerRef`, and your fetch logic per your chosen pattern.
// src/routes/run.tsx
import { useState } from "react";
import { useSimRegistry } from "@/data/sim-registry";
import { useScenario } from "@/stores/scenario";
import { ScenarioPicker } from "@/components/ScenarioPicker";
import { KpiCards } from "@/components/KpiCards";
import { HeatmapLayer } from "@/components/HeatmapLayer";

export function RunPage() {
  const sims = useSimRegistry();
  const [simId, setSimId] = useState(sims[0].id);
  // ... map ref, useQuery for the result, summarise() for KPIs ...
  return (
    <div className="flex h-screen">
      <aside className="w-64 border-r p-4 space-y-3">
        <select value={simId} onChange={(e) => setSimId(e.target.value as any)}>
          {sims.map((s) => <option key={s.id} value={s.id}>{s.icon} {s.name}</option>)}
        </select>
        <ScenarioPicker />
        {result && <KpiCards summary={summary} />}
      </aside>
      <main className="flex-1" ref={mapContainerRef} />
      {result && map && <HeatmapLayer map={map} result={result} />}
    </div>
  );
}
```

That's ~150 lines of view code for a full demo: pick a sim, pick a scenario, see KPIs + heatmap.

## Pitfalls

- **Re-painting the canvas every frame** — `gridToDataUrl` is the expensive bit; memoise with `useMemo(() => gridToDataUrl(result), [result])` and only rebuild the source when the URL changes.
- **Reading `result.bounds` wrong** — wire format is `[west, south, east, north]`. MapLibre's `image` source `coordinates` field is `[[w,n],[e,n],[e,s],[w,s]]` — note the corner order.
- **State that survives reload** — `zustand/middleware/persist` saves scenario choice to localStorage. Trivial to add.
- **Map cleanup** — always `removeLayer` then `removeSource` in the effect cleanup, in that order, or MapLibre throws "source still in use."
- **Cost display vs reality** — `pricePerTile` in the registry is for UI only. Real billing happens in your backend / Infrared's metering. Don't enforce limits in the browser.

## See also

- Backend that serves these patterns: [`python-fastapi-railway.md`](python-fastapi-railway.md)
- Direct-from-Node calls without a Python backend: [`typescript-direct-api.md`](typescript-direct-api.md)
- Generate a frontend with AI instead of writing one: [`lovable-frontend.md`](lovable-frontend.md)
- Result grid orientation and legend bounds: [`../interpretation/grid-conventions.md`](../interpretation/grid-conventions.md)
