# Async & Jobs

The SDK gives you four entry points for running analyses. Picking the right one is the first decision — it determines whether your code blocks, whether you need a public webhook URL, and whether the schedule needs to be persisted between submission and merge.

- `client.run_area_and_wait()` — sync, blocks until the merged `AreaResult` is ready.
- `client.run_area()` — async, returns an `AreaSchedule` immediately. Pair with a webhook receiver or `client.check_area_state()`.
- `client.analyses.execute()` — single-tile primitive. Returns a `Job`. No tiling, no merging.
- `client.jobs.*` — single-tile lifecycle: `get_status`, `wait_for_completion`, `download_results`.

## Decision rule

| Situation                                                          | Entry point                                                       | Why                                              |
| ------------------------------------------------------------------ | ----------------------------------------------------------------- | ------------------------------------------------ |
| Notebook / interactive script, small polygon                       | `client.run_area_and_wait()`                                      | Sync, blocks until result                        |
| Long-running, large area, headless / serverless / batch            | `client.run_area()` + webhook                                     | Async, returns `AreaSchedule` immediately        |
| Multi-user backend fan-out, many polygons concurrent               | `client.run_area()` + webhook + persisted `AreaSchedule`          | One webhook stream consolidates completions     |
| No public webhook URL available                                    | `client.run_area()` + `client.check_area_state()`                 | Manual polling fallback                          |
| Single-tile job with custom polling / replay-from-queue            | `client.analyses.execute()` + `client.jobs.*`                     | Low-level primitive, advanced                    |

## The four entry points

| Method | Returns | Notes |
| --- | --- | --- |
| `run_area_and_wait(payload, polygon, *, buildings=, vegetation=, ground_materials=, job_timeout=300, area_timeout=3600, on_progress=, max_tiles_override=, max_workers=20, webhook_url=, webhook_events=)` | `AreaResult` (or `list[AreaResult]` for list payload) | Sync. `webhook_url=` streams events to a backend without changing blocking behaviour. |
| `run_area(payload, polygon, *, buildings=, vegetation=, ground_materials=, max_tiles_override=, max_workers=20, webhook_url=, webhook_events=, retry_from=)` | `AreaSchedule` (or `list[AreaSchedule]` for list payload) | Async. Submits all tiles, returns immediately. |
| `client.analyses.execute(*, payload, webhook_url=, webhook_events=)` | `Job` | Single tile. Skips tiling and area merging. |
| `client.jobs.get_status(job_id)` / `wait_for_completion(job_id, timeout=None, on_poll=)` / `download_results(job_id)` | `Job` / `Job` / `DownloadResult` | Single-tile lifecycle. |

`payload` types are the analysis request models from `infrared_sdk.analyses.types` (`WindModelRequest`, `SvfModelRequest`, etc).

## Single-tile primitives

Reach for these when you need direct control over **one** job: custom polling, replaying jobs from your own queue, debugging a specific job, or wiring webhooks at the analysis level. For anything that involves a polygon larger than one 512×512m tile, use `run_area` instead.

```python
from infrared_sdk import InfraredClient, WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED
from infrared_sdk.analyses.jobs import JobStatus

with InfraredClient() as client:
    # 1. Submit (returns immediately)
    job = client.analyses.execute(
        payload=payload,
        webhook_url="https://your-server.com/webhooks",
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )
    print(job.job_id, job.status)  # e.g. "abc-123", JobStatus.pending

    # 2a. Poll manually...
    snapshot = client.jobs.get_status(job.job_id)
    if snapshot.status == JobStatus.succeeded:
        download = client.jobs.download_results(job.job_id)

    # 2b. ...or block until terminal (raises JobFailedError on Failed)
    completed = client.jobs.wait_for_completion(job.job_id, timeout=300)

    # 2c. ...or skip polling entirely and react to the webhook delivery.

    # 3. Download results once Succeeded
    download = client.jobs.download_results(completed.job_id)
    payload_dict = client.jobs.decompress(download.content)
```

`DownloadResult` shape (frozen dataclass):

