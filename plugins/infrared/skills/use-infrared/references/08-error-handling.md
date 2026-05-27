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
from infrared_sdk import InfraredJobError, JobFailedError, JobTimeoutError, AreaRunError, AreaTimeoutError

try:
    result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
except AreaRunError as e:
    log.error("all jobs failed", extra={"failed": e.failed_jobs, "total": e.total_jobs})
except AreaTimeoutError as e:
    log.warning("area timed out", extra={"state": e.area_state})
except JobFailedError as e:
    log.error("simulation failed", extra={"job_id": e.job_id})
except JobTimeoutError:
    pass  # consider increasing job_timeout
except InfraredJobError:
    raise  # any other job-level failure
```

## Area-level errors

All three area-level exceptions are importable from the package root:

```python
from infrared_sdk import AreaRunError, AreaTimeoutError, TiledRunError
```

- `AreaRunError` *(added 0.4.0)* — `run_area_and_wait` (and `merge_area_jobs`) raises this when **every** job terminates without producing a usable tile. Carries `failed_jobs`, `skipped_jobs`, `total_jobs`. Callers that previously got `AreaResult` with `succeeded_jobs=0` will now see this exception — wrap in `try/except AreaRunError`. Partial failures (≥1 success + N failures) still return an `AreaResult`.
- `AreaTimeoutError` — `run_area_and_wait` exceeded `area_timeout` (default 3600s). Carries `area_state: AreaState` so you can inspect job counts at the moment of timeout. The shape mirrors `client.check_area_state(schedule)` (see [async-and-jobs.md](async-and-jobs.md)), so the same recovery code works for both sync timeouts and async polling.
- `TiledRunError` — every tile in a tiled run failed. Carries `failed_tiles: list[TileFailure]` with per-tile `tile_id`, `row`, `col`, `error` string, and original `exception`.

`AreaResult` reports partial outcomes via `failed_jobs` / `skipped_jobs` rather than raising, as long as at least one tile succeeded.

## Big-payload errors (`$ref` envelope path)

SDK 0.4.3+ auto-switches POSTs larger than 5 MiB to a presigned `$ref` envelope (controlled by `INFRARED_BIG_PAYLOADS_ENABLED`, default `true`, threshold `INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES`). The envelope path raises its own exception family — all importable from the package root and inheriting from `BigPayloadError`:

```python
from infrared_sdk import (
    BigPayloadError,
    BigPayloadPresignError,
    BigPayloadUploadError,
    BigPayloadFetchError,
    RefExpiredRetryExhausted,
)
```

| Exception | Raised when |
|---|---|
| `BigPayloadPresignError` | Backend rejected the presigned-URL request (auth, quota, malformed payload) |
| `BigPayloadUploadError` | Client could not PUT the body to the presigned URL (network, S3 5xx) |
| `BigPayloadFetchError` | Backend failed to read the body from S3 — dispatch on `.code`: `REF_TOO_LARGE`, `REF_EXPIRED`, `REF_NOT_FOUND`, `REF_FETCH_FAILED` |
| `RefExpiredRetryExhausted` | Auto-retry on `REF_EXPIRED` ran out — re-submit with a fresh body |

Catch `BigPayloadError` as the base if you don't care about the sub-type; dispatch on `.code` (or `isinstance`) when retry behaviour matters. Catching only `InfraredJobError` will **miss the entire big-payload family** — they sit outside the job hierarchy. Notebook `cookbook/notebooks/09_error_handling_and_tuning.ipynb` demonstrates the dispatch-and-retry pattern.

## Webhook errors

`WebhookError` is the base; `WebhookRegistrationError` and `WebhookNotFoundError` subclass it. Catch `WebhookError` for any webhook lifecycle issue.

## Weather / utilities-service errors

`WeatherServiceError` — raised by `WeatherServiceClient` when a weather or utilities endpoint returns a non-retryable HTTP error, OR after the SDK's internal retries are exhausted. Available with auto-retry behavior since 0.4.9:

- **Transparent retry**: All four methods (`get_weather_file_from_location`, `get_weather_file_from_identifier`, `filter_weather_data`, `gen_grid_image`) auto-retry up to **3 times** on `429` / `500` / `502` / `503` / `504`.
- **`Retry-After` honored**: When the server provides a `Retry-After` header (delta-seconds), the SDK sleeps for exactly that long. Otherwise it uses jittered exponential backoff capped at **10 s**. Sub-30 s worst-case wait total — synchronous, user-blocking by design.
- **`requests.Timeout` / `ConnectionError` propagate unchanged**: network-level failures are not retried (`stuck` should mean stuck, not `stuck × 4`).
- **`.retry_after: Optional[float]`** on the exception carries the final response's `Retry-After` so callers can implement *outer* backoff once the SDK budget is exhausted. Matches `JobSubmitError`, `JobPollError`, `ResultsDownloadError`.

```python
from infrared_sdk import WeatherServiceError

try:
    weather = client.weather.filter_weather_data(identifier=id, time_period=tp)
except WeatherServiceError as e:
    if e.retry_after is not None:
        time.sleep(max(e.retry_after, 1.0))   # outer backoff after internal retries
    raise
```

## Pitfalls

- `ValidationError` happens at payload construction, not at submission — wrap the `WindModelRequest(...)` (or other request) constructor call, not `client.run_area_and_wait(...)`.
- Do not retry `401` / `403` — those mean the API key is bad. The SDK will not retry them either.
- `AreaTimeoutError.area_state` is the only way to recover progress after a timeout — log it before re-raising.
- A `JobFailedError` is a normal API outcome (bad inputs, simulation diverged), not a bug. Log and skip; don't retry blindly.
- `ResultsDownloadError` after a successful job is usually transient network — safe to retry once or twice.

## See also

- `05-area-api.md` — `failed_jobs` / `skipped_jobs` / `failed_tiles` semantics
- `06-webhooks.md` — webhook exception types
- `01-quickstart.md` — basic single-job error handling
