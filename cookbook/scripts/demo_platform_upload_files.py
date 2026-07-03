"""Generate a validated sample-data set for the Infrared PLATFORM file upload.

The platform (platform.infrared.city) accepts *files* when creating a project
("Bring your own data") and per-layer in the project's Data-layers panel:

    buildings  → GeoJSON FeatureCollection of Polygon/MultiPolygon footprints
    trees      → GeoJSON FeatureCollection of Point features (ONLY points)
    surfaces   → GeoJSON FC with `properties.material`, or a dict {name: FC}
    weather    → EnergyPlus .epw

This script is the portable REFERENCE IMPLEMENTATION of the file contract —
every rule the platform enforces is written out as a constant + comment so an
agent can port it to any language. Stdlib only (json / math / argparse).

Companion doc (the prose contract): the `use-infrared` skill reference
`references/platform-byo-upload.md`.

Usage:
    python demo_platform_upload_files.py                 # Vienna block, ./platform-upload-samples/
    python demo_platform_upload_files.py --center 9.99 53.55 --radius 220 --out ./samples

===============================================================================
THE CONTRACT (validated against the platform's own parsers, 2026-07-03)
===============================================================================

COORDINATES — applies to every GeoJSON file
  * CRS: EPSG:4326 (WGS84). GeoJSON axis order: [longitude, latitude].
  * Projected/metre coordinates (UTM etc.) are REJECTED (values outside
    lon ±180 / lat ±90). Lat/lon-swapped files are detected and rejected.
  * The combined extent of ALL files must span ≤ 2.0° in each axis and stay
    away from the poles; the site bounding box (expanded by +15% per side,
    min 0.001°) must be ≤ 4.0 km². Practical rule: keep everything within
    ~1.5 km of the site centre.

BUILDINGS (buildings.geojson)
  * FeatureCollection of Polygon / MultiPolygon. Point/LineString features are
    silently dropped; a file with no polygons is rejected.
  * Height in metres from `properties.height_m` (also accepted: `height`, `h`).
    Missing → default 9 m. Values are clamped to 3–200 m.
  * Optional `properties.kind`: "residential" | "office" | "tower" — display
    colour only, no simulation effect.
  * Features tagged `properties.material: "vegetation"` are dropped (they are
    surfaces, not buildings).
  * Caps: ≤ 20 MB, ≤ 50,000 features. Rings should be closed (first == last
    position); exterior ring first (holes = subsequent rings).

TREES (trees.geojson)
  * FeatureCollection of Point features ONLY — one Point per tree. Any
    non-Point feature rejects the whole file.
  * `properties.height` in metres, valid range 1–30.
    `properties.crownDiameter` in metres, valid range 1–20.
    If EITHER is missing/out-of-range, BOTH are replaced by the fallback
    (height 8, crownDiameter 5) to keep proportions — so always set both.
  * Trees outside the site boundary are dropped; max 500 trees kept.

GROUND SURFACES (surfaces.geojson)
  * Two accepted shapes:
      a) one FeatureCollection where every polygon has `properties.material`
      b) a dict {"asphalt": FC, "water": FC, ...} of per-material FCs
  * Canonical materials: water | concrete | asphalt | vegetation | soil.
    Common synonyms auto-map (grass/forest/park→vegetation, road/pavement/
    tarmac/parking→asphalt, sand/gravel/dirt→soil, lake/river/pond/sea→water,
    paving/building→concrete). Anything unresolved defaults to concrete —
    nothing is dropped, so tag every polygon explicitly.
  * Polygons only; ≤ 500 polygons; ≤ 20 MB. Clipped to the site boundary.

WEATHER (*.epw)
  * A real EPW is 8 header lines (line 1 = LOCATION with city, country, lat,
    lon, timezone, elevation; line 8 = DATA PERIODS) + 8,760 hourly rows of 35
    columns. The parser only requires: a LOCATION line, and >=1 data row (starts
    with an integer year) of >=22 columns with a usable dry-bulb value.
  * Dry-bulb temperature = column index 6 (0-based); 99.9 is the missing-value
    sentinel — a file whose dry-bulb column is all-missing is rejected.
  * For real projects use a measured/TMY file (e.g. climate.onebuilding.org);
    the synthetic file generated here is for pipeline testing only.

MULTI-FILE DROP (project creation) — content classification
  When several files are dropped at once, the platform classifies each by
  CONTENT, not filename:
    * .epw extension                          → weather
    * more Points than polygons               → trees
    * ≥ half the polygons material/surface-tagged, or the dict shape
                                              → surfaces
    * polygons otherwise                      → buildings
    * every ADDITIONAL buildings-like file    → a design-variant scenario
  One file per layer (extra buildings files become variants); at least one
  geometry file (buildings/trees/surfaces) is required to place the site.
  Every guess lands staged on its layer row and can be reassigned before
  "Create project".
===============================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

# --- contract constants (mirror the platform's validators) -------------------
BUILDING_HEIGHT_RANGE_M = (3.0, 200.0)  # clamped, not rejected
BUILDING_DEFAULT_HEIGHT_M = 9.0
TREE_HEIGHT_RANGE_M = (1.0, 30.0)  # out-of-range → fallback pair applied
TREE_CROWN_RANGE_M = (1.0, 20.0)
TREE_FALLBACK = {"height": 8.0, "crownDiameter": 5.0}
TREE_MAX_COUNT = 500
MATERIALS = ("water", "concrete", "asphalt", "vegetation", "soil")
MATERIAL_MAX_POLYGONS = 500
SITE_MAX_AREA_KM2 = 4.0  # bbox AFTER +15%/side expansion
SITE_MAX_SPAN_DEG = 2.0  # per axis, across ALL uploaded files
EPW_HOURS = 8760
EPW_MISSING_DRY_BULB = 99.9


def meters_to_deg(lat_deg: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Local equirectangular metres→degrees. Fine at site scale (<0.5% error
    under ~2 km); the platform derives its site box the same way. Port note:
    dlat = dy / 111_320 ; dlon = dx / (111_320 * cos(lat))."""
    dlat = dy_m / 111_320.0
    dlon = dx_m / (111_320.0 * math.cos(math.radians(lat_deg)))
    return dlon, dlat


