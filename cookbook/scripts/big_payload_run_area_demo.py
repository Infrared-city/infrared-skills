"""Deliberate big-payload exercise via ``run_area_and_wait``.

Demonstrates the new big-payloads feature on the two SDK call sites
that an end-to-end area run actually exercises:

1. ``client.vegetation.convert_to_mesh`` — POST /convert/geojson-to-mesh.
   Called explicitly here with a synthetic feature collection above the
   5 MiB threshold so the envelope path fires.
2. ``client.ground_materials._clean`` — POST /ground-material/clean-v3.
   Called internally by ``client.ground_materials.get_area`` once the
   per-tile features are merged. For Barcelona Gracia the merged
   layers blow past 5 MiB on their own, so we delete the local GM cache
   to force a real fetch and see the envelope path log.

After both envelope hits, the script runs UTCI on the same polygon via
``run_area_and_wait`` and prints every per-tile ``job_id`` (captured
via the ``on_progress`` callback) plus the resulting ``AreaResult``.

Watch for these INFO lines from ``infrared_sdk._internal.big_payloads.core``::

    big_payloads: envelope path raw=<N> zip=<M> (<pct>% reduction)

That's the "yes the new feature handled this" signal.

Usage::

    python demos/big_payload_run_area_demo.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Dict

from dotenv import load_dotenv

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
)
from infrared_sdk.models import Location
from infrared_sdk.tiling.types import AreaState

# Reuse the Gracia polygon + .env from the async demo for parity.
DEMO_DIR = os.path.join(os.path.dirname(__file__), "areas_demo_async")
load_dotenv(os.path.join(DEMO_DIR, ".env"))

sys.path.insert(0, DEMO_DIR)
from submit_analyses import (  # noqa: E402  (sibling demo import)
    AREAS,
    TIME_PERIOD,
    _load_cached_buildings,
    _load_cached_vegetation,
    _round_layers_coords,
    _save_cached_buildings,
    _save_cached_vegetation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
logging.getLogger("infrared_sdk").setLevel(logging.INFO)

logger = logging.getLogger("big-payload-run-area")

CACHE_DIR = os.path.join(DEMO_DIR, "cache")
AREA_NAME = "barcelona_gracia"


def _human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n} B"


def _delete_gm_cache(area_name: str) -> None:
    """Wipe the ground-materials cache so get_area must fetch + clean."""
    for fname in os.listdir(CACHE_DIR):
        if fname.startswith(f"{area_name}_") and fname.endswith("_gm.json"):
            path = os.path.join(CACHE_DIR, fname)
            os.remove(path)
            logger.info("Deleted GM cache %s", path)


def _build_oversized_vegetation_collection(seed_features: Dict[str, dict]) -> dict:
    """Replicate real tree features into a >5 MiB FeatureCollection.

    The big-payloads threshold is on the JSON-encoded body. We replicate
    until the encoded body sails past 5 MiB so ``convert_to_mesh`` is
    forced into the envelope path.
    """
    features = list(seed_features.values())
    if not features:
        raise RuntimeError("no seed features available")

    # Pick a dummy reference point in Barcelona; convert_to_mesh requires it.
    body = {
        "type": "FeatureCollection",
        "referencePoint": [2.167, 41.391],
        "features": [],
    }

    # Replicate until we cross 5.5 MiB.
    target = int(5.5 * 1024 * 1024)
    multiplier = 0
    while len(json.dumps(body).encode("utf-8")) < target:
        multiplier += 1
        body["features"].extend(features)
    encoded = len(json.dumps(body).encode("utf-8"))
    logger.info(
        "Synthesised vegetation FeatureCollection: %d features (%dx replication), %s encoded",
        len(body["features"]),
        multiplier,
        _human_size(encoded),
    )
    return body


def main() -> None:
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

    polygon = AREAS[AREA_NAME]["polygon"]
    lat = AREAS[AREA_NAME]["lat"]
    lon = AREAS[AREA_NAME]["lon"]

    # Force GM re-fetch so the _clean envelope path fires.
    _delete_gm_cache(AREA_NAME)

    with InfraredClient(api_key=api_key, logger=logger) as client:
        # ---- 1. Buildings (cache OK; per-tile bodies are tiny anyway) ----
        area_buildings = _load_cached_buildings(AREA_NAME, polygon)
        if area_buildings is None:
            t0 = time.monotonic()
            area_buildings = client.buildings.get_area(polygon, max_tiles_override=120)
            _save_cached_buildings(AREA_NAME, polygon, area_buildings)
            logger.info(
                "Buildings fetched (%d, %.1fs)",
                area_buildings.total_buildings,
                time.monotonic() - t0,
            )
        else:
            logger.info(
                "Buildings loaded from cache (%d)", area_buildings.total_buildings
            )

        # ---- 2. Vegetation real fetch (cache OK) ----
        area_vegetation = _load_cached_vegetation(AREA_NAME, polygon)
        if area_vegetation is None:
            t0 = time.monotonic()
            area_vegetation = client.vegetation.get_area(
                polygon, max_tiles_override=120
            )
            _save_cached_vegetation(AREA_NAME, polygon, area_vegetation)
            logger.info(
                "Vegetation fetched (%d trees, %.1fs)",
                area_vegetation.total_trees,
                time.monotonic() - t0,
            )
        else:
            logger.info(
                "Vegetation loaded from cache (%d trees)", area_vegetation.total_trees
            )

        # ---- 3. Vegetation BIG-PAYLOAD demo: convert_to_mesh on a >5 MiB FC ----
        logger.info("=== Vegetation big-payload demo (convert_to_mesh) ===")
        big_fc = _build_oversized_vegetation_collection(area_vegetation.features)
        t0 = time.monotonic()
        try:
            meshes = client.vegetation.convert_to_mesh(big_fc)
            logger.info(
                "convert_to_mesh OK: %d meshes in %.1fs",
                len(meshes),
                time.monotonic() - t0,
            )
        except Exception as exc:
            logger.warning("convert_to_mesh failed: %s", exc)

        # ---- 4. Ground materials BIG-PAYLOAD demo (real) ----
        logger.info("=== Ground materials big-payload demo (_clean) ===")
        t0 = time.monotonic()
        area_gm = client.ground_materials.get_area(polygon, max_tiles_override=120)
        logger.info(
            "ground_materials.get_area: %d features / %d layers in %.1fs",
            area_gm.total_features,
            len(area_gm.layers),
            time.monotonic() - t0,
        )

        # Drop building layer + round, exactly like the async submitter does,
        # so per-tile job payloads stay reasonable.
        dropped = area_gm.layers.pop("building", None)
        if dropped is not None:
            logger.info(
                "Dropped 'building' GM layer (%d features) for run_area",
                len((dropped or {}).get("features", [])),
            )
        before = len(json.dumps(area_gm.layers).encode("utf-8"))
        _round_layers_coords(area_gm.layers, precision=6)
        after = len(json.dumps(area_gm.layers).encode("utf-8"))
        logger.info(
            "Rounded GM coords: %s → %s (%.1f%% smaller)",
            _human_size(before),
            _human_size(after),
            100 * (1 - after / before) if before else 0,
        )

        # ---- 5. run_area_and_wait UTCI ----
        logger.info("=== run_area_and_wait UTCI (afternoon) ===")
        weather_locs = client.weather.get_weather_file_from_location(lat=lat, lon=lon)
        weather_data = client.weather.filter_weather_data(
            identifier=weather_locs[0]["uuid"], time_period=TIME_PERIOD
        )

        utci_payload = UtciModelRequest.from_weatherfile_payload(
            payload=UtciModelBaseRequest(
                analysis_type=AnalysesName.thermal_comfort_index
            ),
            location=Location(latitude=lat, longitude=lon),
            time_period=TIME_PERIOD,
            weather_data=weather_data,
        )

        captured_job_ids: list[str] = []

        def _on_progress(state: AreaState) -> None:
            if not captured_job_ids:
                # First snapshot has the full job_id set; capture once.
                captured_job_ids.extend(state.job_states.keys())
                logger.info(
                    "Captured %d job_ids from first AreaState snapshot",
                    len(captured_job_ids),
                )
            logger.info(
                "progress: status=%s succeeded=%d running=%d pending=%d failed=%d total=%d",
                state.status,
                state.succeeded,
                state.running,
                state.pending,
                state.failed,
                state.total,
            )

        t0 = time.monotonic()
        result = client.run_area_and_wait(
            utci_payload,
            polygon,
            buildings=area_buildings.buildings,
            vegetation=area_vegetation.features,
            ground_materials=area_gm.layers,
            on_progress=_on_progress,
            max_tiles_override=120,
            area_timeout=1800,
        )
        elapsed = time.monotonic() - t0

        logger.info(
            "run_area_and_wait done in %.1fs: total=%d succeeded=%d failed=%d skipped=%d "
            "grid=%dx%d",
            elapsed,
            result.total_jobs,
            result.succeeded_jobs,
            len(result.failed_jobs),
            len(result.skipped_jobs),
            *result.grid_shape,
        )

        out_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(out_dir, exist_ok=True)
        ids_path = os.path.join(out_dir, "big_payload_run_area_job_ids.json")
        with open(ids_path, "w") as f:
            json.dump(
                {
                    "analysis_type": result.analysis_type,
                    "total": len(captured_job_ids),
                    "succeeded": result.succeeded_jobs,
                    "failed_jobs": result.failed_jobs,
                    "skipped_jobs": result.skipped_jobs,
                    "all_job_ids": captured_job_ids,
                },
                f,
                indent=2,
            )
        logger.info("Wrote job IDs → %s", ids_path)

        preview = ", ".join(captured_job_ids[:5])
        logger.info(
            "First 5 job_ids: %s (%d total)",
            preview,
            len(captured_job_ids),
        )


if __name__ == "__main__":
    main()
