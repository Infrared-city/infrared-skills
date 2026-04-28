"""Fire-and-forget area analysis submitter.

Submits 4 analyses (wind, SVF, UTCI, TCS) for Barcelona and Vienna,
stores the resulting AreaSchedules in SQLite, and exits.  The webhook
server (``webhook_server.py``) handles the rest.

Usage::

    python demos/areas_demo_async/submit_analyses.py
"""

from __future__ import annotations
import db as demo_db
from infrared_sdk.webhooks.types import (
    WEBHOOK_EVENT_FAILED,
    WEBHOOK_EVENT_RUNNING,
    WEBHOOK_EVENT_SUCCEEDED,
)
from infrared_sdk.utils import LocationMixin, TimePeriod
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
    WindModelRequest,
    SvfModelRequest,
    TcsModelBaseRequest,
    TcsModelRequest,
    TcsSubtype,
)
from infrared_sdk import InfraredClient

import hashlib
import json
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

logger = logging.getLogger("submit")

# ---------------------------------------------------------------------------
# Area definitions
# ---------------------------------------------------------------------------

AREAS = {
    "barcelona_gracia": {
        "polygon": {
            "type": "Polygon",
            "coordinates": [
                [
                    [2.136285, 41.423627],
                    [2.13506, 41.424804],
                    [2.135344, 41.424402],
                    [2.135285, 41.424139],
                    [2.134859, 41.423737],
                    [2.134615, 41.423568],
                    [2.134346, 41.423137],
                    [2.13422, 41.422803],
                    [2.134303, 41.422555],
                    [2.134625, 41.422337],
                    [2.134273, 41.422238],
                    [2.133404, 41.422395],
                    [2.133009, 41.422552],
                    [2.132633, 41.422576],
                    [2.132316, 41.422554],
                    [2.13197, 41.422531],
                    [2.131243, 41.422633],
                    [2.130611, 41.422743],
                    [2.130349, 41.422712],
                    [2.129979, 41.42258],
                    [2.130685, 41.421804],
                    [2.131253, 41.421153],
                    [2.131898, 41.420361],
                    [2.132105, 41.419819],
                    [2.131245, 41.419448],
                    [2.130822, 41.419505],
                    [2.130504, 41.419959],
                    [2.129997, 41.420056],
                    [2.129799, 41.419738],
                    [2.129317, 41.41952],
                    [2.129909, 41.419607],
                    [2.13022, 41.418665],
                    [2.131827, 41.41842],
                    [2.134321, 41.417708],
                    [2.136199, 41.415874],
                    [2.137438, 41.414235],
                    [2.1431, 41.411491],
                    [2.14628, 41.409715],
                    [2.148497, 41.406892],
                    [2.148746, 41.406616],
                    [2.149024, 41.406888],
                    [2.149977, 41.405598],
                    [2.149923, 41.403208],
                    [2.151159, 41.400726],
                    [2.159545, 41.3967],
                    [2.170897, 41.405236],
                    [2.162304, 41.412331],
                    [2.161056, 41.414176],
                    [2.158948, 41.414635],
                    [2.157275, 41.416546],
                    [2.155465, 41.41512],
                    [2.154164, 41.415603],
                    [2.152695, 41.416812],
                    [2.15099, 41.417588],
                    [2.15115, 41.418498],
                    [2.150956, 41.420206],
                    [2.14949, 41.420933],
                    [2.143898, 41.42014],
                    [2.14004, 41.420232],
                    [2.138151, 41.421472],
                    [2.136995, 41.423515],
                    [2.136285, 41.423627],
                ]
            ],
        },
        "lat": 41.391,
        "lon": 2.167,
    },
    # "vienna_municipality": {
    #     "polygon": {
    #         "type": "Polygon",
    #         "coordinates": [
    #             [
    #                 [16.333752, 48.199335],
    #                 [16.333752, 48.203969],
    #                 [16.344051, 48.203969],
    #                 [16.344051, 48.199335],
    #                 [16.333752, 48.199335],
    #             ]
    #         ],
    #     },
    #     "lat": 48.201,
    #     "lon": 16.339,
    # },
}

# Wind parameters (shared across areas)
WIND_SPEED = 30  # m/s
WIND_DIRECTION = 225  # SW wind

# Summer afternoon -- single-hour period for thermal analyses
TIME_PERIOD = TimePeriod(
    start_month=7,
    start_day=1,
    start_hour=14,
    end_month=7,
    end_day=30,
    end_hour=14,
)

# Webhook configuration
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_EVENTS = [
    WEBHOOK_EVENT_RUNNING,
    WEBHOOK_EVENT_SUCCEEDED,
    WEBHOOK_EVENT_FAILED,
]

