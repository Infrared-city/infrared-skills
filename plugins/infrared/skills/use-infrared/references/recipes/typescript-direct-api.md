# Recipe: TypeScript via Direct API (no SDK)

For TypeScript / Node.js / Bun / Workers code that needs Infrared results today, while the official TS SDK (`@infrared-city/infrared-sdk-ts`) is still pre-publish. Hit the public REST API directly with `fetch`. Same auth, same job lifecycle, same payload shapes the Python SDK uses — just without the typed client.

## When to use this

- You want a Next.js / Astro / Hono / Worker route that returns an Infrared result and don't want a Python service in the loop.
- You're prototyping a hackathon demo and pulling in a Python wrapper is overkill.
- You already have a Node backend and want to add one analysis endpoint.

**When *not* to use this:** complex workflows with polygon tiling, multi-tile blending (especially `wind-speed`), or webhook delivery. Use the Python SDK (`pip install infrared-sdk`) — it owns the tile orchestration. From TypeScript you can either wait for the TS SDK port or proxy through a small FastAPI service (see [`python-fastapi-railway.md`](python-fastapi-railway.md)).

## Target Stack

- TypeScript 5+ on Node 20+, Bun 1+, or Cloudflare Workers.
- `fetch` (built-in). No SDK needed.
- `fflate` (browser/Worker/Node) for unzipping results.

## Secrets

- `INFRARED_API_KEY` lives **server-side only** — never in browser-bundled code.
- In a Next.js app, keep the key in a route handler (`app/api/.../route.ts`), not a client component.
- In a Worker, set it via `wrangler secret put INFRARED_API_KEY`.
- In **Node**, read it as `process.env.INFRARED_API_KEY`.
- In **Workers**, read from the `env` binding passed to your `fetch` handler — `process.env` only works with `nodejs_compat` + `nodejs_compat_populate_process_env` flags (auto-enabled for compat dates ≥ 2025-04-01). Prefer passing `env.INFRARED_API_KEY` explicitly via a constructor argument (see the minimal client below).

**Browser calls fail twice:** CORS blocks them (API origin doesn't whitelist arbitrary browsers), and any key shipped to the browser is leaked. Always route through your own server.

## API surface

Base URL: `https://api.infrared.city/v2`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/async/{analysis-type}` | Submit a job. Returns `{ jobId }`. |
| `GET`  | `/async/jobs/{jobId}` | Poll status. Returns `{ jobStatus, ... }` (PascalCase value). |
| `GET`  | `/async/jobs/{jobId}/results` | Get `Link` header with presigned S3 URL; download ZIP archive. |

Auth header: `X-Api-Key: <INFRARED_API_KEY>`. Never `Authorization: Bearer`.

### The kebab-case gotcha

The REST wire format uses **kebab-case** for field names. The Python SDK accepts snake_case in code and converts; from raw TypeScript you write kebab-case directly.

```ts
// ❌ Wrong — won't deserialize server-side
{ analysisType: "direct-sun-hours", timePeriod: { startMonth: 7 } }

// ✅ Right
{ "analysis-type": "direct-sun-hours", "time-period": { "start-month": 7 } }
```

Same for enum values: `"direct-sun-hours"`, `"wind-speed"`, `"thermal-comfort-index"`, `"pedestrian-wind-comfort"`. Always kebab.

## Minimal client (40 lines)

A thin, copy-pasteable wrapper. Works in Node, Bun, and Workers.

```ts
// infrared.ts
const BASE = "https://api.infrared.city/v2";

export class InfraredError extends Error {
  constructor(message: string, public status?: number, public body?: unknown) {
    super(message);
  }
}

// Pass apiKey explicitly in Workers (from env binding); falls back to process.env in Node.
export function createClient(config: { apiKey?: string } = {}) {
  function resolveKey(): string {
    const key = config.apiKey ?? (typeof process !== "undefined" ? process.env.INFRARED_API_KEY : undefined);
    if (!key) throw new InfraredError("INFRARED_API_KEY not set");
    return key;
  }

  async function call(path: string, init: RequestInit = {}): Promise<Response> {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "X-Api-Key": resolveKey(),
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) {
      throw new InfraredError(
        `Infrared ${init.method ?? "GET"} ${path} → ${res.status}`,
        res.status,
        await res.text().catch(() => null),
      );
    }
    return res;
  }

  async function submit(
    analysisType: string,
    body: Record<string, unknown>,
  ): Promise<string> {
    const res = await call(`/async/${analysisType}`, {
      method: "POST",
      body: JSON.stringify({ "analysis-type": analysisType, ...body }),
    });
    const { jobId } = (await res.json()) as { jobId: string };
    return jobId;
  }

  async function waitFor(
    jobId: string,
    { pollMs = 3000, timeoutMs = 300_000 } = {},
  ): Promise<void> {
    const start = Date.now();
    while (true) {
      const res = await call(`/async/jobs/${jobId}`);
      const { jobStatus } = (await res.json()) as { jobStatus: string };
      if (jobStatus === "Succeeded" || jobStatus === "Succeded") return; // server returns both spellings historically
      if (jobStatus === "Failed") throw new InfraredError(`Job ${jobId} failed`);
      if (Date.now() - start > timeoutMs) throw new InfraredError(`Job ${jobId} timed out`);
      await new Promise((r) => setTimeout(r, pollMs));
    }
  }

  async function downloadResults<T>(jobId: string): Promise<T> {
    const linkRes = await call(`/async/jobs/${jobId}/results`);
    const linkHeader = linkRes.headers.get("Link") ?? "";
    const match = linkHeader.match(/<([^>]+)>/);
    if (!match) throw new InfraredError("No Link header on results response");
    const presignedUrl = match[1];
    const zipRes = await fetch(presignedUrl);
    const zipBuf = new Uint8Array(await zipRes.arrayBuffer());
    // Unzip — fflate works in browser, Workers, Node, and Bun.
    const { unzipSync, strFromU8 } = await import("fflate");
    const files = unzipSync(zipBuf);
    // Result JSON is typically at "result.json" or the only .json in the archive
    const key = Object.keys(files).find((k) => k.endsWith(".json"));
    if (!key) throw new InfraredError("No JSON in result archive");
    return JSON.parse(strFromU8(files[key])) as T;
  }

  return { submit, waitFor, downloadResults };
}

