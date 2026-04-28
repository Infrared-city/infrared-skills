"""Advanced usage demo: primitives for full control over the analysis pipeline.
Unlike the high-level `run_area` or `run_area_and_wait`,
which handles everything internally,
this demo shows how to use the SDK's lower-level primitives so you can:

  1. Bring your own geometries (buildings / meshes)
  2. Bring your own weather data
  3. Control tile generation and inspect the grid
  4. Submit jobs manually and poll with custom logic
  5. Download and decompress results individually
  6. Merge tile grids with your own clipping / post-processing
  7. Retry only failed tiles without re-running the whole area
  8. Persist and resume schedules across sessions
  9. Handle webhook events instead of polling (event-driven pipelines)
"""

import json
import logging
import os
import time
from typing import List, Tuple

import numpy as np
from dotenv import load_dotenv

from infrared_sdk import (
    AreaResult,
    AreaSchedule,
    AreaState,
    InfraredClient,
    Job,
    JobStatus,
    WindModelRequest,
)
from infrared_sdk.analyses.jobs import (
    JobFailedError,
    JobsServiceClient,
    JobTimeoutError,
)
from infrared_sdk.analyses.types import AnalysesName
from infrared_sdk.tiling.merger import (
    clip_to_polygon,
    merge_tiles,
    merged_grid_shape,
    project_polygon_to_meters,
    GRID_ORIGIN_OFFSET_M,
)
from infrared_sdk.tiling.orchestrator import _clone_payload_for_tile, _extract_grid
from infrared_sdk.tiling.types import TileGrid

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("advanced-demo")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Small polygon in Vienna (~4-6 tiles)
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [16.333752, 48.199335],
            [16.333752, 48.203969],
            [16.344051, 48.203969],
            [16.344051, 48.199335],
            [16.333752, 48.199335],
        ]
    ],
}

WIND_SPEED = 30  # m/s
WIND_DIRECTION = 225  # SW wind


# ═══════════════════════════════════════════════════════════════════════════
# Example 1: Single-tile primitives (manual run_and_wait)
# ═══════════════════════════════════════════════════════════════════════════


def example_single_tile_primitives(client: InfraredClient) -> dict:
    """Run a single-tile analysis using individual primitives.

    This is equivalent to `client.run_and_wait(payload)` but broken into
    discrete steps so you can inject custom logic at each stage.
    """
    logger.info("=" * 60)
    logger.info("Example 1: Single-tile primitives")
    logger.info("=" * 60)

    # Step 1: Build your payload
    # You have full control over geometries, wind params, etc.
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
        # geometries=your_custom_geometries,   # BYO geometries
        # vegetation=your_custom_vegetation,    # BYO vegetation
    )
    logger.info("Step 1: Built payload (type=%s)", payload.analysis_type)

    # Step 2: Submit the job (non-blocking)
    job: Job = client.analyses.execute(payload=payload)
    logger.info("Step 2: Submitted job %s (status=%s)", job.job_id, job.status)

    # Step 3: Poll with your own logic
    # You control: backoff strategy, timeout, progress reporting, cancellation
    completed = _custom_poll(client, job.job_id, timeout=120)
    logger.info("Step 3: Job completed (status=%s)", completed.status)

    # Step 4: Download the raw result
    download = client.jobs.download_results(completed.job_id, _job=completed)
    logger.info(
        "Step 4: Downloaded %d bytes (type=%s)",
        len(download.content),
        download.content_type,
    )

    # Step 5: Decompress
    result = JobsServiceClient.decompress(download.content)
    logger.info(
        "Step 5: Decompressed result (keys=%s)",
        sorted(result.keys()),
    )

    return result


def _custom_poll(
    client: InfraredClient,
    job_id: str,
    timeout: int = 120,
    initial_delay: float = 1.0,
    max_delay: float = 8.0,
) -> Job:
    """Custom polling loop with linear backoff.

    Replace this with whatever strategy fits your use case:
    - Exponential backoff for cost-sensitive workloads
    - Fixed interval for latency-sensitive dashboards
    - Webhook-driven for event-based architectures (no polling needed)
    """
    deadline = time.monotonic() + timeout
    delay = initial_delay
    attempt = 0

    while True:
        job = client.jobs.get_status(job_id)

        if job.status == JobStatus.succeeded:
            return job
        if job.status == JobStatus.failed:
            raise JobFailedError(
                f"Job {job_id} failed: {job.error}",
                job_id=job_id,
                error_message=job.error or "unknown",
            )

        if time.monotonic() + delay > deadline:
            raise JobTimeoutError(
                f"Job {job_id} timed out after {timeout}s",
                job_id=job_id,
            )

        attempt += 1
        logger.info(
            "  Poll #%d: status=%s, sleeping %.1fs...",
            attempt,
            job.status,
            delay,
        )
        time.sleep(delay)
        delay = min(delay + 1.0, max_delay)  # linear backoff