# Buildings cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _polygon_cache_key(polygon: dict) -> str:
    """Deterministic short hash of a polygon for use as a cache filename."""
    raw = json.dumps(polygon, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _load_cached_buildings(area_name: str, polygon: dict):
    """Return cached AreaBuildings or None."""
    from infrared_sdk.buildings.types import AreaBuildings

    path = os.path.join(CACHE_DIR, f"{area_name}_{_polygon_cache_key(polygon)}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return AreaBuildings.model_validate_json(f.read())
    except Exception as exc:
        logger.warning("Cache load failed for %s, will re-fetch: %s", area_name, exc)
        return None


def _save_cached_buildings(area_name: str, polygon: dict, area_buildings) -> None:
    """Persist AreaBuildings to a JSON cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{area_name}_{_polygon_cache_key(polygon)}.json")
    with open(path, "w") as f:
        f.write(area_buildings.model_dump_json())
    logger.info("Area: %s — buildings cached", area_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_payloads(
    weather_data: list,
    lat: float,
    lon: float,
) -> list:
    """Build the 4 analysis payloads for one area."""
    wind_payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    svf_payload = SvfModelRequest(
        analysis_type=AnalysesName.sky_view_factors,
    )

    utci_payload = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(
            analysis_type=AnalysesName.thermal_comfort_index,
        ),
        location=LocationMixin(latitude=lat, longitude=lon),
        time_period=TIME_PERIOD,
        weather_data=weather_data,
    )

    tcs_payload = TcsModelRequest.from_weatherfile_payload(
        payload=TcsModelBaseRequest(
            analysis_type=AnalysesName.thermal_comfort_statistics,
            subtype=TcsSubtype.thermal_comfort,
        ),
        location=LocationMixin(latitude=lat, longitude=lon),
        time_period=TIME_PERIOD,
        weather_data=weather_data,
    )

    return [wind_payload, utci_payload, svf_payload, tcs_payload]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL is not set in .env -- aborting")
        raise SystemExit(1)

    # Initialise the database and clean previous run
    demo_db.init_db()
    conn = demo_db.connect()
    conn.execute("DELETE FROM jobs")
    conn.execute("DELETE FROM area_runs")
    conn.commit()
    logger.info("Database cleaned")

    try:
        with InfraredClient(
            api_key=os.environ["INFRARED_API_KEY"],
            logger=logger,
        ) as client:
            for area_name, area_cfg in AREAS.items():
                polygon = area_cfg["polygon"]
                lat = area_cfg["lat"]
                lon = area_cfg["lon"]

                logger.info(
                    "Area: %s — starting (lat=%.3f, lon=%.3f)",
                    area_name,
                    lat,
                    lon,
                )

                # 1. Preview area
                preview = client.preview_area(polygon, max_tiles_override=150)
                logger.info(
                    "Area: %s — preview: %d tiles, ~%.0fs estimated",
                    area_name,
                    preview.tile_count,
                    preview.estimated_time_s,
                )

                # 2. Fetch buildings (cached)
                area_buildings = _load_cached_buildings(area_name, polygon)

                if area_buildings is not None:
                    logger.info(
                        "Area: %s — buildings loaded from cache (%d)",
                        area_name,
                        area_buildings.total_buildings,
                    )
                else:
                    t_bldg = time.monotonic()
                    area_buildings = client.buildings.get_buildings_in_area(
                        polygon=polygon,
                        max_tiles_override=150,
                    )
                    logger.info(
                        "Area: %s — buildings fetched (%d, %.1fs)",
                        area_name,
                        area_buildings.total_buildings,
                        time.monotonic() - t_bldg,
                    )
                    _save_cached_buildings(area_name, polygon, area_buildings)

                # 3. Fetch weather data
                weather_locations = client.utilities.get_weather_file_from_location(
                    lat=lat,
                    lon=lon,
                )
                weather_id = weather_locations[0]["uuid"]

                weather_data = client.utilities.filter_weather_data(
                    identifier=weather_id,
                    time_period=TIME_PERIOD,
                )
                logger.info(
                    "Area: %s — weather data ready (%d points)",
                    area_name,
                    len(weather_data),
                )

                # 4. Build payloads
                payloads = _build_payloads(weather_data, lat, lon)

                # 5. Submit each payload individually and persist immediately
                for payload in payloads:
                    schedule = client.run_area(
                        payload,
                        polygon,
                        buildings=area_buildings.buildings,
                        webhook_url=WEBHOOK_URL,
                        webhook_events=WEBHOOK_EVENTS,
                        max_tiles_override=150,
                    )

                    # Persist to DB immediately after submission
                    demo_db.save_schedule(conn, area_name, schedule)

                    friendly = demo_db.FRIENDLY_NAMES.get(
                        schedule.analysis_type,
                        schedule.analysis_type,
                    )
                    failed = len(schedule.failed_submissions)
                    submitted = len(schedule.jobs)
                    logger.info(
                        "Area: %s — %s scheduled (%d tiles, %d jobs%s)",
                        area_name,
                        friendly,
                        len(schedule.tile_positions),
                        submitted,
                        f", {failed} failed" if failed else "",
                    )

        logger.info(
            "All analyses submitted — start the webhook server to receive results."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
