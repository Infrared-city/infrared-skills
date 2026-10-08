"""A small, fast HTTP API on the Infrared SDK 1.0.

POST /preview          jobs, tiles and tokens of a run. Free: sends no job.
POST /runs             start an area run in the background, get a run id at once
GET  /runs/{id}        status and progress
GET  /runs/{id}/result.json   physical values (null = no value) and bounds
GET  /runs/{id}/result.png    coloured map, north up
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from infrared_sdk import AreaRunError, InfraredClient
from pydantic import BaseModel, Field

from analyses import build_request
from geometry import extrude_footprints

log = logging.getLogger("infrared-app")


class SiteRequest(BaseModel):
    polygon: dict = Field(description="GeoJSON Polygon, [lon, lat], one ring")
    analysis: Literal["sky-view-factors", "wind-speed", "direct-sun-hours"] = "sky-view-factors"
    params: dict[str, Any] = Field(default_factory=dict)
    # Own data first: footprints in lon/lat with properties.height in metres.
    buildings: dict | None = Field(default=None, description="GeoJSON FeatureCollection")
    # Fallback when the user has no model: public buildings for the polygon.
    # Needs `pip install "infrared-sdk[geodata]"`.
    public_buildings: bool = False

    def key(self) -> str:
        """Hash of every input. Same inputs = same result, so we run it once."""
        blob = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:24]


@dataclass
class Run:
    id: str
    site: SiteRequest
    status: str = "queued"  # queued -> running -> done | failed
    jobs_done: int = 0
    jobs_total: int = 0
    error: str | None = None
    result: Any = None  # AreaResult when done
    png: bytes | None = None


# Process state. One client for the whole process: it keeps the uploaded tile
# geometry in memory (about 24 h), so a second analysis on the same site skips
# the upload. A new client per request would upload everything again.
# For more than one worker process, move `runs` and `by_key` to a database.
state: dict[str, Any] = {}
runs: dict[str, Run] = {}
by_key: dict[str, str] = {}  # input hash -> run id (the result cache)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # InfraredClient() reads INFRARED_API_KEY. The key stays on the server.
    state["client"] = InfraredClient()
    # Runs block on the network and merge in memory: 2 at a time is plenty.
    state["pool"] = ThreadPoolExecutor(max_workers=2)
    yield
    state["pool"].shutdown(wait=False, cancel_futures=True)
    state["client"].close()


app = FastAPI(title="Infrared area API", lifespan=lifespan)


def site_buildings(site: SiteRequest, fetch_public: bool) -> Any:
    """The buildings for the run: the user's own model, else public data."""
    if site.buildings:
        return extrude_footprints(site.buildings, site.polygon)
    if site.public_buildings and fetch_public:
        # Pass the returned object itself to the run: it keeps its own origin.
        return state["client"].buildings.get_area(site.polygon, analysis_type=site.analysis)
    return None


@app.post("/preview")
def preview(site: SiteRequest) -> dict:
    """Count jobs and tokens before anything is billed. Runs locally, free."""
    request = build_request(site.analysis, site.polygon, site.params)
    p = state["client"].preview_area(
        site.polygon, payload=request, buildings=site_buildings(site, fetch_public=False)
    )
    return {
        "tiles": p.tile_count,
        "jobs": p.would_bill_jobs,  # price from jobs, not from tiles
        "estimated_cost_tokens": p.estimated_cost_tokens,
        "estimated_time_s": p.estimated_time_s,
        "cached": site.key() in by_key,  # a cached result costs nothing
    }


def execute(run: Run) -> None:
    """Worker thread: one blocking SDK call does tiling, upload, submit, poll, merge."""
    client: InfraredClient = state["client"]
    site = run.site
    run.status = "running"

    def on_progress(s: Any) -> None:  # AreaState, called by the SDK while it polls
        run.jobs_done, run.jobs_total = s.succeeded, s.total

    try:
        request = build_request(site.analysis, site.polygon, site.params)
        buildings = site_buildings(site, fetch_public=True)
        # No own poll loop: the SDK polls up to 50 jobs per request with backoff.
        # A lost submit is resent with the same idempotency key (never billed
        # twice); a failed tile is sent again once (retries=1).
        run.result = client.run_area_and_wait(
            request, site.polygon, buildings=buildings, on_progress=on_progress
        )
        run.status = "done"
    except AreaRunError as exc:  # a job failed twice: no partial map
        run.status, run.error = "failed", f"{len(exc.failed_jobs)} job(s) failed"
    except Exception:
        log.exception("run %s failed", run.id)  # full detail in the server log only
        run.status, run.error = "failed", "run failed, see the server log"
    if run.status == "failed":
        by_key.pop(site.key(), None)  # let the user try again


@app.post("/runs", status_code=202)
def start_run(site: SiteRequest) -> dict:
    """Start a run, or return the run that already has these exact inputs."""
    key = site.key()
    if key in by_key:
        run = runs[by_key[key]]
        return {"run_id": run.id, "status": run.status, "cached": True}
    run = Run(id=uuid.uuid4().hex[:12], site=site)
    runs[run.id], by_key[key] = run, run.id
    state["pool"].submit(execute, run)
    return {"run_id": run.id, "status": run.status, "cached": False}


def get_run(run_id: str, done: bool = False) -> Run:
    if (run := runs.get(run_id)) is None:
        raise HTTPException(404, "unknown run")
    if done and run.status != "done":
        raise HTTPException(409, f"run is {run.status}")
    return run


@app.get("/runs/{run_id}")
def run_status(run_id: str) -> dict:
    run = get_run(run_id)
    return {
        "run_id": run.id,
        "analysis": run.site.analysis,
        "status": run.status,
        "jobs_done": run.jobs_done,
        "jobs_total": run.jobs_total,
        "error": run.error,
    }


@app.get("/runs/{run_id}/result.json")
def result_json(run_id: str) -> dict:
    result = get_run(run_id, done=True).result
    return {
        "analysis": result.analysis_type,
        "bounds": list(result.bounds),  # [west, south, east, north] of the GRID
        "shape": list(result.grid_shape),  # rows, cols; one cell = 1 m
        "row0": "south",  # flip the rows to draw north up
        "legend": [result.min_legend, result.max_legend],
        # Physical values; NaN -> null. Never read merged_grid directly: it is
        # in the wire type (float16, float32 or int16 with a divisor).
        "grid": result.to_list(),
    }


@app.get("/runs/{run_id}/result.png")
def result_png(run_id: str) -> Response:
    run = get_run(run_id, done=True)
    if run.png is None:
        rows = run.result.to_list()[::-1]  # row 0 is south; the image top is north
        run.png = state["client"].weather.gen_grid_image(
            grid=rows,
            analysis_type=run.result.analysis_type,  # official colours, rendered locally
        )
    return Response(run.png, media_type="image/png")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
