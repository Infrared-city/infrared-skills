"""Standalone visualization generator for the areas async demo.

Iterates over every area stored in the SQLite database, downloads and
merges tile results from the Infrared API, and produces a self-contained
Plotly HTML file per area.

Usage::

    python demos/areas_demo_async/generate_visualizations.py
    python demos/areas_demo_async/generate_visualizations.py --area barcelona_gracia
"""

from __future__ import annotations
from infrared_sdk.tiling.types import AreaResult, TileProgress
from infrared_sdk import InfraredClient
from visualize import generate_visualization
import db as demo_db

import argparse
import logging
import os
import time
from collections import Counter

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
# Tile-progress metrics
# ---------------------------------------------------------------------------


class TileMetrics:
    """Aggregates per-tile progress events for a single fetch.

    Counts one event per tile (last status wins for a given tile id) so
    that re-emitted states (e.g. ``running`` → ``completed``) don't
    double-count.
    """

    def __init__(self) -> None:
        self._last_status: dict[str, str] = {}
        self.total: int = 0

    def __call__(self, progress: TileProgress) -> None:
        self._last_status[progress.tile_id] = progress.status
        self.total = progress.total_count

    @property
    def status_counts(self) -> Counter[str]:
        return Counter(self._last_status.values())

    def summary(self) -> str:
        c = self.status_counts
        ok = c.get("completed", 0)
        failed = c.get("failed", 0)
        skipped = c.get("skipped", 0)
        running = c.get("running", 0)
        return (
            f"{ok}/{self.total} ok, {failed} failed, "
            f"{skipped} skipped, {running} still-running"
        )


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
        polygon: dict | None = None

        for analysis_type, schedule in schedules.items():
            if analysis_type not in demo_db.EXPECTED_ANALYSIS_TYPES:
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
            # Key by the DB analysis_type (loop variable) rather than
            # schedule.analysis_type — the demo reuses "thermal-comfort-index"
            # under two DB keys ("…" and "…-morning") for diurnal comparison.
            results[analysis_type] = area_result
            polygon = area_result.polygon
            logger.info(
                "Area: %s — %s: %d succeeded, %d failed, %d skipped (%.1fs)",
                area_name,
                friendly,
                area_result.succeeded_jobs,
                len(area_result.failed_jobs),
                len(area_result.skipped_jobs),
                elapsed,
            )

        ground_materials = None
        vegetation = None
        if polygon is not None:
            gm_metrics = TileMetrics()
            try:
                t0 = time.monotonic()
                ground_materials = client.ground_materials.get_area(
                    polygon,
                    on_progress=gm_metrics,
                    max_tiles_override=120,
                )
                wall = time.monotonic() - t0
                per_layer = ", ".join(
                    f"{name}={len((fc or {}).get('features', []))}"
                    for name, fc in ground_materials.layers.items()
                )
                features_per_s = (
                    ground_materials.total_features / wall if wall > 0 else 0.0
                )
                logger.info(
                    "Area: %s — ground materials: %d features / %d layers "
                    "in %.1fs (%.1f feat/s) | tiles: %s | per-layer: %s",
                    area_name,
                    ground_materials.total_features,
                    len(ground_materials.layers),
                    wall,
                    features_per_s,
                    gm_metrics.summary(),
                    per_layer or "(none)",
                )
            except Exception:
                logger.exception(
                    "Area: %s — ground materials fetch failed after tiles=%s; "
                    "panel omitted",
                    area_name,
                    gm_metrics.summary(),
                )

            veg_metrics = TileMetrics()
            try:
                t0 = time.monotonic()
                vegetation = client.vegetation.get_area(
                    polygon,
                    on_progress=veg_metrics,
                    max_tiles_override=120,
                )
                wall = time.monotonic() - t0
                trees_per_s = vegetation.total_trees / wall if wall > 0 else 0.0
                logger.info(
                    "Area: %s — vegetation: %d trees in %.1fs (%.1f trees/s) "
                    "| tiles: %s",
                    area_name,
                    vegetation.total_trees,
                    wall,
                    trees_per_s,
                    veg_metrics.summary(),
                )
            except Exception:
                logger.exception(
                    "Area: %s — vegetation fetch failed after tiles=%s; trees omitted",
                    area_name,
                    veg_metrics.summary(),
                )

        output_path = generate_visualization(
            area_name,
            results,
            OUTPUT_DIR,
            ground_materials=ground_materials,
            vegetation=vegetation,
        )
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
