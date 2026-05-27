"""Smoke-test for POST /convert/geojson-to-mesh + $ref response handling.

Sends a synthetic GeoJSON FeatureCollection of tree points to the
utilities service and prints the resulting meshes. Works against local,
staging, and production.

Usage::

    # Local utilities service (http://localhost:8080)
    python demos/demo_geojson_to_mesh.py --local

    # Local on a custom port
    python demos/demo_geojson_to_mesh.py --local --port 3000

    # Staging (requires INFRARED_API_KEY)
    python demos/demo_geojson_to_mesh.py --staging

    # Production (default, requires INFRARED_API_KEY)
    python demos/demo_geojson_to_mesh.py

    # Control feature count (large counts trigger $ref offloading)
    python demos/demo_geojson_to_mesh.py --local --count 5000

For $ref testing against a local server:
  Set GATEWAY_BASE_URL=https://api-test.infrared.city and
  BIG_RESPONSE_THRESHOLD_BYTES=1 in the utilities-service .env, then
  run with any --count value.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import time

from dotenv import load_dotenv

from infrared_sdk.vegetation.service import VegetationServiceClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("demo_geojson_to_mesh")

_PRODUCTION_URL = "https://api.infrared.city/v2/utils"
_STAGING_URL = "https://api-test.infrared.city/utils"

# Reference point: Vienna city centre
_REF_LON = 16.3738
_REF_LAT = 48.2082


def _build_feature_collection(count: int) -> dict:
    """Build a synthetic FeatureCollection of ``count`` tree points.

    Points are laid out on a square grid around the Vienna reference point,
    spaced ~10 m apart. Each feature carries a ``height`` property so the
    utilities service can scale a mesh without a registry lookup.
    """
    cols = math.ceil(math.sqrt(count))
    spacing_deg = 10 / 111_320  # ~10 m in degrees latitude

    features = []
    for i in range(count):
        row, col = divmod(i, cols)
        lon = _REF_LON + col * spacing_deg
        lat = _REF_LAT + row * spacing_deg
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"height": 6.0},
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "referencePoint": [_REF_LON, _REF_LAT],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="geojson-to-mesh smoke test")
    env_group = parser.add_mutually_exclusive_group()
    env_group.add_argument(
        "--local", action="store_true", help="Target http://localhost:<port>"
    )
    env_group.add_argument(
        "--staging", action="store_true", help="Target staging environment"
    )
    env_group.add_argument(
        "--production", action="store_true", help="Target production (default)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Local port (default: 8080)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of tree features to send (default: 100)",
    )
    args = parser.parse_args()

    api_key = os.getenv("INFRARED_API_KEY", "")

    if args.local:
        env_label = f"local (localhost:{args.port})"
        base_url = f"http://localhost:{args.port}"
    elif args.staging:
        env_label = "staging"
        base_url = _STAGING_URL
    else:
        env_label = "production"
        base_url = _PRODUCTION_URL

    logger.info("env=%s  base_url=%s  features=%d", env_label, base_url, args.count)

    fc = _build_feature_collection(args.count)

    with VegetationServiceClient(
        api_key=api_key, base_url=base_url, logger=logger
    ) as client:
        t0 = time.monotonic()
        meshes = client.convert_to_mesh(fc)
        elapsed = time.monotonic() - t0

    logger.info("--- result ---")
    logger.info("features sent : %d", args.count)
    logger.info("meshes received: %d  (%.2f s)", len(meshes), elapsed)

    if meshes:
        first = meshes[0]
        logger.info(
            "first mesh — id=%s  coords=%d  indices=%d",
            first.get("mesh_id"),
            len(first.get("coordinates", [])),
            len(first.get("indices", [])),
        )
    else:
        logger.warning("no meshes returned — check server logs")


if __name__ == "__main__":
    main()
