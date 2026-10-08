"""A small, fast HTTP API on the Infrared SDK 1.0.

POST /preview          tiles, jobs and tokens of a run. Free: sends no job.
POST /runs             start an area run in the background, get a run id at once
GET  /runs/{id}        status and progress
GET  /runs/{id}/result.json?step=1   physical values (null = no value) and bounds
GET  /runs/{id}/result.png    coloured map, north up
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from infrared_sdk import AreaRunError, GeodataDependencyError, InfraredClient
from pydantic import BaseModel, Field, field_validator

from analyses import build_request, run_area
from geometry import extrude_footprints
from store import Run, RunStore

log = logging.getLogger("infrared-app")

MAX_TILES_LARGE = 400  # the most tiles this server runs with allow_large (about 4,000 tokens)
GEODATA_HINT = 'public_buildings needs the geodata extra: pip install "infrared-sdk[geodata]==1.0.0"'


class SiteRequest(BaseModel):
    polygon: dict = Field(description="GeoJSON Polygon, [lon, lat], one closed ring")
    analysis: Literal["sky-view-factors", "wind-speed", "direct-sun-hours"] = "sky-view-factors"
    params: dict[str, Any] = Field(default_factory=dict)
    # Own data first: footprints in lon/lat with properties.height in metres.
    buildings: dict | None = Field(default=None, description="GeoJSON FeatureCollection")
    # Fallback when the user has no model: public buildings for the polygon.
    public_buildings: bool = False
    # The SDK refuses more than 100 tiles. True lifts the cap to MAX_TILES_LARGE.
    allow_large: bool = False

    @field_validator("polygon")
    @classmethod
    def check_polygon(cls, v: dict) -> dict:
        """A bad polygon is the caller's error (422), not a server crash (500)."""
        ring = (v.get("coordinates") or [None])[0] if v.get("type") == "Polygon" else None
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("need a GeoJSON Polygon with one closed ring of 4 or more [lon, lat] points")
        for p in ring:
            ok = isinstance(p, list) and len(p) >= 2 and all(isinstance(c, (int, float)) for c in p[:2])
            if not (ok and -180 <= p[0] <= 180 and -90 <= p[1] <= 90):
                raise ValueError(f"bad point {p!r}: use [lon, lat] in degrees")
        return v

    def key(self) -> str:
        """Hash of every input that changes the result. Same inputs = one run."""
        blob = json.dumps(self.model_dump(exclude={"allow_large"}), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def max_tiles(self) -> int | None:
        return MAX_TILES_LARGE if self.allow_large else None  # None = the SDK cap (100)


# Process state. One client for the whole process: it keeps the uploaded tile
# geometry in memory (about 24 h), so a second analysis on the same site skips
# the upload. A new client per request would upload everything again.
state: dict[str, Any] = {}
store = RunStore(ttl_s=3600, max_runs=50)  # done runs live 1 h, at most 50 in memory


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


def check_site(site: SiteRequest) -> dict:
    """Preview the run (local, free). Turn every input problem into HTTP 422."""
    # The geodata extra adds pyarrow (the public-data reader). Check before any work.
    if site.public_buildings and not site.buildings and importlib.util.find_spec("pyarrow") is None:
        raise HTTPException(422, GEODATA_HINT)
    request = build_request(site.analysis, site.polygon, site.params)
    try:
        p = state["client"].preview_area(
            site.polygon, payload=request, max_tiles_override=site.max_tiles(),
            buildings=site_buildings(site, fetch_public=False),
        )
    except ValueError as exc:  # a polygon the SDK refuses, for example over the tile cap
        hint = f"This server runs at most {MAX_TILES_LARGE} tiles." if site.allow_large else (
            f"Send allow_large: true to run up to {MAX_TILES_LARGE} tiles.")
        raise HTTPException(422, f"{exc} {hint}") from None
    return {"tiles": p.tile_count, "jobs": p.would_bill_jobs, "estimated_cost_tokens": p.estimated_cost_tokens}


@app.post("/preview")
def preview(site: SiteRequest) -> dict:
    """Count tiles, jobs and tokens before anything is billed. Price from jobs."""
    return {**check_site(site), "cached": store.has_key(site.key())}  # a cached result costs nothing


def execute(run: Run) -> None:
    """Worker thread: one blocking SDK call does tiling, upload, submit, poll, merge."""
    client: InfraredClient = state["client"]
    site: SiteRequest = run.site
    run.status = "running"

    def on_progress(s: Any) -> None:  # AreaState, called by the SDK while it polls
        run.jobs_done, run.jobs_total = s.succeeded, s.total

    try:
        request = build_request(site.analysis, site.polygon, site.params)
        buildings = site_buildings(site, fetch_public=True)
        # The SDK tiles, uploads, submits, polls (50 jobs per request) and merges.
        # A lost submit is resent with the same idempotency key (never billed
        # twice); a failed tile is sent again once. Wind uses the directional blend.
        run.result = run_area(
            client, request, site.polygon, buildings=buildings, on_progress=on_progress,
            max_tiles_override=site.max_tiles(),
        )
        store.finish(run, "done")
    except AreaRunError as exc:  # a tile failed twice or did not come back: no partial map
        log.warning("run %s incomplete: %s", run.id, exc)
        store.finish(run, "failed", "the run did not complete (one or more tiles failed); try again")
    except GeodataDependencyError:
        store.finish(run, "failed", GEODATA_HINT)
    except Exception:
        log.exception("run %s failed", run.id)  # full detail in the server log only
        store.finish(run, "failed", "run failed, see the server log")


@app.post("/runs", status_code=202)
def start_run(site: SiteRequest) -> dict:
    """Start a run, or return the run that already has these exact inputs."""
    check_site(site)  # 422 before anything is billed
    run, is_new = store.claim(site.key(), site)  # atomic: equal requests share one run
    if is_new:
        state["pool"].submit(execute, run)
    return {"run_id": run.id, "status": run.status, "cached": not is_new}


def get_run(run_id: str, done: bool = False) -> Run:
    if (run := store.get(run_id)) is None:
        raise HTTPException(404, "unknown or expired run")
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
def result_json(run_id: str, step: int = Query(1, ge=1, le=64)) -> dict:
    """The grid as JSON. One cell = 1 m, so 1 km² is 1 million values (tens of MB
    as JSON). Use `step` (keep every n-th row and column) for a light preview."""
    result = get_run(run_id, done=True).result
    # physical_grid() gives real values (NaN = no value). Always use it (or
    # to_list()); never read merged_grid, which is in the stored wire type.
    grid = result.physical_grid()[::step, ::step]
    return {
        "analysis": result.analysis_type,
        "bounds": list(result.bounds) if result.bounds else None,  # [w, s, e, n] of the GRID
        "shape": list(grid.shape),  # rows, cols
        "cell_m": step,
        "row0": "south",  # flip the rows to draw north up
        "legend": [result.min_legend, result.max_legend],
        "grid": [[None if v != v else v for v in row] for row in grid.tolist()],  # NaN -> null
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
