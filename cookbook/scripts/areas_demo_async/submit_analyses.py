"""Fire-and-forget area analysis submitter.

Submits 2 analyses (wind, UTCI) for each configured area, stores the
resulting AreaSchedules in SQLite, and exits.  The webhook server
(``webhook_server.py``) handles the rest.

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
from infrared_sdk.models import Location, TimePeriod
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
    WindModelRequest,
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

# Summer early-morning -- second UTCI window for diurnal comparison.
MORNING_TIME_PERIOD = TimePeriod(
    start_month=7,
    start_day=1,
    start_hour=9,
    end_month=7,
    end_day=30,
    end_hour=9,
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

    cache_key = _polygon_cache_key(polygon)
    path = os.path.join(CACHE_DIR, f"{area_name}_{cache_key}.json")
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
    cache_key = _polygon_cache_key(polygon)
    path = os.path.join(CACHE_DIR, f"{area_name}_{cache_key}.json")
    with open(path, "w") as f:
        f.write(area_buildings.model_dump_json())
    logger.info("Area: %s — buildings cached", area_name)


# ---------------------------------------------------------------------------
# Ground-materials cache (raw — layer filtering applied after load/save)
# ---------------------------------------------------------------------------


def _gm_cache_path(area_name: str, polygon: dict) -> str:
    return os.path.join(CACHE_DIR, f"{area_name}_{_polygon_cache_key(polygon)}_gm.json")


def _load_cached_ground_materials(area_name: str, polygon: dict):
    """Return cached AreaGroundMaterials or None."""
    from infrared_sdk.layers.ground_materials import AreaGroundMaterials

    path = _gm_cache_path(area_name, polygon)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return AreaGroundMaterials(
            layers=data["layers"],
            polygon=data["polygon"],
            total_features=data["total_features"],
            execution_time=data.get("execution_time", 0.0),
        )
    except Exception as exc:
        logger.warning("GM cache load failed for %s, will re-fetch: %s", area_name, exc)
        return None


def _save_cached_ground_materials(area_name: str, polygon: dict, area_gm) -> None:
    """Persist AreaGroundMaterials (raw) to a JSON cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _gm_cache_path(area_name, polygon)
    data = {
        "layers": area_gm.layers,
        "polygon": area_gm.polygon,
        "total_features": area_gm.total_features,
        "execution_time": area_gm.execution_time,
    }
    with open(path, "w") as f:
        json.dump(data, f)
    logger.info("Area: %s — ground materials cached", area_name)


# ---------------------------------------------------------------------------
# Debug helpers (payload-size logging for 413 investigation)
# ---------------------------------------------------------------------------


def _human_size(n_bytes: int) -> str:
    """Render bytes as KB/MB with one decimal."""
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.2f} MB"
    if n_bytes >= 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes} B"


def _round_coords(value, precision: int):
    """Recursively round floats inside a GeoJSON ``coordinates`` tree.

    Walks nested lists and replaces each numeric leaf with ``round(leaf,
    precision)``.  Non-numeric leaves are returned unchanged.
    """
    if isinstance(value, list):
        return [_round_coords(v, precision) for v in value]
    if isinstance(value, float):
        return round(value, precision)
    return value


