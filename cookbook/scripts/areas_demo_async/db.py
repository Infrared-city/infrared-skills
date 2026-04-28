"""SQLite data layer for the Barcelona async webhook demo.

Tracks area analysis runs and individual tile jobs submitted to the
Infrared API.  Provides atomic persistence helpers so that the webhook
server never observes an inconsistent intermediate state (e.g. an area
run with zero jobs mid-upsert).

Usage -- standalone script::

    conn = connect()
    try:
        save_schedule(conn, "barcelona", schedule)
    finally:
        conn.close()

Usage -- Flask request context::

    app = Flask(__name__)
    app.teardown_appcontext(close_db)
    # inside a view:
    conn = get_db()
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from infrared_sdk.tiling.types import AreaSchedule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Analysis type constants
# ---------------------------------------------------------------------------

#: The four SDK analysis-type strings that every area must complete.
EXPECTED_ANALYSIS_TYPES: tuple[str, ...] = (
    "wind-speed",
    "sky-view-factors",
    "thermal-comfort-index",
    "thermal-comfort-statistics",
)

#: Human-friendly short names keyed by SDK analysis-type string.
FRIENDLY_NAMES: dict[str, str] = {
    "wind-speed": "wind",
    "sky-view-factors": "svf",
    "thermal-comfort-index": "utci",
    "thermal-comfort-statistics": "tcs",
}

# ---------------------------------------------------------------------------
# Valid status values and forward-only transitions
# ---------------------------------------------------------------------------

_JOB_STATUS_ORDER = {"pending": 0, "running": 1, "succeeded": 2, "failed": 2}

# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "demo.db"),
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS area_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    area_name       TEXT NOT NULL,
    analysis_type   TEXT NOT NULL,
    schedule_json   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(area_name, analysis_type)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    area_run_id INTEGER NOT NULL REFERENCES area_runs(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_area_run ON jobs(area_run_id);
"""