# ═══════════════════════════════════════════════════════════════════════════
# Example 2: Area analysis with composable primitives
# ═══════════════════════════════════════════════════════════════════════════


def example_area_composable(client: InfraredClient) -> AreaResult:
    """Run an area analysis using the composable step-by-step API.

    This mirrors `run_area_and_wait` internally but gives you control
    over each phase: tiling, building fetch, submission, polling, merging.
    """
    logger.info("=" * 60)
    logger.info("Example 2: Area composable primitives")
    logger.info("=" * 60)

    # --- Step 1: Preview the area (cost estimation) -----------------------
    preview = client.preview_area(POLYGON)
    logger.info(
        "Step 1: Preview — %d tiles, ~%.0fs estimated, ~%d tokens",
        preview.tile_count,
        preview.estimated_time_s,
        preview.estimated_cost_tokens,
    )

    # --- Step 2: Fetch buildings ------------------------------------------
    # Option A: Use the SDK's area-level building fetch
    area_buildings = client.buildings.get_buildings_in_area(POLYGON)
    logger.info(
        "Step 2: Fetched %d buildings",
        area_buildings.total_buildings,
    )

    # Option B: Bring your own buildings (skip the API call entirely)
    # my_buildings = load_buildings_from_my_database()
    # Pass `{}` to run_area if you want no buildings

    # --- Step 3: Submit jobs (non-blocking) --------------------------------
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    schedule: AreaSchedule = client.run_area(
        payload,
        POLYGON,
        buildings=area_buildings.buildings,
    )
    logger.info(
        "Step 3: Submitted %d jobs (%d failed submissions)",
        len(schedule.jobs),
        len(schedule.failed_submissions),
    )

    # --- Step 4: Poll with custom logic -----------------------------------
    schedule = _custom_area_poll(client, schedule, timeout=600)

    # --- Step 5: Merge results --------------------------------------------
    result: AreaResult = client.merge_area_jobs(schedule)
    logger.info(
        "Step 5: Merged — grid %s, %d ok, %d failed, %d skipped",
        result.grid_shape,
        result.succeeded_jobs,
        len(result.failed_jobs),
        len(result.skipped_jobs),
    )

    return result


def _custom_area_poll(
    client: InfraredClient,
    schedule: AreaSchedule,
    timeout: int = 600,
    interval: float = 5.0,
) -> AreaSchedule:
    """Poll area jobs with custom progress reporting and retry logic.

    Returns the (potentially updated) schedule after retrying failed
    submissions.
    """
    deadline = time.monotonic() + timeout

    while True:
        state: AreaState = client.check_area_state(schedule)
        done = state.succeeded + state.failed
        pct = done / state.total * 100 if state.total else 0

        logger.info(
            "  Area poll: [%3.0f%%] %d/%d done (%d ok, %d fail) — %s",
            pct,
            done,
            state.total,
            state.succeeded,
            state.failed,
            state.status,
        )

        if state.is_complete:
            break

        if time.monotonic() + interval > deadline:
            logger.warning("Area poll timed out after %ds", timeout)
            break

        time.sleep(interval)

    # --- Retry failed submissions (if any) --------------------------------
    if schedule.failed_submissions:
        logger.info(
            "Retrying %d failed submissions...",
            len(schedule.failed_submissions),
        )
        retry_schedule = client.run_area(
            WindModelRequest(
                analysis_type=AnalysesName.wind_speed,
                wind_speed=WIND_SPEED,
                wind_direction=WIND_DIRECTION,
            ),
            POLYGON,
            buildings={},
            retry_from=schedule,
        )
        schedule = schedule.merge(retry_schedule)

    return schedule


# ═══════════════════════════════════════════════════════════════════════════
# Example 3: Full manual pipeline (tile-by-tile control)
# ═══════════════════════════════════════════════════════════════════════════


