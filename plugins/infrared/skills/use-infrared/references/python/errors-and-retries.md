# Python: errors, retries and cost safety

Failures come in three layers: a bad input (before any job), a transport problem (HTTP), and a job
that fails on the server. Catch each layer where your retry rule fits.

Docs: [Cost and retry](https://infrared.city/docs/sdk/1.0/sdk.md) (chapter "Cost and retry"),
[Client](https://infrared.city/docs/sdk/1.0/python/sdk/index.md),
[Tiling](https://infrared.city/docs/sdk/1.0/python/tiling/index.md).

## What the SDK does for you

- **Bad input fails before you pay.** A request is checked when you build it (pydantic).
  A polygon is checked at `preview_area` and at the run.
- **No double bill.** Each job has an idempotency key. If a submit gets no answer, the SDK sends
  the same key again (up to 6 sends). The server returns the job it already has.
  A job that failed or was refused is sent again as a new job.
- **One retry round.** `run_area_and_wait(..., retries=1)` sends the failed tiles again one time.
  Use `retries=0` to turn it off.
- **No map with holes.** If a tile still fails, the call raises `AreaRunError`.
- **HTTP 429 and 5xx** are retried with backoff. `401` and `403` are not: fix the key.
- **No poll loop needed.** The SDK polls up to 50 job ids in one request and paces itself.

## Catch errors at the right layer

```python
from pydantic import ValidationError
from infrared_sdk import (
    AreaRunError, AreaTimeoutError, InfraredClient, JobFailedError, SvfModelRequest, WindModelRequest,
)
from infrared_sdk.analyses.types import AnalysesName
from infrared_sdk.tiling.validation import PolygonValidationError

client = InfraredClient()
lon, lat = 16.371, 48.208
polygon = {"type": "Polygon", "coordinates": [[
    [lon, lat], [lon + 0.004, lat], [lon + 0.004, lat + 0.003],
    [lon, lat + 0.003], [lon, lat]]]}

# 1. Payload errors: raised when you build the request. No network call.
try:
    WindModelRequest(analysis_type=AnalysesName.wind_speed, wind_speed=4.5, wind_direction=22.5)
except ValidationError as exc:
    print("bad request:", exc.errors()[0]["loc"])         # a fractional bearing is refused

# 2. Polygon errors: raised by preview_area, which is free.
try:
    client.preview_area({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},
                        analysis_type="sky-view-factors")
except PolygonValidationError as exc:
    print("bad polygon:", str(exc)[:60])

# 3. Run errors. A tile fails: AreaRunError. Too slow: AreaTimeoutError.
buildings = {"tower": {
    "coordinates": [c for z in (0, 30) for x, y in [(100, 100), (120, 100), (120, 120), (100, 120)]
                    for c in (x, y, z)],
    "indices": [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
                1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]}}
request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)
try:
    result = client.run_area_and_wait(
        request, polygon, buildings=buildings,
        retries=1,                 # the default: failed tiles go out one more time
        area_timeout=900,          # seconds for the whole area
    )
    print("ok", result.succeeded_jobs, "of", result.total_jobs, "tiles")
except AreaRunError as exc:
    # The tiles that failed and why. Nothing is merged. Fix the cause, then run again.
    for tile in exc.failed_tiles:
        print("tile failed:", tile)
    raise
except AreaTimeoutError as exc:
    print("still running:", exc.area_state)    # log it before you give up
    raise
except JobFailedError as exc:
    print("simulation failed:", exc.job_id, exc.error_message)
    raise
```

## Exceptions

| Exception | Meaning | What to do |
|---|---|---|
| `ValidationError` (pydantic) | Bad request field | Fix the value |
| `PolygonValidationError` | Bad polygon, or more than 100 tiles | Fix it, or pass `max_tiles_override` after you read the price |
| `AreaRunError` | A tile failed after the retry (`failed_tiles`, `failed_jobs`) | Read the tile errors, fix, run again |
| `AreaTimeoutError` | `area_timeout` passed (`area_state`) | Raise the timeout, or use `run_area` and check later |
| `PartsRunError` | An interior run in parts failed (`schedule`) | `run_and_wait(request, retry_from=exc.schedule)` |
| `JobFailedError` | One job failed on the server (`job_id`, `error_message`) | Read the message. Do not retry blind |
| `JobSubmitError` | Submit failed (`status_code`, `retry_after`) | See the HTTP table |
| `AmbiguousSubmitResponseError` | The submit answer was unclear | The SDK never resends it: check `uncertain_submissions` |
| `ResultsDownloadError` | A download failed | Usually network. Try once or twice more |
| `WeatherServiceError` | Weather catalog failed (`retry_after`) | The SDK already retried 3 times |
| `EpwParseError`, `WeatherModelInputsError` | Bad EPW, or the weather cannot feed the model | Use an hourly EPW with 8760 rows |
| `GeodataDependencyError` | The `[geodata]` extra is missing | `pip install "infrared-sdk[geodata]"` |
| `BigPayloadError` family | A large upload failed (`code`: `REF_TOO_LARGE`, `REF_EXPIRED`, ...) | Weld and simplify meshes. Expired links retry by themselves |

Base class of all job errors: `InfraredJobError`. The big-payload errors are not in that family.

## HTTP codes you can meet

| Code | Cause | Action |
|---|---|---|
| 401, 403 | Bad or missing key | Fix `INFRARED_API_KEY`. Never loop |
| 402 | No credits | The SDK stops sending tiles. Tiles sent before may still run and bill. Add credits, then retry |
| 413 | Request over 64 MiB | Weld meshes, simplify, or cut the area |
| 422 | The server refused the input | Read the message (below) |
| 429, 5xx | Rate limit or server error | The SDK retries with backoff |

Common 422 and worker messages:

| Message contains | Cause |
|---|---|
| `analysis-surfaces would synthesize more than 262144 sensors` | Too many facade sensors. Raise `surface_grid_size`, or lower `max_sensors_per_job` |
| `not seated on the terrain` | `terrain_alignment="assume-aligned"` and the model sits off the terrain. Use `"auto-align"` |
| `DNI length 0 != sun_vectors N`, `missing array '...'` | The weather arrays were left out. Build the request with `from_weatherfile_payload` |

## Retry a partial run

With `run_area` (not `..._and_wait`) you get an `AreaSchedule`. After the jobs end, send only the
failed tiles again with the same request and the same layers. Tiles that succeeded carry over and
bill once.

```python
schedule = client.run_area(request, polygon, buildings=buildings,
                           on_accepted=lambda job_id, tile: print("accepted", tile))
# ... wait for the jobs, for example with client.run_area_and_wait on the same request,
# or check client.check_area_state(schedule) from time to time ...
# schedule = client.run_area(request, polygon, buildings=buildings, retry_from=schedule)
# result = client.merge_area_jobs(schedule)
```

If you interrupt a run (Ctrl-C), the exception has a `partial_schedule`. Pass it as `retry_from`.
A tile whose submit outcome is unknown sits in `uncertain_submissions`. The SDK never resends it.

## Cost rules

- Preview first, with the same `payload=` as the run. Price from `would_bill_jobs`.
- One job is one tile for one analysis (one batch for facades, one part for daylight factor).
- There is no result cache. The same run again bills again.
- Several analyses on the same grid family share the geometry uploads.
  That saves time. It does not change the job count.
- Do not send a run again after a crash before you check what the first one did.