def _round_layers_coords(layers: dict, precision: int = 6) -> None:
    """Round all coordinate floats in a ``{layer: FeatureCollection}`` dict.

    Mutates *layers* in place.  6 decimals ≈ 11 cm precision, well below
    anything ground-material assignment cares about.
    """
    for fc in layers.values():
        if not isinstance(fc, dict):
            continue
        for feat in fc.get("features", []) or []:
            geom = feat.get("geometry") or {}
            if "coordinates" in geom:
                geom["coordinates"] = _round_coords(geom["coordinates"], precision)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_payloads(
    weather_data_afternoon: list,
    weather_data_morning: list,
    lat: float,
    lon: float,
) -> list:
    """Build the wind + afternoon-UTCI + morning-UTCI submissions.

    Returns a list of ``(db_key_override, payload)`` pairs. ``db_key_override``
    is ``None`` for the wind + afternoon-UTCI cases (they use the payload's
    built-in analysis type) and ``"thermal-comfort-index-morning"`` for the
    morning UTCI so the demo DB can keep both UTCI rows under the same
    area without tripping the ``UNIQUE(area_name, analysis_type)`` index.
    """
    wind_payload = WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=WIND_SPEED,
        wind_direction=WIND_DIRECTION,
    )

    utci_afternoon = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(
            analysis_type=AnalysesName.thermal_comfort_index,
        ),
        location=Location(latitude=lat, longitude=lon),
        time_period=TIME_PERIOD,
        weather_data=weather_data_afternoon,
    )

    utci_morning = UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(
            analysis_type=AnalysesName.thermal_comfort_index,
        ),
        location=Location(latitude=lat, longitude=lon),
        time_period=MORNING_TIME_PERIOD,
        weather_data=weather_data_morning,
    )

    return [
        (None, wind_payload),
        (None, utci_afternoon),
        ("thermal-comfort-index-morning", utci_morning),
    ]


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
                preview = client.preview_area(polygon, max_tiles_override=120)
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
                    area_buildings = client.buildings.get_area(
                        polygon=polygon,
                        max_tiles_override=120,
                    )
                    logger.info(
                        "Area: %s — buildings fetched (%d, %.1fs)",
                        area_name,
                        area_buildings.total_buildings,
                        time.monotonic() - t_bldg,
                    )
                    _save_cached_buildings(area_name, polygon, area_buildings)

                # 3. Fetch weather data (two windows: 14:00 + 09:00).
                weather_locations = client.weather.get_weather_file_from_location(
                    lat=lat,
                    lon=lon,
                )
                weather_id = weather_locations[0]["uuid"]

                weather_data_afternoon = client.weather.filter_weather_data(
                    identifier=weather_id,
                    time_period=TIME_PERIOD,
                )
                weather_data_morning = client.weather.filter_weather_data(
                    identifier=weather_id,
                    time_period=MORNING_TIME_PERIOD,
                )
                logger.info(
                    "Area: %s — weather data ready (afternoon=%d, morning=%d points)",
                    area_name,
                    len(weather_data_afternoon),
                    len(weather_data_morning),
                )

                # 4. Fetch ground materials (reuse across both run_area calls).
                #
                # NOTE: vegetation is intentionally disabled for this run.
                # The utilities-service FGB column-name fix ships tomorrow;
                # until then, vegetation has known data-quality issues (see
                # sdk-gm-vegetation-extension). We pass vegetation={} to
                # run_area so nothing is auto-fetched or bundled per tile.
                area_vegetation = None

                area_ground_materials = _load_cached_ground_materials(
                    area_name, polygon
                )
                if area_ground_materials is not None:
                    logger.info(
                        "Area: %s — ground materials loaded from cache "
                        "(%d features, %d layers)",
                        area_name,
                        area_ground_materials.total_features,
                        len(area_ground_materials.layers),
                    )
                else:
                    try:
                        t_gm = time.monotonic()
                        area_ground_materials = client.ground_materials.get_area(
                            polygon,
                            max_tiles_override=120,
                        )
                        logger.info(
                            "Area: %s — ground materials fetched (%d features, "
                            "%d layers, %.1fs)",
                            area_name,
                            area_ground_materials.total_features,
                            len(area_ground_materials.layers),
                            time.monotonic() - t_gm,
                        )
                        _save_cached_ground_materials(
                            area_name, polygon, area_ground_materials
                        )
                    except Exception as exc:
                        logger.warning(
                            "Area: %s — ground materials fetch failed, "
                            "sending empty: %s",
                            area_name,
                            exc,
                        )
                        area_ground_materials = None

                if area_ground_materials is not None:
                    # Drop the Mapbox 'building' layer — redundant with the
                    # 3D building meshes already sent via `buildings=`, and it
                    # dominates payload size (~33 MB for Gracia).  The SDK
                    # pipeline does not reference this layer by name.  Applied
                    # after load/save so the cache always holds raw data.
                    dropped = area_ground_materials.layers.pop("building", None)
                    if dropped is not None:
                        logger.info(
                            "Area: %s — dropped 'building' layer from ground "
                            "materials (%d features) to reduce payload size",
                            area_name,
                            len((dropped or {}).get("features", [])),
                        )
                    # Round coordinate floats to 6 decimals (≈11 cm).  Mapbox
                    # returns ~14 digits which wastes bytes in every tile
                    # payload; rounding is lossless for ground-material
                    # assignment and typically shaves 30–40% off the JSON.
                    before_bytes = len(
                        json.dumps(area_ground_materials.layers).encode("utf-8")
                    )
                    _round_layers_coords(area_ground_materials.layers, precision=6)
                    after_bytes = len(
                        json.dumps(area_ground_materials.layers).encode("utf-8")
                    )
                    logger.info(
                        "Area: %s — rounded GM coords to 6 decimals: %s → %s "
                        "(%.1f%% smaller)",
                        area_name,
                        _human_size(before_bytes),
                        _human_size(after_bytes),
                        100 * (1 - after_bytes / before_bytes) if before_bytes else 0,
                    )

                # 5. Build payloads (list of (db_key_override, payload) pairs)
                submissions = _build_payloads(
                    weather_data_afternoon, weather_data_morning, lat, lon
                )

                # 6. Submit each payload individually and persist immediately
                vegetation_arg = (
                    area_vegetation.features if area_vegetation is not None else {}
                )
                ground_materials_arg = (
                    area_ground_materials.layers
                    if area_ground_materials is not None
                    else {}
                )
                for db_key_override, payload in submissions:
                    schedule = client.run_area(
                        payload,
                        polygon,
                        buildings=area_buildings.buildings,
                        vegetation=vegetation_arg,
                        ground_materials=ground_materials_arg,
                        webhook_url=WEBHOOK_URL,
                        webhook_events=WEBHOOK_EVENTS,
                        max_tiles_override=120,
                    )

                    # Persist to DB immediately after submission. The override
                    # keeps the morning UTCI distinct from the afternoon UTCI
                    # (both carry the same SDK analysis_type).
                    demo_db.save_schedule(
                        conn,
                        area_name,
                        schedule,
                        analysis_type_key=db_key_override,
                    )

                    effective_key = db_key_override or schedule.analysis_type
                    friendly = demo_db.FRIENDLY_NAMES.get(
                        effective_key,
                        effective_key,
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