def example_manual_pipeline(client: InfraredClient) -> np.ndarray:
    """Fully manual tile-by-tile pipeline for maximum control.

    Demonstrates:
    - Manual tile generation and inspection
    - Per-tile payload cloning with location overrides
    - Individual job submission, polling, download, decompression
    - Manual grid merging and polygon clipping
    - Custom post-processing on the merged grid
    """
    logger.info("=" * 60)
    logger.info("Example 3: Full manual tile-by-tile pipeline")
    logger.info("=" * 60)

    # --- Step 1: Generate tiles -------------------------------------------
    tile_grid: TileGrid = client._generate_tiles(POLYGON)
    non_empty = tile_grid.non_empty_tiles
    logger.info(
        "Step 1: Generated %dx%d grid, %d non-empty tiles",
        tile_grid.num_rows,
        tile_grid.num_cols,
        len(non_empty),
    )

    # Inspect tiles — each tile has coordinates, centroid, size
    for row, col, tile in non_empty:
        logger.info(
            "  Tile [%d,%d] id=%s centroid=(%.4f, %.4f) size=%dm",
            row,
            col,
            tile.tileId[:8],
            tile.centroid.latitude,
            tile.centroid.longitude,
            tile.size,
        )

    # --- Step 2: Build per-tile payloads ----------------------------------
    base_payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    # Fetch buildings per tile (server-side spatial filtering)
    buildings_per_tile = client.buildings.get_buildings_by_tiles(tile_grid)
    logger.info("Step 2: Fetched buildings for %d tiles", len(buildings_per_tile))

    # --- Step 3: Submit, poll, download tile by tile ----------------------
    tile_grids: List[Tuple[int, int, np.ndarray]] = []
    failed_tiles: List[str] = []

    for row, col, tile in non_empty:
        tile_payload = _clone_payload_for_tile(base_payload, tile)

        # Inject buildings for this tile into the payload
        tile_buildings = buildings_per_tile.get(tile.tileId)
        if tile_buildings is not None:
            tile_payload.geometries = tile_buildings

        logger.info("  Tile [%d,%d]: submitting...", row, col)
        try:
            # Submit
            job = client.analyses.execute(payload=tile_payload)

            # Poll (reuse our custom poller)
            completed = _custom_poll(client, job.job_id, timeout=120)

            # Download + decompress
            download = client.jobs.download_results(completed.job_id, _job=completed)
            result_dict = JobsServiceClient.decompress(download.content)

            # Extract the 512x512 grid
            grid_data = _extract_grid(result_dict, "")
            grid_array = np.array(grid_data, dtype=np.float64)
            tile_grids.append((row, col, grid_array))
            logger.info(
                "  Tile [%d,%d]: success (shape=%s)", row, col, grid_array.shape
            )

        except (JobFailedError, JobTimeoutError, Exception) as exc:
            logger.warning("  Tile [%d,%d]: failed — %s", row, col, exc)
            failed_tiles.append(tile.tileId)

    # --- Step 4: Merge tiles with bilinear blending -----------------------
    if tile_grids:
        merged = merge_tiles(tile_grids, tile_grid.num_rows, tile_grid.num_cols)
    else:
        h, w = merged_grid_shape(tile_grid.num_rows, tile_grid.num_cols)
        merged = np.full((h, w), np.nan, dtype=np.float64)

    logger.info("Step 4: Merged grid shape = %s", merged.shape)

    # --- Step 5: Clip to polygon ------------------------------------------
    polygon_meters, _, _ = project_polygon_to_meters(POLYGON)
    clipped = clip_to_polygon(
        merged,
        polygon_meters,
        grid_origin=(-GRID_ORIGIN_OFFSET_M, -GRID_ORIGIN_OFFSET_M),
    )
    logger.info("Step 5: Clipped grid shape = %s", clipped.shape)

    # --- Step 6: Custom post-processing -----------------------------------
    # This is where you add your own logic on the raw grid data:
    valid = clipped[~np.isnan(clipped)]
    if valid.size > 0:
        logger.info(
            "Step 6: Post-processing — min=%.2f, max=%.2f, mean=%.2f, std=%.2f",
            np.min(valid),
            np.max(valid),
            np.mean(valid),
            np.std(valid),
        )

        # Example: classify wind speeds into zones
        zones = np.full_like(clipped, np.nan)
        zones[clipped < 2.0] = 0  # calm
        zones[(clipped >= 2.0) & (clipped < 5.0)] = 1  # moderate
        zones[clipped >= 5.0] = 2  # strong
        zone_counts = {
            "calm (<2 m/s)": int(np.nansum(zones == 0)),
            "moderate (2-5 m/s)": int(np.nansum(zones == 1)),
            "strong (>5 m/s)": int(np.nansum(zones == 2)),
        }
        logger.info("  Wind zones: %s", zone_counts)

    logger.info(
        "  %d tiles succeeded, %d failed",
        len(tile_grids),
        len(failed_tiles),
    )

    return clipped