// Convenience default export for Node usage (reads process.env automatically):
export const { submit, waitFor, downloadResults } = createClient();
```

## Result download flow

The real flow for `/async/jobs/{jobId}/results`:
1. `GET /async/jobs/{jobId}/results` returns a `Link: <presigned-S3-URL>; rel="results"` header (not a body).
2. The presigned S3 URL serves a **ZIP archive** (not gzip JSON).
3. Unzip the archive to get `result.json`.

`fflate` handles the unzip and works in browser, Workers, Node, and Bun — see `downloadResults` in the minimal client above. Add it to your project with `npm add fflate`.

## Worked example — direct sun hours on a single tile

A 512 m × 512 m tile centred on Vienna's Rathausplatz. Single-tile means no polygon, just `latitude` + `longitude`.

Note: `direct-sun-hours` and `daylight-availability` require a **single-month** time period — multi-month windows return HTTP 400 silently.

```ts
import { submit, waitFor, downloadResults } from "./infrared";

type SunHoursResult = Record<string, unknown>;
// After unzipping, inspect the JSON to see the actual field names:
// console.log(Object.keys(r));

async function main() {
  const jobId = await submit("direct-sun-hours", {
    latitude: 48.2107,
    longitude: 16.3589,
    "time-period": {
      "start-month": 7, "start-day": 1,  "start-hour": 8,
      "end-month":   7, "end-day":   31, "end-hour":   18,
    },
    geometries: {}, // empty = use SDK-fetched buildings for that tile
  });
  console.log("submitted", jobId);
  await waitFor(jobId, { pollMs: 5000, timeoutMs: 180_000 });
  const r = await downloadResults<SunHoursResult>(jobId);
  console.log("result keys:", Object.keys(r));
}

main();
```

Run it with `INFRARED_API_KEY=... bun run example.ts` or `tsx example.ts`.

## Field shape cheat sheet

```jsonc
// direct-sun-hours / daylight-availability / svf
// Note: direct-sun-hours and daylight-availability require a single-month window.
{
  "analysis-type": "direct-sun-hours",
  "latitude": 48.21, "longitude": 16.36,
  "time-period": { "start-month":7,"start-day":1,"start-hour":8,"end-month":7,"end-day":31,"end-hour":18 },
  "geometries": {}
}

// pedestrian-wind-comfort
{
  "analysis-type": "pedestrian-wind-comfort",
  "latitude": 48.21, "longitude": 16.36,
  "criteria": "lawson-lddc",
  "geometries": {}
}

// thermal-comfort-index (UTCI) — needs more inputs; see references/analyses/07-thermal-comfort-utci.md
```

For full payload schemas, see the per-analysis references under [`../analyses/`](../analyses/).

## Pitfalls

- **camelCase fields will silently fail** — server returns `400` or ignores the field. Always kebab.
- **`AnalysesName.WIND_SPEED` etc. don't exist over the wire** — that's a Python enum. The wire value is just the kebab string.
- **Multi-tile polygons are not supported by this recipe** — tiling, cost preview, and merge logic live in the Python SDK. For polygons, proxy through Python.
- **`wind-speed` over multiple tiles needs `directional_blend`** — even more reason to use the Python SDK for any wind polygon. Single-tile wind from this recipe is fine.
- **`[lat, lon]` vs `[lon, lat]`** — top-level `latitude` / `longitude` are scalars (order obvious). Inside GeoJSON the order is `[lon, lat]` (RFC 7946).
- **Don't store `jobId` and retry indefinitely** — jobs typically complete within seconds; if `failed` happens, inspect the status response body and surface the error.

## Upgrade path — when the TS SDK lands

When `@infrared-city/infrared-sdk-ts` ships to npm (Track A parity fixes outstanding as of writing), the above ~150 lines collapse to:

```ts
import { InfraredClient, AnalysesName } from "@infrared-city/infrared-sdk-ts";

const client = new InfraredClient(); // reads INFRARED_API_KEY env
const result = await client.runAndWait({
  analysisType: AnalysesName.DirectSunHours,
  latitude: 48.21,
  longitude: 16.36,
  timePeriod: {
    startMonth: 7, startDay: 1, startHour: 8,
    endMonth: 7,   endDay: 31,  endHour: 18,
  },
});
```

The wrapper from this recipe and the SDK share the same wire format, so payloads carry over. The big win is typed enums + multi-tile orchestration + typed error classes. Keep this recipe around for runtimes the SDK doesn't ship for (e.g., bare Workers without the bundle).

## See also

- Auth and invariants: [../00-setup.md](../00-setup.md)
- Per-analysis payloads: [../analyses/](../analyses/)
- Result interpretation (legend bounds, grid orientation): [../interpretation/grid-conventions.md](../interpretation/grid-conventions.md)
- Backend proxy in Python: [`python-fastapi-railway.md`](python-fastapi-railway.md)
