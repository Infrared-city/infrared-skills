# Long runs: save, resume, retry, webhooks

Most apps need only `run_area_and_wait` (`runAreaAndWait`). It tiles, uploads, submits,
polls and merges. Read this page when a run must survive a restart, a deploy or a closed tab.

Reference: [Python client](https://infrared.city/docs/sdk/1.0/python/sdk/index.md),
[tiling](https://infrared.city/docs/sdk/1.0/python/tiling/index.md),
[webhooks](https://infrared.city/docs/sdk/1.0/python/webhooks/index.md),
guide chapter "Cost and retry" in <https://infrared.city/docs/sdk/1.0/sdk.md>.

## Which call?

| Situation | Call |
|---|---|
| Script, notebook, server thread that can wait | `run_area_and_wait(...)` with `on_progress=` |
| Run must survive a process restart | `run_area(...)`, save the schedule, then `check_area_state` and `merge_area_jobs` |
| You want a push when a job ends | `webhook_url=` on either call, plus your own receiver |

Do not write your own poll loop around single jobs. The SDK asks for the status of up to
50 jobs in one request and backs off on 429 and 5xx. Your own loop only adds requests.

## The blocking call, with progress

```python
from infrared_sdk import InfraredClient, AreaRunError

client = InfraredClient()                                   # one client per process

def on_progress(state):                                     # AreaState, called while the SDK polls
    print(f"{state.succeeded}/{state.total} jobs done")

try:
    result = client.run_area_and_wait(request, polygon, buildings=buildings,
                                      on_progress=on_progress)
except AreaRunError as exc:                                 # a tile failed twice: no map with holes
    print(len(exc.failed_jobs), "job(s) failed")
```

- A failed tile is sent again one time (`retries=1`). Do not wrap the call in a second retry loop.
- `AreaTimeoutError` (after `area_timeout`, default 3600 s) carries `exc.area_state`.
  The jobs continue to run and are billed. Do not send the run again. Resume it (below).

## Run ids and resume

`run_area` submits every tile and returns an `AreaSchedule` at once. The schedule is your
run record: it holds the job id of each tile. Save it, and any process can finish the run.

```python
import json
from infrared_sdk import AreaSchedule

# 1. Submit. on_accepted stores each job id at once, so a crash during the
#    submit loses nothing. The SDK calls it from its submit threads.
schedule = client.run_area(request, polygon, buildings=buildings,
                           on_accepted=lambda job_id, tile: db.add_job(run_key, job_id, tile))
db.save_schedule(run_key, json.dumps(schedule.to_dict()))   # plain JSON

# 2. Later, maybe in another process: load it and check it.
schedule = AreaSchedule.from_dict(json.loads(db.load_schedule(run_key)))
known: dict = {}                                            # finished jobs are not asked again
state = client.check_area_state(schedule, known=known)
print(state.status, state.succeeded, state.failed, state.total)

# 3. All jobs ended: merge. Some failed: send only those again.
if state.is_complete and state.failed == 0:
    result = client.merge_area_jobs(schedule)
elif state.is_complete:
    schedule = client.run_area(request, polygon, buildings=buildings,
                               retry_from=schedule, known=known)
```

Rules:

- **Same inputs on a retry.** `retry_from` checks the request, the weather, the buildings and
  the other site inputs against the saved schedule. A different input raises `ValueError`.
- **One request per schedule.** `run_area([a, b], ...)` returns two schedules. Save and retry
  each one separately.
- **`failed_submissions`** are tiles whose submit failed. `retry_from` sends them again.
  **`uncertain_submissions`** can already have a job. The SDK does not send them again.
- **Ctrl-C or a stopped thread** during the submit raises with `exc.partial_schedule`.
  Give it to `retry_from=`. The SDK does not send again the tiles that the server accepted.
- **Facade and roof runs:** merge in the process that submitted. Another process gets the
  values, but `columns.render_buffers()` then needs the saved layout ("Serve many users" in the guide).
- **A schedule that you will not merge:** call `client.forget_schedule(schedule)`.
- **A schedule is not a result.** When the run is done, store the result
  (`result.to_dict()`). See [recipes/persistence-and-users.md](recipes/persistence-and-users.md).

TypeScript has the same steps: `runArea`, `checkAreaState`, `mergeAreaJobs`,
`retryFrom`, `onAccepted`, and `areaScheduleToJSON` / `areaScheduleFromJSON` to save a schedule.

## Idempotency: what is billed

- Each job has an idempotency key. If a submit gets no answer, the SDK sends the same key
  again, and the server returns the job that it has. You do not pay two times.
- A failed or refused job gets a new key on a retry. That is a new, billed job.
- The server has **no result cache**. The same run again is billed again. Cache in your app:
  hash every input and reuse the stored result
  ([recipes/persistence-and-users.md](recipes/persistence-and-users.md)).
- **HTTP 402 (no credits):** the SDK stops the submit and sets
  `schedule.submission_abort_status = 402`. Tiles that it sent before can still run and bill.
  Add credits, then use `retry_from=schedule`.

## Webhooks

SDK 1.0 supports webhooks. A webhook tells your server that a job ended. It does not
carry the result: you still merge with the SDK.

```python
from infrared_sdk import WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED

HOOK = "https://your-app.example/hooks/infrared"
client.webhooks.register(HOOK, "production")                # one time; "development" for tests

schedule = client.run_area(request, polygon, buildings=buildings, webhook_url=HOOK,
                           webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED])
```

Receiver (FastAPI here, any framework works):

```python
@app.post("/hooks/infrared")
async def infrared_hook(request: Request) -> dict:
    body = await request.body()                             # raw bytes, before any JSON parse
    # Standard Webhooks v1. WEBHOOK_SECRET is the "whsec_..." signing secret; keep it on the server.
    if not client.webhooks.verify_signature(body, dict(request.headers), WEBHOOK_SECRET):
        raise HTTPException(400, "bad signature")
    events.put(json.loads(body))                            # answer fast; work in the background
    return {"ok": True}
```

- One event for each job. A run of 3 analyses over 20 tiles sends 60 events in a short burst.
  Buffer them, then call `check_area_state` one time for the schedule. Do not merge per event.
- A delivery can come two times. Make the handler idempotent: store the `webhook-id` header.
- With `run_area_and_wait`, `webhook_url` only adds events. The call still blocks.

## See also

- [python/errors-and-retries.md](python/errors-and-retries.md): every error type.
- [throughput-and-limits.md](throughput-and-limits.md): jobs per second, tile caps, tokens.
- [building-fast-apps.md](building-fast-apps.md): one client, preview first, let the SDK poll.