# ═══════════════════════════════════════════════════════════════════════════
# Example 4: BYO weather data for thermal analyses
# ═══════════════════════════════════════════════════════════════════════════


def example_byo_weather(client: InfraredClient):
    """Demonstrate how to bring your own weather data.

    The SDK's weather utilities fetch from the Infrared weather API,
    but you can bypass them entirely with your own data source.
    """
    logger.info("=" * 60)
    logger.info("Example 4: BYO weather data")
    logger.info("=" * 60)

    from infrared_sdk.utils import TimePeriod, WeatherDataPoint, LocationMixin
    from infrared_sdk.analyses.types import (
        UtciModelBaseRequest,
        UtciModelRequest,
    )

    # --- Option A: Use SDK weather utilities (for reference) ---------------
    logger.info("Option A: Fetch from Infrared weather API")
    locations = client.utilities.get_weather_file_from_location(
        lat=48.200,
        lon=16.340,
    )
    weather_id = locations[0]["uuid"]
    time_period = TimePeriod(
        start_month=7,
        start_day=1,
        start_hour=14,
        end_month=7,
        end_day=30,
        end_hour=14,
    )
    sdk_weather = client.utilities.filter_weather_data(
        identifier=weather_id,
        time_period=time_period,
    )
    logger.info("  SDK returned %d weather data points", len(sdk_weather))

    # --- Option B: Bring your own weather data ----------------------------
    logger.info("Option B: BYO weather data")

    # Create WeatherDataPoint objects from your own source
    # (e.g., local weather station, custom forecast API, CSV file)
    custom_weather = [
        WeatherDataPoint(
            dryBulbTemperature=28.5,
            relativeHumidity=45.0,
            windSpeed=3.2,
            windDirection=180.0,
            diffuseHorizontalRadiation=120.0,
            directNormalRadiation=650.0,
            globalHorizontalRadiation=550.0,
            horizontalInfraredRadiationIntensity=350.0,
            # ... fill other fields from your data source
        )
        for _ in range(len(sdk_weather))  # match the time period length
    ]
    logger.info("  Created %d custom weather data points", len(custom_weather))

    # Build UTCI payload with your weather data
    _ = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(
            analysis_type=AnalysesName.thermal_comfort_index,
        ),
        location=LocationMixin(latitude=48.200, longitude=16.340),
        time_period=time_period,
        weather_data=custom_weather,
    )
    logger.info("  Built UTCI payload with custom weather (ready to submit)")

    # You'd then submit this payload just like any other:
    # result = client.run_and_wait(utci_payload, timeout=300)
    # Or use it with run_area for area-level analysis


# ═══════════════════════════════════════════════════════════════════════════
# Example 5: Persist & resume schedules
# ═══════════════════════════════════════════════════════════════════════════