def rect(lon: float, lat: float, w_m: float, h_m: float, props: dict) -> dict:
    """Axis-aligned closed rectangle (exterior ring, CCW, first==last)."""
    dlon, dlat = meters_to_deg(lat, w_m, h_m)
    ring = [
        [lon, lat],
        [lon + dlon, lat],
        [lon + dlon, lat + dlat],
        [lon, lat + dlat],
        [lon, lat],  # closed ring — required by RFC 7946, expected by parsers
    ]
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def make_buildings(lon0: float, lat0: float, radius_m: float, rng: random.Random) -> dict:
    """A block grid of extruded footprints. height_m drives the extrusion."""
    features = []
    step = radius_m / 3.5
    for ix in range(-3, 4):
        for iy in range(-3, 4):
            if rng.random() < 0.35:  # leave gaps — streets / courtyards
                continue
            dlon, dlat = meters_to_deg(lat0, ix * step, iy * step)
            h = rng.choice([6, 9, 12, 15, 18, 24, 32])
            kind = "tower" if h >= 24 else ("office" if h >= 15 else "residential")
            features.append(
                rect(
                    lon0 + dlon,
                    lat0 + dlat,
                    w_m=step * 0.55,
                    h_m=step * 0.55,
                    props={"height_m": h, "kind": kind},
                )
            )
    return fc(features)


def make_variant(buildings: dict, lat0: float, rng: random.Random) -> dict:
    """A design variant: same block, denser + taller (extra buildings file →
    the platform creates it as a variant scenario)."""
    features = []
    for f in buildings["features"]:
        g = json.loads(json.dumps(f))  # deep copy
        g["properties"]["height_m"] = min(
            BUILDING_HEIGHT_RANGE_M[1], g["properties"]["height_m"] * rng.uniform(1.3, 1.8)
        )
        features.append(g)
    return fc(features)


def make_trees(lon0: float, lat0: float, radius_m: float, rng: random.Random) -> dict:
    """Point-per-tree with BOTH height and crownDiameter set (in range)."""
    features = []
    for _ in range(60):
        ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(0, radius_m * 0.9)
        dlon, dlat = meters_to_deg(lat0, r * math.cos(ang), r * math.sin(ang))
        h = round(rng.uniform(4, 22), 1)  # within 1–30
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "height": h,
                    "crownDiameter": round(min(TREE_CROWN_RANGE_M[1], h * 0.6), 1),
                },
                "geometry": {"type": "Point", "coordinates": [lon0 + dlon, lat0 + dlat]},
            }
        )
    return fc(features)


