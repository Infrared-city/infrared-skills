# Building fast apps on the SDK

Patterns for an app that serves many users and feels instant. They come from a production
platform built on the SDK. Link, do not copy: the exact calls are in the docs.

- Guide chapters "Where it runs", "Serve many users" and "Cost and retry":
  <https://infrared.city/docs/sdk/1.0/sdk.md>
- Python backend app recipe: [recipes/python-fastapi-app.md](recipes/python-fastapi-app.md)
- TypeScript: [typescript/quickstart.md](typescript/quickstart.md),
  [typescript/map-grid.md](typescript/map-grid.md), [typescript/facades-3d.md](typescript/facades-3d.md),
  [typescript/cloudflare-proxy.md](typescript/cloudflare-proxy.md)

## 1. One client, one worker, one core

Make the client once. Start the Rust core once. Do not make a new client for each click.

```ts
// TypeScript, Node: once per process
await initializeCore();                       // a second call is safe: the SDK ignores it
export const client = new InfraredClient({ apiKey: process.env.INFRARED_API_KEY });
```

In a browser, run the SDK in one Web Worker for each signed-in session (`serveSdkWorker`,
`createWorkerClient`). The worker does the heavy work. The page stays free.
End the worker at sign-out and when the user changes. One worker for each identity.
In Python, keep one `InfraredClient` for each process.

```python
# Python: module level, not inside a request handler
client = InfraredClient()
```

A second client holds the geometry again and uses more memory.

## 2. Keep the geometry upload links (and clear them at sign-out)

The SDK uploads the geometry of each tile once and reuses the link for every analysis on that tile.
In Python the links stay in the process memory for about 24 hours.
In a browser, a reload makes a new worker, which would upload again.
Give the client a persistent `geometryUrlStore` (IndexedDB) so the same geometry skips the upload,
also after a reload.

```ts
const geometryUrlStore = {
  async get(key: string) { return await idbGet(key); },          // { url, expiresAt } or undefined
  async set(key: string, url: string, expiresAt: number) { await idbPut(key, { url, expiresAt }); },
};
serveSdkWorker({ geometryUrlStore });
```

The links are read links to your users' geometry. They are secrets. **Delete the store at sign-out.**
An entry lasts 23 hours. A refused link is uploaded again by the SDK.

## 3. Let the SDK poll

Do not write a poll loop. `runAreaAndWait` (`run_area_and_wait`) asks for the status of up to
50 jobs in one request, starts at 0.5 s, then every 1 s, and after 10 s every 2 s. It backs off on
429 and 5xx. A loop of your own sends more requests and costs more. In a worker split
(`runArea` in the worker, `mergeAreaJobs` after), poll with a plain client on the page.

## 4. Preview before you run

Preview is free and local. It sends no job. Show the user the tiles, the jobs and the cost first.

```python
preview = client.preview_area(polygon, payload=request, buildings=buildings)
print(preview.would_bill_jobs, preview.estimated_cost_tokens)     # price from would_bill_jobs
```

```ts
const plan = await client.previewAreaBatches(input, polygon, { buildings });
console.log(plan.plannedJobCount);          // same input and layers as the run
```

Preview one analysis at a time and add the results. Always pass the analysis, or the preview
prices the wind grid.

## 5. Several analyses on one geometry

Pass a list of requests in one call. Analyses of one grid family share the geometry upload.
That saves time. The job count stays the same.

```python
sky, solar = client.run_area_and_wait([svf_request, solar_request], polygon, buildings=buildings)
```

## 6. Helpers, then the colour scale

Never decode the stored type yourself. Always use the helper, then map values to colours with one fixed scale for each analysis.

| Result | Python | TypeScript |
|---|---|---|
| Ground grid | `result.physical_grid()` | `areaGridValuesF32(result)` |
| Facades and roofs | `result.columns.render_buffers()` | `surfaceRenderBuffers(columns)` |
| Legend | `result.min_legend`, `legend_range(...)` | `result.minLegend`, `legendRange(...)` |

Cache decoded buffers. Do not decode on each mouse move. Colour rules:
[recipes/rendering-results-well.md](recipes/rendering-results-well.md).

## 7. Baked samples for an instant first paint

At build time, run the SDK once for a sample site and save the result as a static file.
On page open, load the file. The user sees a map at once and pays no job.
Use the same call that the live run uses, so a baked file proves the live path works.
When the user presses Run, the live result replaces the baked one.

```python
# bake.py: run in CI or by hand, then ship the file with the app
import numpy as np
result = client.run_area_and_wait(request, sample_polygon, buildings=sample_buildings)
np.savez_compressed("public/samples/svf.npz", grid=result.physical_grid(), bounds=result.bounds)
```

## 8. Batch reads

Merge many small reads into one. A pin, hover or sample read for 50 points is one request, not 50.
Read geometry and values in parallel, and read ahead the numbers that the user will ask for next.

## 9. Bounded retries, then fail loud

Retry a transfer a few times with backoff, then show the error. The SDK already retries
transport errors and sends failed tiles again once (`retries=1`). Do not wrap it in a second
retry loop. Do not send a run again after a worker crash before you check whether a job exists:
a paid job can be running. See [python/errors-and-retries.md](python/errors-and-retries.md).

## 10. Protect the key with a proxy

Never send the API key to a browser. Put a small proxy on your own origin. It checks that the user
is signed in, can count a quota, adds `X-Api-Key`, and forwards to the API. It also relays the
storage links for upload and download. Recipe: [typescript/cloudflare-proxy.md](typescript/cloudflare-proxy.md).

## 11. Clean up

- Drop schedules that you will not merge: `client.forget_schedule(schedule)`
  (`client.jobs.captures.forgetSchedule`).
- At exit: `client.close()` (Python), `client.jobs.captures.free()` (TypeScript).
- A merge of a very large site uses much memory for a short time. Run one or two merges at a time.
- On Node 22 or later, `initializeCore({ threads: 4 })` speeds up big merges. Not in a browser.