def example_persist_resume(client: InfraredClient):
    """Demonstrate persisting a schedule to disk and resuming later.

    Useful for long-running area analyses where you want to:
    - Submit jobs and come back later
    - Resume after a crash or restart
    - Share schedules across processes
    """
    logger.info("=" * 60)
    logger.info("Example 5: Persist & resume schedules")
    logger.info("=" * 60)

    cache_path = os.path.join(os.path.dirname(__file__), ".cache", "schedule.json")

    # --- Phase 1: Submit and persist --------------------------------------
    area_buildings = client.buildings.get_buildings_in_area(POLYGON)
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    schedule = client.run_area(payload, POLYGON, buildings=area_buildings.buildings)
    logger.info(
        "Phase 1: Submitted %d jobs, persisting schedule...",
        len(schedule.jobs),
    )

    # Persist to JSON
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(schedule.to_dict(), f, indent=2)
    logger.info("  Saved schedule to %s", cache_path)

    # --- Phase 2: Resume from disk ----------------------------------------
    logger.info("Phase 2: Loading schedule from disk...")
    with open(cache_path) as f:
        loaded = AreaSchedule.from_dict(json.load(f))
    logger.info(
        "  Loaded: %d jobs, analysis_type=%s",
        len(loaded.jobs),
        loaded.analysis_type,
    )

    # Check current state
    state = client.check_area_state(loaded)
    logger.info(
        "  State: %s (%d ok, %d fail, %d pending, %d running)",
        state.status,
        state.succeeded,
        state.failed,
        state.pending,
        state.running,
    )

    # Wait if still running
    while not state.is_complete:
        logger.info("  Waiting 5s...")
        time.sleep(5)
        state = client.check_area_state(loaded)

    # Merge
    result = client.merge_area_jobs(loaded)
    logger.info(
        "Phase 2: Merged — grid %s, %d ok, %d failed",
        result.grid_shape,
        result.succeeded_jobs,
        len(result.failed_jobs),
    )

    # Clean up
    os.remove(cache_path)


# ═══════════════════════════════════════════════════════════════════════════
# Example 6: Webhook event handler (event-driven, no polling)
# ═══════════════════════════════════════════════════════════════════════════


def handle_webhook_event(
    raw_body: bytes,
    headers: dict,
    webhook_secret: str,
) -> dict:
    """Handle an incoming Infrared webhook event.

    Drop this into your Flask / FastAPI / Django endpoint to process
    job status events instead of polling. The Infrared API sends
    Standard Webhooks with HMAC-SHA256 signatures.

    Webhook payload formats
    -----------------------
    Standard Webhooks format (default)::

        {
            "type": "job.succeeded",      # job.running | job.succeeded | job.failed
            "data": {
                "jobId": "abc-123",
                "status": "Succeeded",
                "modelName": "wind-speed",
                "requestedAt": "2025-01-01T00:00:00Z",
                "startedAt": "2025-01-01T00:00:05Z",
                "finishedAt": "2025-01-01T00:01:00Z"
            }
        }

    Flat Lambda format (alternative)::

        {
            "jobId": "abc-123",
            "status": "succeeded",
            "modelName": "wind-speed"
        }

    Parameters
    ----------
    raw_body : bytes
        The raw HTTP request body (read *before* JSON parsing).
    headers : dict
        Request headers (keys lowercased). Must include
        ``webhook-id``, ``webhook-timestamp``, ``webhook-signature``.
    webhook_secret : str
        Your ``whsec_``-prefixed webhook secret.

    Returns
    -------
    dict
        Parsed event with keys: ``job_id``, ``status``, ``event_type``,
        ``raw_payload``. Returns ``{"error": ...}`` on verification failure.

    Example — Flask
    ---------------
    ::

        @app.route("/webhook", methods=["POST"])
        def webhook():
            event = handle_webhook_event(
                raw_body=request.get_data(),
                headers={k.lower(): v for k, v in request.headers},
                webhook_secret=os.environ["WEBHOOK_SECRET"],
            )
            if "error" in event:
                return {"error": event["error"]}, 401

            if event["status"] == "succeeded":
                # Download results for this job
                download = client.jobs.download_results(event["job_id"])
                result = JobsServiceClient.decompress(download.content)
                save_to_database(event["job_id"], result)

            elif event["status"] == "failed":
                alert_team(event["job_id"], event["raw_payload"])

            return {"status": "ok"}, 200

    Example — FastAPI
    -----------------
    ::

        @app.post("/webhook")
        async def webhook(request: Request):
            raw_body = await request.body()
            headers = {k.lower(): v for k, v in request.headers.items()}
            event = handle_webhook_event(raw_body, headers, WEBHOOK_SECRET)
            if "error" in event:
                raise HTTPException(status_code=401, detail=event["error"])
            # ... process event["job_id"], event["status"]
            return {"status": "ok"}
    """
    from infrared_sdk.webhooks.service import WebhooksServiceClient

    # 1. Verify HMAC signature (reject tampered / replayed requests)
    if not WebhooksServiceClient.verify_signature(
        payload_body=raw_body,
        headers=headers,
        secret=webhook_secret,
    ):
        return {"error": "invalid signature"}

    # 2. Parse the JSON payload
    payload = json.loads(raw_body) if raw_body else {}

    # 3. Extract event type and job ID (support both payload formats)
    event_type = payload.get("type", "")
    if not event_type and "status" in payload:
        # Flat Lambda format: derive event type from status field
        event_type = f"job.{payload['status']}"

    job_id = payload.get("data", {}).get("jobId", "") or payload.get("jobId", "")

    # 4. Map to a normalized status
    status_map = {
        "job.running": "running",
        "job.succeeded": "succeeded",
        "job.failed": "failed",
    }
    status = status_map.get(event_type, "unknown")

    return {
        "job_id": job_id,
        "status": status,
        "event_type": event_type,
        "raw_payload": payload,
    }