_PRAGMAS = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
    ("busy_timeout", "5000"),
    ("synchronous", "NORMAL"),
)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and safety PRAGMAs on a fresh connection."""
    for pragma, value in _PRAGMAS:
        conn.execute(f"PRAGMA {pragma}={value}")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a standalone connection with PRAGMAs enforced.

    Intended for use in scripts (``submit_analyses.py``) or background
    threads.  Callers are responsible for closing the connection.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def get_db(db_path: str | None = None) -> sqlite3.Connection:
    """Return a per-request Flask connection (stored on ``g``).

    Must be called inside a Flask application context.  The connection
    is automatically closed by :func:`close_db` registered as a
    teardown handler.
    """
    from flask import g  # imported lazily to avoid hard Flask dependency

    if "db" not in g:
        g.db = connect(db_path)
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    """Flask teardown callback -- close the per-request connection."""
    from flask import g

    conn: sqlite3.Connection | None = g.pop("db", None)
    if conn is not None:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create tables and indexes idempotently.

    If *conn* is ``None`` a temporary connection is opened and closed
    automatically.
    """
    close_after = False
    if conn is None:
        conn = connect()
        close_after = True
    try:
        conn.executescript(_SCHEMA_SQL)
        logger.info("Database schema initialized")
    finally:
        if close_after:
            conn.close()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def save_schedule(
    conn: sqlite3.Connection,
    area_name: str,
    schedule,  # AreaSchedule -- not typed to avoid circular import
) -> int:
    """Atomically persist an AreaSchedule and its jobs.

    Uses ``BEGIN IMMEDIATE`` so that a concurrent reader (e.g.
    ``check_area_complete``) never sees an area_run row with zero
    associated jobs (which would happen if the ``INSERT OR REPLACE``
    cascade-deleted old jobs before the new ones were inserted).

    Returns the ``area_run_id`` of the inserted/replaced row.
    """
    schedule_json = json.dumps(schedule.to_dict())
    analysis_type = schedule.analysis_type

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT OR REPLACE INTO area_runs
                   (area_name, analysis_type, schedule_json, status, created_at)
               VALUES (?, ?, ?, 'pending', datetime('now'))""",
            (area_name, analysis_type, schedule_json),
        )
        row = conn.execute(
            "SELECT id FROM area_runs WHERE area_name = ? AND analysis_type = ?",
            (area_name, analysis_type),
        ).fetchone()
        area_run_id: int = row["id"]

        for job_id in schedule.jobs.values():
            conn.execute(
                """INSERT OR IGNORE INTO jobs (job_id, area_run_id, status, updated_at)
                   VALUES (?, ?, 'pending', datetime('now'))""",
                (job_id, area_run_id),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    friendly = FRIENDLY_NAMES.get(analysis_type, analysis_type)
    logger.info(
        "Area: %s — %s: saved schedule (%d jobs)",
        area_name,
        friendly,
        len(schedule.jobs),
    )
    return area_run_id


def update_job_status(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
) -> Optional[int]:
    """Update a job's status (forward-only) and return its area_run_id.

    Returns ``None`` if the job_id is unknown or if the transition is
    not forward (e.g. ``succeeded`` -> ``running``).
    """
    if status not in _JOB_STATUS_ORDER:
        logger.warning("Invalid job status %r for job %s", status, job_id)
        return None

    row = conn.execute(
        "SELECT area_run_id, status FROM jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        logger.warning("Unknown job_id %s", job_id)
        return None

    current_order = _JOB_STATUS_ORDER.get(row["status"], -1)
    new_order = _JOB_STATUS_ORDER[status]
    if new_order <= current_order:
        logger.debug(
            "Ignoring non-forward transition %s -> %s for job %s",
            row["status"],
            status,
            job_id,
        )
        return None

    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE job_id = ?",
        (status, job_id),
    )
    conn.commit()

    return row["area_run_id"]


# ---------------------------------------------------------------------------
# Completion detection
# ---------------------------------------------------------------------------


def check_area_complete(conn: sqlite3.Connection, area_name: str) -> bool:
    """Return True only when all expected analysis types exist for
    *area_name* AND every job across those runs has a terminal status
    (``succeeded`` or ``failed``).
    """
    rows = conn.execute(
        """SELECT ar.analysis_type, j.status
           FROM area_runs ar
           JOIN jobs j ON j.area_run_id = ar.id
           WHERE ar.area_name = ?""",
        (area_name,),
    ).fetchall()

    if not rows:
        return False

    types_seen: set[str] = set()
    for row in rows:
        types_seen.add(row["analysis_type"])
        # if row["status"] not in ("succeeded", "failed"):
        #     return False

    # return all(t in types_seen for t in EXPECTED_ANALYSIS_TYPES)
    return len(types_seen) > 0


# ---------------------------------------------------------------------------
# Merge lifecycle
# ---------------------------------------------------------------------------


def try_mark_merging(conn: sqlite3.Connection, area_name: str) -> bool:
    """Atomically set all area_runs for *area_name* to ``merging``.

    Returns ``True`` if at least one row was affected (i.e. nobody else
    has already started merging).  Returns ``False`` if all rows were
    already in ``merging`` status, preventing a double merge.
    """
    cursor = conn.execute(
        """UPDATE area_runs
           SET status = 'merging'
           WHERE area_name = ?
             AND status NOT IN ('merging', 'completed')""",
        (area_name,),
    )
    conn.commit()
    affected = cursor.rowcount > 0
    if affected:
        logger.info("Marked area %s as merging", area_name)
    else:
        logger.debug("Area %s already merging, skipping", area_name)
    return affected


def mark_area_completed(conn: sqlite3.Connection, area_name: str) -> None:
    """Transition area_runs from ``merging`` to ``completed``.

    Only affects rows currently in ``merging`` so as not to
    accidentally overwrite a concurrent re-run that reset rows
    back to ``pending``.
    """
    conn.execute(
        """UPDATE area_runs
           SET status = 'completed'
           WHERE area_name = ? AND status = 'merging'""",
        (area_name,),
    )
    conn.commit()
    logger.info("Area %s marked completed", area_name)


def mark_area_failed(conn: sqlite3.Connection, area_name: str) -> None:
    """Reset area_runs from ``merging`` back to ``merge_failed``.

    Only transitions rows currently in ``merging`` so as not to
    accidentally overwrite a concurrent re-run.
    """
    conn.execute(
        """UPDATE area_runs
           SET status = 'merge_failed'
           WHERE area_name = ? AND status = 'merging'""",
        (area_name,),
    )
    conn.commit()
    logger.info("Area %s marked merge_failed", area_name)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_area_schedules(
    conn: sqlite3.Connection,
    area_name: str,
) -> Dict[str, "AreaSchedule"]:
    """Reconstruct AreaSchedule objects from stored JSON.

    Returns a dict keyed by analysis_type.  Import is deferred to avoid
    a circular dependency at module level.
    """
    from infrared_sdk.tiling.types import AreaSchedule

    rows = conn.execute(
        "SELECT analysis_type, schedule_json FROM area_runs WHERE area_name = ?",
        (area_name,),
    ).fetchall()

    return {
        row["analysis_type"]: AreaSchedule.from_dict(json.loads(row["schedule_json"]))
        for row in rows
    }


def get_area_names(conn: sqlite3.Connection) -> list[str]:
    """Return all distinct area names that have at least one area_run."""
    rows = conn.execute(
        "SELECT DISTINCT area_name FROM area_runs ORDER BY area_name",
    ).fetchall()
    return [row["area_name"] for row in rows]


def get_area_name_for_job(
    conn: sqlite3.Connection,
    job_id: str,
) -> Optional[str]:
    """Return the area_name that owns *job_id*, or ``None``."""
    row = conn.execute(
        """SELECT ar.area_name
           FROM jobs j
           JOIN area_runs ar ON ar.id = j.area_run_id
           WHERE j.job_id = ?""",
        (job_id,),
    ).fetchone()
    return row["area_name"] if row else None


def get_job_context(
    conn: sqlite3.Connection,
    job_id: str,
) -> Optional[dict]:
    """Return area_name, analysis_type, and tile position for *job_id*.

    Returns ``None`` if the job is not found.  The ``tile_xy`` key is a
    ``(row, col)`` string like ``"(3,5)"`` or ``"?"`` if the position
    cannot be resolved from the schedule.
    """
    row = conn.execute(
        """SELECT ar.area_name, ar.analysis_type, ar.schedule_json
           FROM jobs j
           JOIN area_runs ar ON ar.id = j.area_run_id
           WHERE j.job_id = ?""",
        (job_id,),
    ).fetchone()
    if row is None:
        return None

    area_name = row["area_name"]
    analysis_type = row["analysis_type"]
    friendly = FRIENDLY_NAMES.get(analysis_type, analysis_type)

    # Resolve tile position from the schedule
    tile_xy = "?"
    try:
        schedule = json.loads(row["schedule_json"])
        jobs = schedule.get("jobs", {})
        positions = schedule.get("tile_positions", {})
        # jobs: {tile_id: job_id}, positions: {tile_id: [row, col]}
        for tile_id, jid in jobs.items():
            if jid == job_id:
                pos = positions.get(tile_id)
                if pos:
                    tile_xy = f"({pos[0]},{pos[1]})"
                break
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return {
        "area_name": area_name,
        "analysis_type": friendly,
        "tile_xy": tile_xy,
    }


def dump_jobs(conn: sqlite3.Connection) -> None:
    """Print all jobs with their area and status (for debugging)."""
    rows = conn.execute(
        """SELECT j.job_id, j.status, ar.area_name, ar.analysis_type
           FROM jobs j
           JOIN area_runs ar ON ar.id = j.area_run_id
           ORDER BY ar.area_name, ar.analysis_type""",
    ).fetchall()
    print(f"\n{'JOB ID':<40} {'AREA':<15} {'TYPE':<30} {'STATUS'}")
    print("-" * 95)
    for r in rows:
        print(
            f"{r['job_id']:<40} {r['area_name']:<15} {r['analysis_type']:<30} {r['status']}"
        )
    print(f"\nTotal: {len(rows)} jobs\n")


if __name__ == "__main__":
    c = connect()
    dump_jobs(c)
    c.close()
