# Setup and the run model

Read this page first. It tells you where the SDK sends jobs, what goes into one run, and what
comes back. Every example on the design pages uses the same shape.

![One run: request fields, call arguments, tiles, jobs, grid](images/run-model.svg)

## 1. Install, key, base URL

```bash
pip install infrared-sdk                       # Python 3.9+
npm install @infrared-city/infrared-sdk        # TypeScript, Node 18+
export INFRARED_API_KEY=...                    # never in code, never in a repo, never in a log
```

The SDK sends jobs to **production** when you set nothing. To use another environment, set the
base URL. The order is: constructor argument, then the environment variable `INFRARED_BASE_URL`,
then the default.

| Environment | Base URL | Note |
|---|---|---|
| Production (default) | `https://api.infrared.city/v2` | Bills your production account |
| Staging (test) | `https://api-test.infrared.city` | **No `/v2`.** Needs a staging key |

```python
client = InfraredClient(base_url="https://api-test.infrared.city")   # staging
```

```ts
const client = new InfraredClient({ apiKey: process.env.INFRARED_API_KEY, baseUrl: "https://api-test.infrared.city" });
```

- `https://api-test.infrared.city/v2` is wrong. It gives an HTTP 404 or "does not advertise
  binary transport". Remove `/v2`.
- Before the first run, print the base URL of the client and say it to the user. One tester ran
  on production by mistake: there the installations were dropped or refused.
- Keys are per environment. Ask the user which key and which environment to use.

## 2. One run

```python
result = client.run_area_and_wait(request, polygon, buildings=..., vegetation=..., ground_materials=...)
```

| Goes in | What | Where |
|---|---|---|
| The request (payload) | `analysis_type`, weather and `time_period`, `installations`, `physics`, `analysis_surfaces`, comfort materials | Fields of the request object |
| The call | `polygon` (lon/lat), `buildings`, `vegetation`, `ground_materials` | Arguments of `run_area_and_wait` |

**`installations` goes on the request, not on the call.** `run_area_and_wait(..., installations=...)`
raises `TypeError`. In TypeScript: `{ ...request, installations }` as the first argument;
`buildings` goes in the options (third argument).

What the SDK does for you:

1. It cuts the polygon into 512 m tiles and skips empty tiles.
2. It uploads the geometry one time and sends one job for each tile and analysis.
   **One job = one tile x one analysis = one billed job.**
3. It polls, downloads and merges. A failed tile is sent again one time; a tile that still fails
   raises `AreaRunError` (never a map with holes).

**Cache.** The server keeps a result for 24 hours, keyed by the request body. The same body
again is a cache hit: no new job, the same numbers. To test a change, change the body (one
input). Two identical runs do not prove that a setting works.

**Preview first.** `client.preview_area(polygon, payload=request, buildings=buildings)` is
free and local. Read `would_bill_jobs` and `estimated_cost_tokens`. Always pass `payload=`:
without it the preview prices a wind run.

## 3. What comes back

| You asked for | You get | Read it with |
|---|---|---|
| Ground grid (default) | `AreaResult`: one grid of 1 m cells for each 512 m tile, merged | `result.physical_grid()` (2-D, row 0 = south) |
| Facades and roofs (`analysis_surfaces`) | `SurfaceAnalysisResult` | `result.columns`, `columns.physical_values()` |
| PV pieces in a solar-radiation run | `result.pv_yield` | `pv_yield["entries"][id]` |
| What the server changed | `result.warnings` (list of texts, `CODE: ...`) | [warnings-and-refusals](warnings-and-refusals.md) |

- The grid covers the whole tile, not only your polygon. A small site is a 512 x 512 grid that
  is mostly NaN. NaN = no value (outside the site, or no sensor).
- Place the grid with `result.bounds` = `(west, south, east, north)` in degrees. Do not compute
  the extent yourself.
- Ground cells under buildings can be NaN or 0. Mask them before a mean or a minimum.
- **Crop to a polygon** (the court, the street) before you report a number. The helper
  `cell_mask(result, polygon)` is in [recipes/compare-and-derive](recipes/compare-and-derive.md).
- Two runs on the same polygon give the same grid: compare cell by cell. Check that
  `result_a.bounds == result_b.bounds`.

## 4. Time and cost hints

Measured on staging, one tile, 2026-10-20 (SDK 1.1.4.dev2):

| Run | Wall time |
|---|---|
| UTCI, 5 hours, 4 buildings, trees, ground, 9 installations | 1.5 to 5.5 s |
| Sky view factor, ground | 1.4 s |
| Solar radiation, one year, ground + facades + roofs | 1.6 to 2.3 s |

The price comes from the job count (`would_bill_jobs`). A larger polygon gives more tiles, so
more jobs. Facade runs can split into more jobs: preview with
`buildings=`.

Next: [analyses-at-a-glance](analyses-at-a-glance.md), [design-variants](design-variants.md),
[recipes/compare-and-derive](recipes/compare-and-derive.md), [agent-workflow](agent-workflow.md).
