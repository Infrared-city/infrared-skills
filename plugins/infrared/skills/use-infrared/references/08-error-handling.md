# Error Handling

The SDK has three layers of failure: payload validation (Pydantic), HTTP transport, and job lifecycle. Each raises a distinct exception family — catch at the layer that matches your retry policy.

## Payload validation

Payloads are validated at construction time. Bad inputs fail fast, before any HTTP call:

```python
from pydantic import ValidationError
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName

try:
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=200,  # exceeds max of 100
        wind_direction=180,
    )
except ValidationError as e:
    print(e)  # field validation errors
```

`PolygonValidationError` (subclass of `ValueError`, raised from `infrared_sdk.tiling.validation`) covers GeoJSON polygon issues — wrong type, self-intersection, fewer than 3 unique vertices, etc.

## HTTP transport

The SDK auto-retries HTTP `429` (rate-limited) and `5xx` with exponential backoff + jitter. Non-retryable codes (`401`, `403`) raise immediately. Auth failures are not retried — fix the API key, do not loop.

## Job exception hierarchy

All job-level exceptions inherit from `InfraredJobError`:

| Exception              | Raised when                       |
| ---------------------- | --------------------------------- |
| `JobSubmitError`       | Job submission failed             |
| `JobPollError`         | Error while polling status        |
| `JobFailedError`       | Job completed with failed status  |
| `JobTimeoutError`      | Single-job polling timed out      |
| `ResultsDownloadError` | Failed to download results        |
| `JobNotCompletedError` | Result accessed before completion |

```python
from infrared_sdk import InfraredJobError, JobFailedError, JobTimeoutError

try:
    result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
except JobFailedError as e:
    log.error("simulation failed", extra={"job_id": e.job_id})
except JobTimeoutError:
    pass  # consider increasing job_timeout
except InfraredJobError:
    raise  # any other job-level failure
```

## Area-level errors

- `AreaTimeoutError` — `run_area_and_wait` exceeded `area_timeout` (default 3600s). The exception carries `area_state: AreaState` so you can inspect counts of succeeded / failed / running / pending jobs at the moment of timeout. Re-exported at the package root: `from infrared_sdk import AreaTimeoutError`.
- `TiledRunError` — every tile in a tiled run failed. Carries `failed_tiles: list[TileFailure]` with per-tile `tile_id`, `row`, `col`, `error` string, and original `exception`. Not yet re-exported at the package root — import it from the deeper path: `from infrared_sdk.tiling.types import TiledRunError`.

`AreaResult` reports partial outcomes via `failed_jobs` / `skipped_jobs` rather than raising, as long as at least one tile succeeded.

## Webhook errors

`WebhookError` is the base; `WebhookRegistrationError` and `WebhookNotFoundError` subclass it. Catch `WebhookError` for any webhook lifecycle issue.

## Pitfalls

- `ValidationError` happens at payload construction, not at submission — wrap the `WindModelRequest(...)` (or other request) constructor call, not `client.run_area_and_wait(...)`.
- Do not retry `401` / `403` — those mean the API key is bad. The SDK will not retry them either.
- `AreaTimeoutError.area_state` is the only way to recover progress after a timeout — log it before re-raising.
- A `JobFailedError` is a normal API outcome (bad inputs, simulation diverged), not a bug. Log and skip; don't retry blindly.
- `ResultsDownloadError` after a successful job is usually transient network — safe to retry once or twice.

## See also

- `05-area-api.md` — `failed_jobs` / `skipped_jobs` semantics
- `06-webhooks.md` — webhook exception types
- `01-quickstart.md` — basic single-job error handling