def example_webhook_area_workflow(client: InfraredClient):
    """Show how to wire webhook events into an area workflow.

    Instead of polling with check_area_state, you submit jobs with a
    webhook_url and let the API push status updates to your endpoint.
    When all jobs complete, you call merge_area_jobs.
    """
    logger.info("=" * 60)
    logger.info("Example 6: Webhook-driven area workflow")
    logger.info("=" * 60)

    YOUR_WEBHOOK_URL = "https://your-server.example.com/webhook"

    area_buildings = client.buildings.get_buildings_in_area(POLYGON)
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    # Subscribe to succeeded + failed events at submission time
    from infrared_sdk.webhooks.types import (
        WEBHOOK_EVENT_SUCCEEDED,
        WEBHOOK_EVENT_FAILED,
    )

    schedule: AreaSchedule = client.run_area(
        payload,
        POLYGON,
        buildings=area_buildings.buildings,
        webhook_url=YOUR_WEBHOOK_URL,
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )
    logger.info(
        "Submitted %d jobs with webhook_url=%s",
        len(schedule.jobs),
        YOUR_WEBHOOK_URL,
    )

    # Persist the schedule so your webhook handler can load it later
    schedule_data = schedule.to_dict()
    logger.info(
        "Persist this schedule (json-serializable, %d bytes)",
        len(json.dumps(schedule_data)),
    )

    # --- In your webhook handler (separate process/server): ---------------
    # 1. Each event calls handle_webhook_event() to get job_id + status
    # 2. Track completed job_ids (e.g., in a database or Redis)
    # 3. When all jobs are terminal, load the schedule and merge:
    #
    #     schedule = AreaSchedule.from_dict(load_schedule_from_db())
    #     result = client.merge_area_jobs(schedule)
    #
    # No polling needed — the API pushes events to you.

    logger.info("(Skipping actual webhook wait — see handle_webhook_event())")

    # For this demo, fall back to polling to show the full flow
    while True:
        state = client.check_area_state(schedule)
        if state.is_complete:
            break
        time.sleep(5)

    result = client.merge_area_jobs(schedule)
    logger.info(
        "Merged — grid %s, %d ok, %d failed",
        result.grid_shape,
        result.succeeded_jobs,
        len(result.failed_jobs),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


def main():
    with InfraredClient(
        api_key=os.environ["INFRARED_API_KEY"],
        logger=logger,
    ) as client:
        # Example 1: Single-tile primitives
        single_result = example_single_tile_primitives(client)
        print(f"\nExample 1 done — result keys: {sorted(single_result.keys())}\n")

        # Example 2: Area composable (submit / poll / merge separately)
        area_result = example_area_composable(client)
        print(f"\nExample 2 done — grid {area_result.grid_shape}\n")

        # Example 3: Full manual tile-by-tile pipeline
        manual_grid = example_manual_pipeline(client)
        print(f"\nExample 3 done — grid {manual_grid.shape}\n")

        # Example 4: BYO weather data
        example_byo_weather(client)
        print("\nExample 4 done — custom weather payload ready\n")

        # Example 5: Persist and resume
        example_persist_resume(client)
        print("\nExample 5 done — schedule persisted and resumed\n")

        # Example 6: Webhook-driven area workflow
        example_webhook_area_workflow(client)
        print("\nExample 6 done — webhook workflow complete\n")

    print("=" * 60)
    print("All examples complete!")
    print("=" * 60)
    print("\nNote: handle_webhook_event() is a standalone function you can")
    print("import and use directly in your Flask/FastAPI/Django endpoint.")


if __name__ == "__main__":
    main()
