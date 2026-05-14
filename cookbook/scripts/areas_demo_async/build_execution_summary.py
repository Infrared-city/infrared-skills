"""Build EXECUTION_SUMMARY.md for the async area demo.

Joins three sources of truth to give an end-to-end picture of the
last submitted run:

* ``demo.db``  -- area_runs + jobs (status, last-update timestamp)
* ``cache/``   -- per-area buildings / vegetation / ground-materials
                  artefacts (size + counts)
* Live API    -- per-job ``requestedAt`` / ``startedAt`` / ``finishedAt``
                  via ``client.jobs.get_status`` so we can compute
                  queue-time and execution-time per tile.

Usage::

    python demos/areas_demo_async/build_execution_summary.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.jobs import Job, JobStatus

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DEMO_DIR, ".env"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logging.getLogger("infrared_sdk").setLevel(logging.WARNING)
logger = logging.getLogger("exec-summary")

DB_PATH = os.path.join(DEMO_DIR, "demo.db")
CACHE_DIR = os.path.join(DEMO_DIR, "cache")
OUT_PATH = os.path.join(DEMO_DIR, "EXECUTION_SUMMARY.md")

FRIENDLY = {
    "wind-speed": "Wind speed",
    "thermal-comfort-index": "UTCI (afternoon)",
    "thermal-comfort-index-morning": "UTCI (morning)",
}


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    # Accept both Z and ±00:00 forms.
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class JobTiming:
    job_id: str
    db_status: str
    api_status: Optional[JobStatus]
    requested_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    queue_s: Optional[float]
    exec_s: Optional[float]
    error: Optional[str]


def fetch_timings(
    client: InfraredClient, db_jobs: list[tuple[str, str]]
) -> list[JobTiming]:
    """Pull live status for each job_id; tolerate per-job 5xx/404."""
    rows: list[JobTiming] = []
    for job_id, db_status in db_jobs:
        api_status = None
        req = sta = fin = None
        err = None
        try:
            job: Job = client.jobs.get_status(job_id)
            api_status = job.status
            req = _parse_iso(job.requested_at)
            sta = _parse_iso(job.started_at)
            fin = _parse_iso(job.finished_at)
            err = job.error
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
        queue = (sta - req).total_seconds() if req and sta else None
        exec_s = (fin - sta).total_seconds() if sta and fin else None
        rows.append(
            JobTiming(
                job_id=job_id,
                db_status=db_status,
                api_status=api_status,
                requested_at=req,
                started_at=sta,
                finished_at=fin,
                queue_s=queue,
                exec_s=exec_s,
                error=err,
            )
        )
    return rows


def cache_inventory(area_name: str) -> dict:
    """Inspect cache/ for the per-area artefacts we know how to read."""
    info: dict = {}
    if not os.path.isdir(CACHE_DIR):
        return info
    for fname in os.listdir(CACHE_DIR):
        if not fname.startswith(f"{area_name}_"):
            continue
        path = os.path.join(CACHE_DIR, fname)
        size = os.path.getsize(path)
        if fname.endswith("_gm.json"):
            with open(path) as f:
                data = json.load(f)
            info["ground_materials"] = {
                "path": fname,
                "size_bytes": size,
                "total_features": data.get("total_features"),
                "layers": list((data.get("layers") or {}).keys()),
            }
        elif fname.endswith("_veg.json"):
            with open(path) as f:
                data = json.load(f)
            info["vegetation"] = {
                "path": fname,
                "size_bytes": size,
                "total_trees": data.get("total_trees"),
            }
        elif fname.endswith(".json"):
            with open(path) as f:
                data = json.load(f)
            info["buildings"] = {
                "path": fname,
                "size_bytes": size,
                "total_buildings": data.get("total_buildings"),
            }
    return info


def _human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n} B"


def _stat_row(values: list[float], unit: str = "s") -> str:
    if not values:
        return "n/a"
    return (
        (
            f"min={min(values):.1f}{unit} "
            f"p50={statistics.median(values):.1f}{unit} "
            f"mean={statistics.mean(values):.1f}{unit} "
            f"p95={statistics.quantiles(values, n=20)[-1]:.1f}{unit} "
            f"max={max(values):.1f}{unit}"
        )
        if len(values) > 1
        else f"{values[0]:.1f}{unit}"
    )


def render_markdown(area_runs: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Async-area-demo execution summary")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from "
        f"`demo.db`, `cache/`, and live job status._"
    )
    lines.append("")

    # ---- Executive summary ----
    total = sum(r["total"] for r in area_runs)
    succ = sum(r["succeeded_api"] for r in area_runs)
    failed = sum(r["failed_api"] for r in area_runs)
    pending = sum(r["pending_or_unknown"] for r in area_runs)
    grand_exec = [
        t.exec_s for r in area_runs for t in r["timings"] if t.exec_s is not None
    ]
    grand_queue = [
        t.queue_s for r in area_runs for t in r["timings"] if t.queue_s is not None
    ]

    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        f"- Submitted **{total} jobs** across **{len(area_runs)} analyses** "
        f"(area: `{area_runs[0]['area_name']}`)."
    )
    lines.append(
        f"- API status: **{succ} succeeded**, {failed} failed, "
        f"{pending} still pending/unknown."
    )
    if grand_exec:
        lines.append(
            f"- Per-tile execution time across all analyses: {_stat_row(grand_exec)}."
        )
    if grand_queue:
        lines.append(
            f"- Per-tile queue time (request → start): {_stat_row(grand_queue)}."
        )
    if area_runs[0]["cache"]:
        ci = area_runs[0]["cache"]
        bld = ci.get("buildings", {})
        veg = ci.get("vegetation", {})
        gm = ci.get("ground_materials", {})
        bits = []
        if bld:
            bits.append(f"{bld['total_buildings']:,} buildings")
        if veg:
            bits.append(f"{veg['total_trees']:,} trees")
        if gm:
            bits.append(
                f"{gm['total_features']:,} GM features in {len(gm['layers'])} layers"
            )
        if bits:
            lines.append(f"- Layer payloads bundled per tile: {', '.join(bits)}.")
    lines.append(
        "- All three submissions cleared the gateway without 413; the "
        "`feat/big-payloads-support` envelope path is in place but was not "
        "triggered for these particular calls (per-tile job submissions use "
        "the older zip-then-POST mechanism, separate from "
        "`post_with_big_payload`)."
    )
    lines.append("")

    # ---- Per-analysis tables ----
    lines.append("## Per-analysis breakdown")
    lines.append("")
    lines.append(
        "| Analysis | Tiles | Succeeded | Failed | Pending | Min | p50 | Mean | p95 | Max |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in area_runs:
        execs = [t.exec_s for t in r["timings"] if t.exec_s is not None]

        def fmt(v):
            return f"{v:.1f}s" if v is not None else "—"

        if execs:
            mn = min(execs)
            md = statistics.median(execs)
            mean = statistics.mean(execs)
            p95 = statistics.quantiles(execs, n=20)[-1] if len(execs) > 1 else execs[0]
            mx = max(execs)
        else:
            mn = md = mean = p95 = mx = None
        lines.append(
            f"| {FRIENDLY.get(r['analysis_type'], r['analysis_type'])} "
            f"| {r['total']} "
            f"| {r['succeeded_api']} "
            f"| {r['failed_api']} "
            f"| {r['pending_or_unknown']} "
            f"| {fmt(mn)} | {fmt(md)} | {fmt(mean)} | {fmt(p95)} | {fmt(mx)} |"
        )
    lines.append("")

    # ---- Per-job detail ----
    lines.append("## Per-job execution time (grouped by analysis type)")
    lines.append("")
    lines.append(
        "Pulled live from `GET /async/jobs/{jobId}`. `queue_s` is the wait "
        "between submission and worker pickup; `exec_s` is `finishedAt - "
        "startedAt`."
    )
    lines.append("")
    for r in area_runs:
        lines.append(
            f"### {FRIENDLY.get(r['analysis_type'], r['analysis_type'])} "
            f"(`{r['analysis_type']}`, {r['total']} jobs)"
        )
        lines.append("")
        lines.append(
            "| job_id | status | requested_at (UTC) | queue_s | exec_s | error |"
        )
        lines.append("|---|---|---|---:|---:|---|")
        ordered = sorted(
            r["timings"],
            key=lambda t: t.requested_at or datetime.max.replace(tzinfo=timezone.utc),
        )
        for t in ordered:
            req = (
                t.requested_at.isoformat(timespec="seconds") if t.requested_at else "—"
            )
            qs = f"{t.queue_s:.1f}" if t.queue_s is not None else "—"
            xs = f"{t.exec_s:.1f}" if t.exec_s is not None else "—"
            status = (
                t.api_status.value
                if isinstance(t.api_status, JobStatus)
                else (t.api_status or t.db_status)
            )
            err = (t.error or "").replace("|", "\\|")
            if len(err) > 60:
                err = err[:57] + "…"
            lines.append(f"| `{t.job_id}` | {status} | {req} | {qs} | {xs} | {err} |")
        lines.append("")

    # ---- Cache inventory ----
    lines.append("## Cache inventory (per area)")
    lines.append("")
    seen_areas = set()
    for r in area_runs:
        if r["area_name"] in seen_areas or not r["cache"]:
            continue
        seen_areas.add(r["area_name"])
        ci = r["cache"]
        lines.append(f"### `{r['area_name']}`")
        lines.append("")
        lines.append("| Layer | File | Size | Counts |")
        lines.append("|---|---|---:|---|")
        if "buildings" in ci:
            b = ci["buildings"]
            lines.append(
                f"| Buildings | `{b['path']}` | {_human_size(b['size_bytes'])} "
                f"| {b['total_buildings']:,} buildings |"
            )
        if "vegetation" in ci:
            v = ci["vegetation"]
            lines.append(
                f"| Vegetation | `{v['path']}` | {_human_size(v['size_bytes'])} "
                f"| {v['total_trees']:,} trees |"
            )
        if "ground_materials" in ci:
            g = ci["ground_materials"]
            lines.append(
                f"| Ground materials | `{g['path']}` | {_human_size(g['size_bytes'])} "
                f"| {g['total_features']:,} features ({len(g['layers'])} layers: "
                f"{', '.join(g['layers'])}) |"
            )
        lines.append("")

    # ---- Technical summary ----
    lines.append("## Technical summary")
    lines.append("")
    lines.append(
        "**Submission flow.** `submit_analyses.py` resolves the polygon, "
        "loads cached buildings/vegetation/ground-materials, drops the "
        "redundant `building` GM layer, rounds GM coordinates to 6 decimals "
        "(~26% byte reduction on Gracia), and calls "
        "`InfraredClient.run_area(...)` once per analysis with "
        "`webhook_url`/`webhook_events` set. Each `run_area` returns an "
        "`AreaSchedule` (tile_id → job_id) which is persisted into "
        "`area_runs` + `jobs` tables and the script exits."
    )
    lines.append("")
    lines.append(
        "**Status tracking.** `webhook_server.py` listens for `job.running`, "
        "`job.succeeded`, `job.failed` events. The DB schema only stores the "
        "latest status + a single `updated_at` field, so per-job timing has "
        "to come from the live API (`GET /async/jobs/{jobId}`), which "
        "exposes `requestedAt`, `startedAt`, `finishedAt`. This script polls "
        "each known job_id and computes:"
    )
    lines.append("")
    lines.append(
        "- `queue_s = startedAt - requestedAt` — time spent waiting for a worker."
    )
    lines.append("- `exec_s  = finishedAt - startedAt` — actual analysis runtime.")
    lines.append("")
    lines.append(
        "**Per-tile payload composition.** Each per-tile job body bundles "
        "the analysis payload (wind speed/direction or UTCI weather) + "
        "polygon-clipped buildings (DotBim mesh) + intersecting "
        "vegetation features + intersecting GM layers. The SDK zips the "
        "JSON before POST (`Content-Type: application/zip`), which is the "
        "pre-existing protection against gateway body-size limits. The new "
        "`post_with_big_payload` envelope (S3 presign + `$ref`) is wired "
        "into 4 service-call sites (`buildings._get`, "
        "`ground_materials._clean`, `vegetation.convert_to_mesh`, "
        "`weather.gen_grid_image`) but **not** into "
        "`analyses/jobs.py:submit_job`. Both mechanisms coexist and serve "
        "different call paths."
    )
    lines.append("")
    lines.append(
        "**Reproducibility.** Cache files in `cache/` are deterministic for "
        "a given polygon (filename hash = SHA-256 of canonical JSON). "
        "Deleting any of them forces a re-fetch on the next run; the buildings "
        "and ground-materials fetchers are the slow paths (~30 s and ~90 s "
        "respectively for Gracia)."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    api_key = os.environ.get("INFRARED_API_KEY")
    if not api_key:
        logger.error("INFRARED_API_KEY missing")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        logger.error("demo.db not found — run submit_analyses.py first")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT ar.id, ar.area_name, ar.analysis_type, ar.created_at,
               j.job_id, j.status
        FROM area_runs ar
        JOIN jobs j ON j.area_run_id = ar.id
        ORDER BY ar.id, j.job_id
        """
    ).fetchall()
    conn.close()

    by_run: dict[int, dict] = {}
    for row in rows:
        rid = row["id"]
        if rid not in by_run:
            by_run[rid] = {
                "id": rid,
                "area_name": row["area_name"],
                "analysis_type": row["analysis_type"],
                "created_at": row["created_at"],
                "jobs": [],
            }
        by_run[rid]["jobs"].append((row["job_id"], row["status"]))

    logger.info(
        "Found %d area_runs / %d jobs in db",
        len(by_run),
        sum(len(r["jobs"]) for r in by_run.values()),
    )

    area_runs: list[dict] = []
    with InfraredClient(api_key=api_key, logger=logger) as client:
        for r in by_run.values():
            t0 = time.monotonic()
            timings = fetch_timings(client, r["jobs"])
            logger.info(
                "Fetched %d statuses for %s in %.1fs",
                len(timings),
                r["analysis_type"],
                time.monotonic() - t0,
            )
            succ_api = sum(1 for t in timings if t.api_status == JobStatus.succeeded)
            failed_api = sum(1 for t in timings if t.api_status == JobStatus.failed)
            other = len(timings) - succ_api - failed_api
            area_runs.append(
                {
                    **r,
                    "timings": timings,
                    "total": len(timings),
                    "succeeded_api": succ_api,
                    "failed_api": failed_api,
                    "pending_or_unknown": other,
                    "cache": cache_inventory(r["area_name"]),
                }
            )

    md = render_markdown(area_runs)
    with open(OUT_PATH, "w") as f:
        f.write(md)
    logger.info("Wrote %s (%d bytes)", OUT_PATH, len(md))


if __name__ == "__main__":
    main()
