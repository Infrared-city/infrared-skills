# Threads and workers in the TypeScript SDK

Use this page to decide where the SDK work runs. The work is mostly
local CPU: build the site, plan the tiles, encode the geometry, merge the
results. The cloud does the simulation.

Short answer: run one SDK client in one place. Add threads only for very
large facade runs. Do not run the SDK in many processes.

## The default: one event loop (Node)

- `await initializeCore()` loads the WASM core once per process.
- The core runs on the main thread. Network calls (upload, submit, poll,
  download) do not block the event loop. The CPU steps do.
- For a script or a server job, this is fast enough. A 20 km² ground run
  plans in about 3 seconds on one core.

## Threaded core (Node 22 or later)

```ts
import { initializeCore, InfraredClient } from "@infrared-city/infrared-sdk-ts";

// Call once, before any other SDK call. A process holds one core,
// so a second call with another thread count is refused.
await initializeCore({ threads: 4 });

const client = new InfraredClient({ apiKey: process.env.INFRARED_API_KEY });
```

- `threads` above 1 loads the threaded core from `generated-threads/` in the
  package (1.0.0 ships it). The SDK starts a pool of worker threads.
- The results are byte-identical to the serial core.
- Node 20 cannot start the pool. The call is refused there.
- The browser and worker entry points refuse `threads` above 1.

### When it helps

Threads speed up the parallel CPU steps: planning and merging facade runs.
They do not speed up ground runs, small areas or the cloud time.

Measured on one 32-core machine, Node 22, about 24 km² of a dense city
(about 68,000 buildings, facades planned offline with `previewAreaBatches`,
no API cost). Median of two runs:

| Step | `threads` 1 | `threads` 4 | `threads` 8 |
|---|---|---|---|
| Facade plan, 127 jobs, 18 million sensors | 8.7 s | 4.2 s | 3.4 s |
| Ground plan, 81 tiles | 3.2 s | 3.1 s | 3.1 s |
| Start-up of `initializeCore` | 0.04 s | 0.1 s | 0.1 s |
| Peak memory of the process | 0.86 GB | 0.78 GB | 0.85 GB |

The SDK README reports a similar gain for the facade merge: a 4 km facade
merge takes 5.5 s instead of 10 s. It names 4 threads as the best value
for the merge, and 8 as slower. Start with 4. Measure 8 on your own data.

### Costs and risks

- Start-up cost is small (about 0.1 s). Memory is about the same
  as the serial core in the plan test; the README gives about 10 % more for a merge.
- **A failure on a pool thread ends the whole process.** The core writes one
  JSON line to stderr (`infrared_core_worker_failed`) and the process
  stops. This includes running out of WASM memory near the 4 GiB limit.
  The serial core throws a normal error instead.
- So run a threaded job where a restart is acceptable. Keep the input well
  below the memory limit. Split very large areas.
- Do not also run the SDK inside your own worker pool. Use one level of
  parallelism only.

## Your own worker_threads or processes

Each worker thread and each process has its own WASM core. It also has its
own cache of prepared sites and uploaded geometry. The caches are not
shared.

- A second process uploads the same geometry again. It pays the cold-run time
  again, and it uses more memory (a site costs tens of MB to 1 GB).
- Each client also polls. Two clients double the status requests that count
  against your account rate limit (see `../throughput-and-limits.md`).
- A handle never crosses a thread. Send bytes, not SDK objects.

So prefer ONE SDK instance per process. Run one process per account.
To serve many users, queue the runs in that one process. The SDK
reuses uploads between the runs there.

## Browser: one Web Worker

An `async` function does not move CPU work off the page. A big area still
freezes the UI if it runs on the main thread.

Run the SDK in ONE Web Worker. The package has a helper for this
(`@infrared-city/infrared-sdk-ts/worker`):

```ts
// sdk.worker.ts: the whole worker file
import { serveSdkWorker } from "@infrared-city/infrared-sdk-ts/worker";
serveSdkWorker();

// page
import { createWorkerClient } from "@infrared-city/infrared-sdk-ts/worker";
const sdk = createWorkerClient({
  worker: new Worker(new URL("./sdk.worker.ts", import.meta.url), { type: "module" }),
  module,              // WebAssembly.Module, compiled once on the page
  config: { baseUrl }, // plain, cloneable client settings only
  getToken,            // runs on the page, never in the worker
});
const schedule = await sdk.runArea(input, polygon, { onProgress });
const result = await sdk.mergeAreaJobs(schedule); // grid buffer is transferred
```

- One worker serves one client. Use one worker per signed-in session.
- Result buffers move by transfer, not by copy. Do not read a buffer after
  you send it.
- Poll with a plain `InfraredClient` on the page. This keeps the status
  calls light.
- A browser app needs a same-origin proxy to the API. See the SDK README.

### Threads in the browser need isolation

Threaded WASM needs `SharedArrayBuffer`. A page gets it only with these
headers (cross-origin isolation):

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

The headers block cross-origin images, scripts and frames that do not opt
in. They also break some pop-up sign-in flows. The SDK does not need them:
`initializeCore` refuses `threads` above 1 in the browser. Use one Web
Worker instead.

## Comparison

| Option | UI stays smooth | Speed-up | Memory | Risk |
|---|---|---|---|---|
| Main thread (browser) | No, freezes on big areas | None | Lowest | Frozen page |
| One Web Worker | Yes | Off-thread, no gain in speed | One core | Low. Recommended in a browser |
| Node, serial core | n/a | Baseline | One core | Low. Default in Node |
| Node, threaded core (`threads: 4`) | n/a | About 2x on facade plan and merge | Slightly higher | A pool failure ends the process |
| Many processes or workers | Yes | Little: each uploads again and polls again | N cores, N caches | More requests, more rate-limit use |

## See also

- Rate limits and speed indicators: `../throughput-and-limits.md`
- SDK guide: https://infrared.city/docs/sdk/
