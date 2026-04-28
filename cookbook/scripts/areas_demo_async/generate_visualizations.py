"""Standalone visualization generator for the areas async demo.

Iterates over every area stored in the SQLite database, downloads and
merges tile results from the Infrared API, and produces a self-contained
Plotly HTML file per area.

Usage::

    python demos/areas_demo_async/generate_visualizations.py
    python demos/areas_demo_async/generate_visualizations.py --area barcelona_gracia
"""

from __future__ import annotations
from infrared_sdk.tiling.types import AreaResult
from infrared_sdk import InfraredClient
from visualize import generate_visualization
import db as demo_db

import argparse
import logging
import os
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

logger = logging.getLogger("generate_visualizations")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
DEFAULT_MAX_WORKERS = 10


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def merge_and_visualize(
    client: InfraredClient,
    area_name: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> str:
    """Download results, merge tiles, and generate visualization for one area.

    Returns the path to the generated HTML file, or an empty string on failure.
    """
    conn = demo_db.connect()
    try:
        schedules = demo_db.get_area_schedules(conn, area_name)
        if not schedules:
            logger.warning("No schedules found for area %s -- skipping", area_name)
            return ""

        results: dict[str, AreaResult] = {}

        for analysis_type, schedule in schedules.items():
            if analysis_type != "wind-speed":
                continue

            friendly = demo_db.FRIENDLY_NAMES.get(analysis_type, analysis_type)
            logger.info(
                "Area: %s — %s: merging (%d jobs)",
                area_name,
                friendly,
                len(schedule.jobs),
            )
            t0 = time.monotonic()
            area_result = client.merge_area_jobs(schedule, max_workers=max_workers)
            elapsed = time.monotonic() - t0
            results[schedule.analysis_type] = area_result
            logger.info(
                "Area: %s — %s: %d succeeded, %d failed, %d skipped (%.1fs)",
                area_name,
                friendly,
                area_result.succeeded_jobs,
                len(area_result.failed_jobs),
                len(area_result.skipped_jobs),
                elapsed,
            )

        output_path = generate_visualization(area_name, results, OUTPUT_DIR)
        logger.info("Area: %s — visualization saved: %s", area_name, output_path)
        return output_path

    except Exception:
        logger.exception("Failed to generate visualization for area %s", area_name)
        return ""
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Plotly visualizations for completed area analyses.",
    )
    parser.add_argument(
        "--area",
        help="Process only this area name (default: all areas in the DB).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Max parallel download threads per merge (default: %(default)s).",
    )
    args = parser.parse_args()

    conn = demo_db.connect()
    if args.area:
        area_names = [args.area]
    else:
        area_names = demo_db.get_area_names(conn)
    conn.close()

    if not area_names:
        logger.info("No areas found in the database.")
        return

    logger.info("Areas to process: %s", area_names)

    with InfraredClient(
        api_key=os.environ["INFRARED_API_KEY"],
        logger=logger,
    ) as client:
        for area_name in area_names:
            logger.info("Area: %s — processing", area_name)
            merge_and_visualize(client, area_name, max_workers=args.workers)

    logger.info("All areas processed.")


if __name__ == "__main__":
    main()
