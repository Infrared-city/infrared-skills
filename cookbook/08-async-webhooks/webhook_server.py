"""Flask webhook receiver for the areas async demo.

Receives Standard Webhooks events from the Infrared API, verifies
HMAC signatures, tracks job status in SQLite, and triggers merge +
Plotly visualization in a background thread when all analyses for
an area complete.

Usage::

    python webhook_server.py
"""

from __future__ import annotations

import db as demo_db
from infrared_sdk.webhooks.service import WebhooksServiceClient
from flask import Flask, request

import json
import logging
import os
import threading
import time

from dotenv import load_dotenv

# Load .env from the same directory as this script
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
# Suppress raw URL / HTTP logs from the SDK
logging.getLogger("infrared_sdk").setLevel(logging.WARNING)

logger = logging.getLogger("webhook_server")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB
app.teardown_appcontext(demo_db.close_db)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# Event type -> DB job status mapping
# ---------------------------------------------------------------------------

_EVENT_STATUS_MAP: dict[str, str] = {
    "job.running": "running",
    "job.succeeded": "succeeded",
    "job.failed": "failed",
}

# ---------------------------------------------------------------------------
# Event processing (shared by request handler and retry thread)
# ---------------------------------------------------------------------------

RETRY_DELAY_S = 5
MAX_RETRIES = 3


def _process_event(job_id: str, new_status: str, attempt: int = 1) -> None:
    """Process a single webhook event against the DB.

    Opens its own connection so it works both inside Flask requests and
    from a background retry thread.
    """
    conn = demo_db.connect()
    try:
        ctx = demo_db.get_job_context(conn, job_id)
        if ctx is None:
            if attempt < MAX_RETRIES:
                logger.info(
                    "Job: %s Status: %s — unknown, retrying (%d/%d)",
                    job_id,
                    new_status,
                    attempt,
                    MAX_RETRIES,
                )
                threading.Thread(
                    target=_retry_event,
                    args=(job_id, new_status, attempt + 1),
                    daemon=True,
                ).start()
            else:
                logger.warning(
                    "Job: %s Status: %s — unknown after %d attempts, giving up",
                    job_id,
                    new_status,
                    MAX_RETRIES,
                )
            return

        area = ctx["area_name"]
        atype = ctx["analysis_type"]
        tile = ctx["tile_xy"]

        # Forward-only status update
        area_run_id = demo_db.update_job_status(conn, job_id, new_status)
        if area_run_id is not None:
            logger.info(
                "Area: %s Job: %s Status: %s Tile: %s %s — status updated",
                area,
                job_id,
                new_status,
                tile,
                atype,
            )

        # Check completion only on terminal events
        if new_status not in ("succeeded", "failed"):
            return

        if not demo_db.check_area_complete(conn, area):
            return

        logger.info("Area: %s — all jobs complete, starting merge", area)

    finally:
        conn.close()


def _retry_event(job_id: str, new_status: str, attempt: int) -> None:
    """Wait then retry processing an event (runs in a background thread)."""
    time.sleep(RETRY_DELAY_S)
    _process_event(job_id, new_status, attempt)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive and process a Standard Webhooks event."""
    # 1. Read raw body FIRST (before get_json parses it)
    raw_body = request.get_data()

    # 2. Normalize headers
    headers = {k.lower(): v for k, v in request.headers}

    # 3. Verify HMAC signature
    if not WebhooksServiceClient.verify_signature(
        payload_body=raw_body,
        headers=headers,
        secret=WEBHOOK_SECRET,
    ):
        logger.warning("Signature verification failed")
        return {"error": "invalid signature"}, 401

    # 4. Parse JSON payload from raw body (avoid Flask's Content-Type check)
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}

    # Support both Standard Webhooks format (type + data.jobId) and the
    # flat Lambda format (status + jobId at top level).
    event_type = payload.get("type", "")
    if not event_type and "status" in payload:
        event_type = f"job.{payload['status']}"
    job_id = payload.get("data", {}).get("jobId", "") or payload.get("jobId", "")

    # 5. Map event type to DB status
    new_status = _EVENT_STATUS_MAP.get(event_type)
    if not new_status or not job_id:
        logger.debug(
            "Ignoring event: type=%s job_id=%s",
            event_type,
            job_id,
        )
        return {"status": "ok"}, 200

    # 6. Process event (retries in background if job not yet in DB)
    _process_event(job_id, new_status)

    return {"status": "ok"}, 200


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Initialise DB schema on startup
    demo_db.init_db()

    port = int(os.environ.get("PORT", 8000))
    logger.info("Starting webhook server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