| Field           | Type    | Description                                                                |
| --------------- | ------- | -------------------------------------------------------------------------- |
| `content`       | `bytes` | Compressed result bytes (ZIP or GZIP). Pass to `client.jobs.decompress()`. |
| `presigned_url` | `str`   | Pre-signed S3 URL the content was fetched from (always populated).         |
| `job_id`        | `str`   | The job this result belongs to.                                            |
| `content_type`  | `str`   | HTTP `Content-Type` of the downloaded blob.                                |

`client.jobs.decompress(content: bytes) -> dict` is a `@staticmethod`. It auto-detects ZIP vs GZIP and returns the parsed JSON payload — exact shape depends on the analysis (e.g. an `AreaResult.to_dict()` shape for tiled jobs). Do not assume a specific top-level key.

`JobStatus` is a `StrEnum`; values match the wire format (capitalised strings):

| Value       | Wire string  | Terminal? | Description                                                              |
| ----------- | ------------ | --------- | ------------------------------------------------------------------------ |
| `pending`   | `"Pending"`  | No        | Accepted by the API, queued for execution.                               |
| `running`   | `"Running"`  | No        | Inference backend is processing it.                                      |
| `succeeded` | `"Succeeded"`| **Yes**   | Results downloadable via `client.jobs.download_results()`.               |
| `failed`    | `"Failed"`   | **Yes**   | Inspect `job.error` for the reason. `wait_for_completion` raises here.   |
| `unknown`   | `"Unknown"`  | No        | Forward-compat fallback for unrecognised statuses. Keep polling.         |

`wait_for_completion(timeout=)` defaults to 300 s, uses exponential backoff with full jitter (cap 10 s, floor 0.5 s), raises `JobTimeoutError` on timeout and `JobFailedError` on `failed`. The optional `on_poll(job, attempt, elapsed, next_delay)` callback fires on every iteration including the terminal one; return `False` to stop early.

## Async area runs with `run_area`

`run_area` performs the same tiling, layer assignment, and submission as `run_area_and_wait`, but returns an `AreaSchedule` describing in-flight jobs without blocking on completion.

```python
from infrared_sdk import InfraredClient, WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED

with InfraredClient() as client:
    area = client.buildings.get_area(polygon)

    schedule = client.run_area(
        payload,
        polygon,
        buildings=area.buildings,
        webhook_url="https://your-server.com/webhooks",
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )

    print(f"Submitted {len(schedule.jobs)} jobs "
          f"({len(schedule.failed_submissions)} submission errors)")

    # ... your webhook receiver records each job.succeeded / job.failed event ...

    # Once all jobs are terminal, merge into a single AreaResult
    result = client.merge_area_jobs(schedule)
```

### `AreaSchedule` schema

| Field                | Type                          | Description                                                                  |
| -------------------- | ----------------------------- | ---------------------------------------------------------------------------- |
| `jobs`               | `dict[str, str]`              | `tile_id` → submitted `job_id`.                                              |
| `polygon`            | `dict`                        | Source GeoJSON polygon (used by `merge_area_jobs` to clip).                  |
| `analysis_type`      | `str`                         | Analysis type that was submitted.                                            |
| `failed_submissions` | `tuple[str, ...]`             | Tile IDs whose submission HTTP call failed; pass to `retry_from=`.           |
| `webhook_url`        | `str \| None`                 | Webhook URL the schedule was submitted with (preserved on retries).          |
| `webhook_events`     | `tuple[str, ...] \| None`     | Webhook events the schedule subscribed to.                                   |

`tile_positions`, `grid_shape`, and `config_hash` are also present on the dataclass but are internal bookkeeping for `merge_area_jobs` — agents should treat them as opaque.

### Persistence

`AreaSchedule.to_dict()` and `AreaSchedule.from_dict()` round-trip JSON-safely, so a schedule can be stored in a database row, file, or queue message between submission and merge. Tuples become lists; `webhook_events` is preserved.

```python
import json
schedule_blob = json.dumps(schedule.to_dict())
# ... later, possibly in another process ...
from infrared_sdk.tiling.types import AreaSchedule
schedule = AreaSchedule.from_dict(json.loads(schedule_blob))
result = client.merge_area_jobs(schedule)
```

### Retry submission failures

`failed_submissions` is the recovery surface. Pass the original schedule back via `retry_from=` to resubmit only the tiles whose submission failed, then merge:

