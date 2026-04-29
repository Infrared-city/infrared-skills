"""Minimal Flask webhook receiver for Infrared async job notifications.

Run this in a terminal alongside ``07_async_and_webhooks.ipynb`` to see
what the dispatcher actually POSTs when jobs change status.

**This receiver verifies every incoming request via the Standard Webhooks
HMAC-SHA256 signature** (the same scheme the Infrared SDK exposes through
``client.webhooks.verify_signature``). Anything that doesn't carry a
valid signature is rejected with HTTP 401 and never written to disk.

Usage::

    pip install flask
    export INFRARED_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python webhook_receiver.py

The secret is the value Infrared returns from
``client.webhooks.register(url=..., type=...)``. Re-use the same secret
on the receiver and on the registered endpoint, otherwise valid
deliveries will get 401'd.

The Infrared dispatcher needs a publicly reachable URL, so you'll
typically expose this via a tunnel (ngrok, cloudflared, tailscale
funnel) and register the public URL with
``client.webhooks.register(url=..., type=...)``.

Quickstart with cloudflared (no signup)::

    cloudflared tunnel --url http://localhost:8080

then copy the printed ``https://<random>.trycloudflare.com`` and append
``/infrared`` -- that's the URL to register.

Dev-only escape hatch: setting ``INFRARED_WEBHOOK_INSECURE=1`` disables
signature verification. Do **not** use it on a publicly reachable
endpoint; anyone who guesses the URL will be able to write arbitrary
files into ``webhook_log/``.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

try:
    from flask import Flask, request, jsonify, abort
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Flask is required for webhook_receiver.py. Install with `pip install flask`."
    ) from exc

from infrared_sdk.webhooks.service import WebhooksServiceClient


PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))
LOG_DIR = os.path.join(os.path.dirname(__file__), "webhook_log")
os.makedirs(LOG_DIR, exist_ok=True)

WEBHOOK_SECRET: str | None = os.environ.get("INFRARED_WEBHOOK_SECRET")
INSECURE: bool = os.environ.get("INFRARED_WEBHOOK_INSECURE") == "1"
SIGNATURE_TOLERANCE_S: int = int(os.environ.get("INFRARED_WEBHOOK_TOLERANCE_S", "300"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("webhook_receiver")

if not WEBHOOK_SECRET and not INSECURE:
    raise SystemExit(
        "INFRARED_WEBHOOK_SECRET is not set. The receiver refuses to start "
        "without a webhook secret because anyone who finds the public URL "
        "could otherwise forge events. Set the secret returned by "
        "client.webhooks.register(...), or set INFRARED_WEBHOOK_INSECURE=1 "
        "for local-only testing."
    )

if INSECURE:
    logger.warning(
        "INFRARED_WEBHOOK_INSECURE=1 is set: signature verification is "
        "DISABLED. Do not expose this endpoint to the public internet."
    )


app = Flask(__name__)


@app.route("/infrared", methods=["POST"])
def infrared_webhook():
    """Receive an Infrared job notification (signature-verified)."""
    raw_body = request.get_data(cache=False)  # bytes, before any parsing
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not INSECURE:
        # Narrow Optional[str] -> str. The startup guard above guarantees
        # WEBHOOK_SECRET is set whenever INSECURE is False.
        assert WEBHOOK_SECRET is not None
        ok = WebhooksServiceClient.verify_signature(
            payload_body=raw_body,
            headers=headers,
            secret=WEBHOOK_SECRET,
            tolerance=SIGNATURE_TOLERANCE_S,
        )
        if not ok:
            logger.warning(
                "Rejected webhook with invalid/missing signature from %s "
                "(webhook-id=%s, webhook-timestamp=%s)",
                request.remote_addr,
                headers.get("webhook-id"),
                headers.get("webhook-timestamp"),
            )
            abort(401)

    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Verified signature but body is not valid JSON; rejecting.")
        abort(400)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    fname = os.path.join(LOG_DIR, f"hook_{timestamp}_{os.urandom(3).hex()}.json")
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(
            {
                "received_at_utc": timestamp,
                "headers": dict(request.headers),
                "body": body,
            },
            f,
            indent=2,
            default=str,
        )
    logger.info(
        "Verified webhook: event=%s job_id=%s status=%s -> %s",
        body.get("event") or body.get("type"),
        body.get("jobId") or body.get("job_id"),
        body.get("status"),
        fname,
    )
    return jsonify({"ok": True}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "received_count": len(os.listdir(LOG_DIR))}), 200


if __name__ == "__main__":
    mode = "INSECURE (no signature check)" if INSECURE else "verifying HMAC signatures"
    logger.info(
        "Listening on 0.0.0.0:%d  (POST /infrared, GET /health) -- %s", PORT, mode
    )
    logger.info("Logs being written to %s", LOG_DIR)
    app.run(host="0.0.0.0", port=PORT)
