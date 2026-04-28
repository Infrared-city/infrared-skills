"""Advanced usage: lower-level primitives for full control over the pipeline.

Unlike run_area_and_wait (which handles everything), these examples show
how to break the pipeline into discrete steps for custom logic:

  1. Single-tile primitives (manual submit / poll / download)
  2. Area composable primitives (submit / poll / merge separately)
  3. Full manual tile-by-tile pipeline (internal APIs)
  4. BYO weather data for thermal analyses
  5. Persist & resume schedules across sessions
  6. Webhook-driven area workflow (event-based, no polling)

Usage::

    uv run python demos/demo_advanced_usage.py
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
)
from infrared_sdk.analyses.jobs import (
    Job,
    JobFailedError,
    JobsServiceClient,
    JobStatus,
    JobTimeoutError,
)
from infrared_sdk.analyses.types import AnalysesName, WindModelRequest
from infrared_sdk.tiling.types import TileGrid

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logger = logging.getLogger("advanced-demo")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [16.333752, 48.199335], [16.333752, 48.203969],
        [16.344051, 48.203969], [16.344051, 48.199335],
        [16.333752, 48.199335],
    ]],
}

WIND_SPEED = 30
WIND_DIRECTION = 225


def _custom_poll(client: InfraredClient, job_id: str, timeout: int = 120) -> Job:
    """Custom polling loop with linear backoff."""
    deadline = time.monotonic() + timeout
    delay = 1.0
    attempt = 0
    while True:
        job = client.jobs.get_status(job_id)
        if job.status == JobStatus.succeeded:
            return job
        if job.status == JobStatus.failed:
            raise JobFailedError(f"Job {job_id} failed", job_id=job_id, error_message=job.error or "unknown")
        if time.monotonic() + delay > deadline:
            raise JobTimeoutError(f"Job {job_id} timed out", job_id=job_id)
        attempt += 1
        logger.info("  Poll #%d: status=%s, sleeping %.1fs...", attempt, job.status, delay)
        time.sleep(delay)
        delay = min(delay + 1.0, 8.0)


# ===================================================================
# Example 1: Single-tile primitives
# ===================================================================

def example_single_tile_primitives(client: InfraredClient) -> dict:
    """Run a single-tile analysis using individual primitives.

    Equivalent to client._run_and_wait(payload) but with full control
    over each step: submit, poll, download, decompress.

    NOTE: _run/_run_and_wait are internal methods. The public API is
    area-based (run_area / run_area_and_wait). Use single-tile
    primitives only when you need tile-level control.
    """
    logger.info("=" * 60)
    logger.info("Example 1: Single-tile primitives")
    logger.info("=" * 60)

    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    # Submit (non-blocking)
    job = client.analyses.execute(payload=payload)
    logger.info("Submitted job %s", job.job_id)

    # Poll with custom logic
    completed = _custom_poll(client, job.job_id, timeout=120)

    # Download and decompress
    download = client.jobs.download_results(completed.job_id, _job=completed)
    result = JobsServiceClient.decompress(download.content)
    logger.info("Result keys: %s", sorted(result.keys()))

    return result


# ===================================================================
# Example 2: Area composable primitives
# ===================================================================

def example_area_composable(client: InfraredClient) -> AreaResult:
    """Run an area analysis using the composable step-by-step API.

    Breaks run_area_and_wait into its constituent public methods:
    preview_area -> buildings.get_area -> run_area -> check_area_state -> merge_area_jobs
    """
    logger.info("=" * 60)
    logger.info("Example 2: Area composable primitives")
    logger.info("=" * 60)

    # Step 1: Preview (cost estimation)
    preview = client.preview_area(POLYGON)
    logger.info("Preview: %d tiles, ~%.0fs estimated", preview.tile_count, preview.estimated_time_s)

    # Step 2: Fetch buildings
    area = client.buildings.get_area(POLYGON)
    logger.info("Fetched %d buildings", area.total_buildings)

    # Step 3: Submit (non-blocking)
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED, wind_direction=WIND_DIRECTION,
    )
    schedule: AreaSchedule = client.run_area(payload, POLYGON, buildings=area.buildings)
    logger.info("Submitted %d jobs", len(schedule.jobs))

    # Step 4: Poll with custom logic
    deadline = time.monotonic() + 600
    while True:
        state: AreaState = client.check_area_state(schedule)
        logger.info("  [%3.0f%%] %d/%d done (%d ok, %d fail)",
                     (state.succeeded + state.failed) / max(state.total, 1) * 100,
                     state.succeeded + state.failed, state.total, state.succeeded, state.failed)
        if state.is_complete:
            break
        if time.monotonic() > deadline:
            logger.warning("Timed out")
            break
        time.sleep(5)

    # Retry failed submissions if any
    if schedule.failed_submissions:
        logger.info("Retrying %d failed submissions...", len(schedule.failed_submissions))
        retry = client.run_area(payload, POLYGON, buildings={}, retry_from=schedule)
        schedule = schedule.merge(retry)

    # Step 5: Merge results
    result = client.merge_area_jobs(schedule)
    logger.info("Merged: grid %s, %d ok, %d failed", result.grid_shape, result.succeeded_jobs, len(result.failed_jobs))

    return result


# ===================================================================
# Example 3: Full manual tile-by-tile pipeline
# ===================================================================

def example_manual_pipeline(client: InfraredClient) -> np.ndarray:
    """Fully manual tile-by-tile pipeline for maximum control.

    WARNING: This uses internal SDK APIs (_generate_tiles, _clone_payload_for_tile,
    _extract_grid, merge_tiles, clip_to_polygon) that are not part of the public API
    and may change without notice. Use the composable public API (Example 2)
    unless you need this level of control.
    """
    from infrared_sdk.tiling.merger import (
        clip_to_polygon, merge_tiles, merged_grid_shape,
        project_polygon_to_meters, GRID_ORIGIN_OFFSET_M,
    )
    from infrared_sdk.tiling.orchestrator import _clone_payload_for_tile, _extract_grid

    logger.info("=" * 60)
    logger.info("Example 3: Full manual tile-by-tile pipeline (INTERNAL APIs)")
    logger.info("=" * 60)

    # Generate tiles
    tile_grid: TileGrid = client._generate_tiles(POLYGON)
    non_empty = tile_grid.non_empty_tiles
    logger.info("Generated %dx%d grid, %d non-empty tiles", tile_grid.num_rows, tile_grid.num_cols, len(non_empty))

    base_payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED, wind_direction=WIND_DIRECTION,
    )

    # Fetch buildings per tile
    buildings_per_tile = client.buildings.get_by_tiles(tile_grid)

    # Submit, poll, download tile by tile
    tile_grids: List[Tuple[int, int, np.ndarray]] = []
    for row, col, tile in non_empty:
        tile_payload = _clone_payload_for_tile(base_payload, tile)
        tile_buildings = buildings_per_tile.get(tile.tileId)
        if tile_buildings is not None:
            tile_payload.geometries = tile_buildings

        try:
            job = client.analyses.execute(payload=tile_payload)
            completed = _custom_poll(client, job.job_id)
            download = client.jobs.download_results(completed.job_id, _job=completed)
            result_dict = JobsServiceClient.decompress(download.content)
            grid_array = np.array(_extract_grid(result_dict, ""), dtype=np.float64)
            tile_grids.append((row, col, grid_array))
            logger.info("  Tile [%d,%d]: success (%s)", row, col, grid_array.shape)
        except Exception as exc:
            logger.warning("  Tile [%d,%d]: failed - %s", row, col, exc)

    # Merge and clip
    if tile_grids:
        merged = merge_tiles(tile_grids, tile_grid.num_rows, tile_grid.num_cols)
    else:
        h, w = merged_grid_shape(tile_grid.num_rows, tile_grid.num_cols)
        merged = np.full((h, w), np.nan, dtype=np.float64)

    polygon_meters, _, _ = project_polygon_to_meters(POLYGON)
    clipped = clip_to_polygon(merged, polygon_meters, grid_origin=(-GRID_ORIGIN_OFFSET_M, -GRID_ORIGIN_OFFSET_M))
    logger.info("Merged: %s -> clipped: %s", merged.shape, clipped.shape)

    return clipped


# ===================================================================
# Example 4: BYO weather data
# ===================================================================

def example_byo_weather(client: InfraredClient):
    """Bring your own weather data for thermal analyses.

    Shows how to construct WeatherDataPoint objects from your own source
    (local station, CSV, forecast API) and use them with from_weatherfile_payload.
    """
    from infrared_sdk.models import TimePeriod, WeatherDataPoint, Location
    from infrared_sdk.analyses.types import UtciModelBaseRequest, UtciModelRequest

    logger.info("=" * 60)
    logger.info("Example 4: BYO weather data")
    logger.info("=" * 60)

    # Option A: Use SDK weather utilities (reference)
    stations = client.weather.get_weather_file_from_location(lat=48.200, lon=16.340)
    weather_id = stations[0].get("identifier") or stations[0].get("uuid")
    tp = TimePeriod(start_month=7, start_day=1, start_hour=14, end_month=7, end_day=30, end_hour=14)
    sdk_weather = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)
    logger.info("SDK returned %d weather data points", len(sdk_weather))

    # Option B: Bring your own weather data
    custom_weather = [
        WeatherDataPoint(
            dryBulbTemperature=28.5, relativeHumidity=45.0,
            windSpeed=3.2, windDirection=180.0,
            diffuseHorizontalRadiation=120.0, directNormalRadiation=650.0,
            globalHorizontalRadiation=550.0, horizontalInfraredRadiationIntensity=350.0,
        )
        for _ in range(len(sdk_weather))
    ]

    utci_payload = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
        location=Location(latitude=48.200, longitude=16.340),
        time_period=tp,
        weather_data=custom_weather,
    )
    logger.info("Built UTCI payload with %d custom weather points: %s", len(custom_weather), utci_payload.analysis_type)


# ===================================================================
# Example 5: Persist & resume schedules
# ===================================================================

def example_persist_resume(client: InfraredClient):
    """Persist a schedule to disk and resume from another session.

    Useful for long-running analyses where you want to submit, disconnect,
    and come back later to check status and merge results.
    """
    logger.info("=" * 60)
    logger.info("Example 5: Persist & resume schedules")
    logger.info("=" * 60)

    cache_path = os.path.join(os.path.dirname(__file__), ".cache", "schedule.json")

    # Phase 1: Submit and persist
    area = client.buildings.get_area(POLYGON)
    payload = WindModelRequest(analysis_type=AnalysesName.wind_speed, wind_speed=WIND_SPEED, wind_direction=WIND_DIRECTION)
    schedule = client.run_area(payload, POLYGON, buildings=area.buildings)
    logger.info("Submitted %d jobs, persisting...", len(schedule.jobs))

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(schedule.to_dict(), f, indent=2)

    # Phase 2: Resume from disk (simulates a new session)
    with open(cache_path) as f:
        loaded = AreaSchedule.from_dict(json.load(f))
    logger.info("Loaded schedule: %d jobs", len(loaded.jobs))

    # Wait for completion
    while True:
        state = client.check_area_state(loaded)
        if state.is_complete:
            break
        time.sleep(5)

    result = client.merge_area_jobs(loaded)
    logger.info("Merged: grid %s, %d ok", result.grid_shape, result.succeeded_jobs)
    os.remove(cache_path)


# ===================================================================
# Example 6: Webhook-driven area workflow
# ===================================================================

def handle_webhook_event(raw_body: bytes, headers: dict, webhook_secret: str) -> dict:
    """Handle an incoming Infrared webhook event.

    Drop this into your Flask / FastAPI endpoint. The Infrared API sends
    Standard Webhooks with HMAC-SHA256 signatures.

    Webhook payload::

        {
            "type": "job.succeeded",
            "data": {
                "jobId": "abc-123",
                "status": "Succeeded",
                "modelName": "wind-speed",
                ...
            }
        }

    Returns dict with keys: job_id, status, event_type, raw_payload.
    Returns {"error": ...} on verification failure.
    """
    from infrared_sdk.webhooks.service import WebhooksServiceClient

    if not WebhooksServiceClient.verify_signature(
        payload_body=raw_body, headers=headers, secret=webhook_secret,
    ):
        return {"error": "invalid signature"}

    payload = json.loads(raw_body) if raw_body else {}
    event_type = payload.get("type", "")
    if not event_type and "status" in payload:
        event_type = f"job.{payload['status']}"

    job_id = payload.get("data", {}).get("jobId", "") or payload.get("jobId", "")
    status_map = {"job.running": "running", "job.succeeded": "succeeded", "job.failed": "failed"}

    return {
        "job_id": job_id,
        "status": status_map.get(event_type, "unknown"),
        "event_type": event_type,
        "raw_payload": payload,
    }


def example_webhook_workflow(client: InfraredClient):
    """Submit jobs with webhook URL — API pushes events instead of polling."""
    from infrared_sdk import WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED

    logger.info("=" * 60)
    logger.info("Example 6: Webhook-driven area workflow")
    logger.info("=" * 60)

    area = client.buildings.get_area(POLYGON)
    payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED, wind_direction=WIND_DIRECTION,
    )

    WEBHOOK_URL = "https://your-server.example.com/webhook"
    schedule = client.run_area(
        payload, POLYGON, buildings=area.buildings,
        webhook_url=WEBHOOK_URL,
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )
    logger.info("Submitted %d jobs with webhook_url=%s", len(schedule.jobs), WEBHOOK_URL)

    # Persist schedule for your webhook handler to load later:
    # json.dump(schedule.to_dict(), open("schedule.json", "w"))
    #
    # In your webhook handler:
    #   schedule = AreaSchedule.from_dict(json.load(open("schedule.json")))
    #   result = client.merge_area_jobs(schedule)

    # For this demo, fall back to polling
    while True:
        state = client.check_area_state(schedule)
        if state.is_complete:
            break
        time.sleep(5)

    result = client.merge_area_jobs(schedule)
    logger.info("Merged: grid %s, %d ok", result.grid_shape, result.succeeded_jobs)


# ===================================================================
# Main
# ===================================================================

def main():
    with InfraredClient(logger=logger) as client:
        r1 = example_single_tile_primitives(client)
        print(f"\nExample 1 done - result keys: {sorted(r1.keys())}\n")

        r2 = example_area_composable(client)
        print(f"\nExample 2 done - grid {r2.grid_shape}\n")

        r3 = example_manual_pipeline(client)
        print(f"\nExample 3 done - grid {r3.shape}\n")

        example_byo_weather(client)
        print("\nExample 4 done\n")

        example_persist_resume(client)
        print("\nExample 5 done\n")

        example_webhook_workflow(client)
        print("\nExample 6 done\n")

    print("All examples complete!")


if __name__ == "__main__":
    main()