```python
retry_schedule = client.run_area(payload, polygon, retry_from=prior_schedule)
combined = prior_schedule.merge(retry_schedule)
result = client.merge_area_jobs(combined)
```

`retry_from` also re-uses the prior schedule's `webhook_url` / `webhook_events` if you don't pass new ones. `AreaSchedule.merge()` validates that polygon, `analysis_type`, and `config_hash` match — mismatched merges raise `ValueError`.

### Manual polling without a webhook

When you don't have a routable webhook URL, `client.check_area_state(schedule)` queries every job status in parallel and returns an `AreaState`:

```python
state = client.check_area_state(schedule)
print(state.status, state.succeeded, state.failed, state.is_complete)
# status: "pending" | "running" | "completed" | "failed" | "partial" | "empty"
```

`AreaState` fields: `status`, `job_states` (`dict[str, JobStatus]`), `succeeded`, `failed`, `running`, `pending`, `total`, `is_complete` (`True` only when `total > 0` and no jobs are non-terminal). Loop on `is_complete` with your own sleep.

**Same shape works for sync timeouts.** When `run_area_and_wait()` raises `AreaTimeoutError`, the exception's `.area_state` attribute is the same `AreaState` shape — so the recovery code you write for async polling also handles sync timeouts. Catch the timeout, inspect `e.area_state.succeeded` / `e.area_state.failed` / `e.area_state.is_complete`, and (if jobs are still running) keep checking via `client.check_area_state(schedule)` from the underlying schedule. See `08-error-handling.md`.

### Materialise results

Once all jobs in a schedule are terminal, `client.merge_area_jobs(schedule)` downloads each succeeded job's payload, merges per-tile grids into one clipped grid, and returns the same `AreaResult` shape that `run_area_and_wait()` would. Failed and skipped jobs are accounted for via `result.failed_jobs` / `result.skipped_jobs`.

### Multi-payload runs

Pass a list of payloads to submit a multi-analysis or parameter sweep over the same polygon:

```python
schedules = client.run_area([wind_payload, svf_payload], polygon, buildings=area.buildings)
# schedules is list[AreaSchedule], one per payload, all sharing one thread pool.
```

All schedules share a single `max_workers` (default 20) thread pool. Webhook events for the whole batch arrive as `payloads × tiles` deliveries in a tight burst — see `06-webhooks.md` for buffer-ingestion guidance.

## Pitfalls

- **Single-tile primitives skip tiling.** `client.analyses.execute()` submits one analysis to one tile. Passing a polygon larger than one 512×512m tile through it does not auto-tile — you'll get a single grid covering the bounding box, not the polygon. Use `run_area` for anything area-shaped.
- **`JobStatus.unknown` is non-terminal.** It is the forward-compat fallback when the API returns a status the SDK doesn't recognise. Treat it like `running` — keep polling.
- **`failed_submissions` is not job failure.** It tracks tiles whose **HTTP submission** failed (transport-level errors). Job-level failures arrive later as `job.failed` webhook events / `JobStatus.failed` and surface in `AreaResult.failed_jobs` after `merge_area_jobs()`.
- **`run_area_and_wait` with `webhook_url=` still blocks.** Passing a webhook URL does **not** make the call async — events are delivered to the URL **and** the call still blocks and returns the merged `AreaResult` locally. Use it when you want both a synchronous result inline and a backend stream of job-level signals.
- **Persisted `AreaSchedule` requires SDK version compatibility.** `from_dict` is forward-compatible across minor versions (unknown keys are ignored), but a major schema change can break replay. Don't persist schedules indefinitely across SDK upgrades; re-submit if the version moves.
- **Multi-payload bursts.** A `run_area([p1, p2, ...], polygon, ...)` call delivers `payloads × tiles` webhook events in a tight window. See `06-webhooks.md` for the buffer-ingestion pattern.

## See also

- `05-area-api.md` — sync `run_area_and_wait` deep-dive, tiling geometry, `AreaResult` fields
- `06-webhooks.md` — Standard Webhooks v1 verification, idempotency, multi-payload burst handling
- `08-error-handling.md` — `AreaTimeoutError`, `JobFailedError`, `JobTimeoutError`, `TiledRunError`
- `01-quickstart.md` — minimum-viable end-to-end run