def make_surfaces(lon0: float, lat0: float, radius_m: float) -> dict:
    """Single-FC shape: every polygon carries properties.material. Quadrants of
    asphalt / vegetation / concrete + a water strip + soil patch."""
    q = radius_m * 0.85
    dlon_q, dlat_q = meters_to_deg(lat0, q, q)
    features = [
        rect(lon0 - dlon_q, lat0 - dlat_q, q, q, {"material": "asphalt"}),
        rect(lon0, lat0 - dlat_q, q, q, {"material": "vegetation"}),
        rect(lon0 - dlon_q, lat0, q, q, {"material": "concrete"}),
        rect(lon0, lat0, q, q, {"material": "soil"}),
        rect(lon0 - dlon_q, lat0 + dlat_q * 0.98, 2 * q, q * 0.15, {"material": "water"}),
    ]
    return fc(features)


def make_epw(city: str, lat: float, lon: float, tz_hours: float, rng: random.Random) -> str:
    """Minimal-but-valid synthetic EPW: 8 headers + 8760 rows, 35 columns.
    Sinusoidal seasonal+diurnal dry-bulb, fixed RH/wind. Testing only."""
    header = [
        f"LOCATION,{city},-,SYN,Synthetic,000000,{lat:.2f},{lon:.2f},{tz_hours:.1f},200.0",
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        "COMMENTS 1,Synthetic file for platform-upload pipeline testing only",
        "COMMENTS 2,Generated by demo_platform_upload_files.py",
        "DATA PERIODS,1,1,Data,Sunday, 1/ 1,12/31",
    ]
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    rows: list[str] = []
    hour_of_year = 0
    for month, dim in enumerate(days_in_month, start=1):
        for day in range(1, dim + 1):
            for hour in range(1, 25):  # EPW hours are 1..24
                seasonal = -8.0 * math.cos(2 * math.pi * hour_of_year / EPW_HOURS)
                diurnal = 4.0 * math.sin(2 * math.pi * (hour - 8) / 24)
                dry_bulb = round(11.0 + seasonal + diurnal + rng.uniform(-0.5, 0.5), 1)
                ghi = max(0, int(400 * math.sin(math.pi * (hour - 6) / 12))) if 6 <= hour <= 18 else 0
                cols = ["0"] * 35
                cols[0] = "2019"  # any non-leap year
                cols[1] = str(month)
                cols[2] = str(day)
                cols[3] = str(hour)
                cols[4] = "0"  # minute
                cols[5] = "?9?9?9?9E0?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9"  # flags
                cols[6] = str(dry_bulb)  # dry-bulb °C — the field that MUST be usable
                cols[7] = str(round(dry_bulb - 3.0, 1))  # dew point
                cols[8] = "65"  # relative humidity %
                cols[9] = "101325"  # pressure Pa
                cols[13] = str(ghi)  # global horizontal irradiance Wh/m²
                cols[14] = str(int(ghi * 0.7))  # direct normal
                cols[15] = str(int(ghi * 0.3))  # diffuse horizontal
                cols[20] = "225"  # wind direction °
                cols[21] = "2.5"  # wind speed m/s
                rows.append(",".join(cols))
                hour_of_year += 1
    return "\n".join(header + rows) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--center", nargs=2, type=float, default=[16.37, 48.20], metavar=("LON", "LAT"))
    p.add_argument("--radius", type=float, default=200.0, help="site half-size in metres (keep ≤ ~700)")
    p.add_argument("--out", type=Path, default=Path("platform-upload-samples"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--city", default="Vienna")
    args = p.parse_args()

    lon0, lat0 = args.center
    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    buildings = make_buildings(lon0, lat0, args.radius, rng)
    files = {
        "buildings.geojson": buildings,
        "variant-b.geojson": make_variant(buildings, lat0, rng),
        "trees.geojson": make_trees(lon0, lat0, args.radius, rng),
        "surfaces.geojson": make_surfaces(lon0, lat0, args.radius),
    }
    for name, data in files.items():
        (args.out / name).write_text(json.dumps(data))
        print(f"wrote {args.out / name}  ({len(data['features'])} features)")

    epw_path = args.out / f"{args.city.lower()}-synthetic.epw"
    epw_path.write_text(make_epw(args.city, lat0, lon0, tz_hours=1.0, rng=rng))
    print(f"wrote {epw_path}  ({EPW_HOURS} rows)")
    print(
        "\nDrop ALL of these together on the platform's 'Bring your own data' card —\n"
        "each file is auto-classified onto its layer row (variant-b becomes a\n"
        "design-variant scenario). Or attach them one-by-one per row."
    )


if __name__ == "__main__":
    main()
