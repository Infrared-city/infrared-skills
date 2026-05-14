"""Deliberate big-payload exercise.

Builds a grid whose JSON serialization comfortably exceeds the
5 MiB ``INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES`` default and POSTs it
to ``/analysis/generate-image`` via :meth:`WeatherServiceClient.gen_grid_image`.

What to watch for in the logs (INFO level on ``infrared_sdk``):

    big_payloads: envelope path raw=<N> zip=<M> (...)

That single line is the "yes, the new feature handled this request"
signal — the SDK zipped the body, presigned an S3 upload, PUT the zip,
and POSTed the ``$ref`` envelope instead of the raw JSON. Without the
feature the gateway would 413.

Usage::

    python demos/big_payload_demo.py
    python demos/big_payload_demo.py --side 900   # ~9 MiB grid
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time

from dotenv import load_dotenv

from infrared_sdk import InfraredClient

load_dotenv(os.path.join(os.path.dirname(__file__), "areas_demo_async", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
# Surface the big-payload envelope-path INFO line.
logging.getLogger("infrared_sdk").setLevel(logging.INFO)

logger = logging.getLogger("big-payload-demo")


def _human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n} B"


def build_grid(side: int, seed: int = 42) -> list[list[float]]:
    """Random ``side x side`` float grid. ~12 bytes/cell once JSON-encoded."""
    rng = random.Random(seed)
    return [
        [round(rng.uniform(-50.0, 50.0), 6) for _ in range(side)] for _ in range(side)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--side",
        type=int,
        default=750,
        help="Grid side length. 750 → ~6.4 MiB JSON (above 5 MiB threshold).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("INFRARED_API_KEY")
    if not api_key:
        logger.error("INFRARED_API_KEY not set — aborting")
        sys.exit(1)

    threshold = int(
        os.environ.get("INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES", 5 * 1024 * 1024)
    )
    enabled = (
        os.environ.get("INFRARED_BIG_PAYLOADS_ENABLED", "true").strip().lower()
        == "true"
    )
    logger.info("big-payloads enabled=%s threshold=%s", enabled, _human_size(threshold))

    t0 = time.monotonic()
    grid = build_grid(args.side)
    raw = json.dumps({"grid": grid, "analysis_type": "wind-speed"}).encode("utf-8")
    logger.info(
        "Built grid %dx%d in %.1fs — JSON body %s (%s threshold)",
        args.side,
        args.side,
        time.monotonic() - t0,
        _human_size(len(raw)),
        "ABOVE" if len(raw) > threshold else "below",
    )

    with InfraredClient(api_key=api_key, logger=logger) as client:
        t0 = time.monotonic()
        png = client.weather.gen_grid_image(grid=grid, analysis_type="wind-speed")
        logger.info(
            "gen_grid_image returned %s in %.1fs",
            _human_size(len(png)),
            time.monotonic() - t0,
        )


if __name__ == "__main__":
    main()
