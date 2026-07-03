"""Real Vienna open-data fetch + normalization for the platform BYO demo set.

The data layer behind ``demo_vienna_scenarios.py``: fetch buildings + ground
surfaces from OpenStreetMap (Overpass, ODbL) and trees from the Stadt Wien
Baumkataster WFS (CC BY 4.0), and normalize each into GeoJSON shaped for the
platform's upload parsers (see the ``use-infrared`` reference
``references/platform-byo-upload.md``). Stdlib only.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

# --- platform contract constants (mirror the upload parsers) -----------------
BUILDING_HEIGHT_RANGE_M = (3.0, 200.0)  # extruder clamps to this
BUILDING_FALLBACK_HEIGHT_M = 12.0  # our default when OSM has no height/levels
LEVEL_HEIGHT_M = 3.0  # platform convention: building:levels * 3
TREE_HEIGHT_RANGE_M = (1.0, 30.0)
TREE_CROWN_RANGE_M = (1.0, 20.0)
TREE_FALLBACK = {"height": 8.0, "crownDiameter": 5.0}

USER_AGENT = "infrared-skills-demo/1.0 (github.com/Infrared-city/infrared-skills)"
OVERPASS = "https://overpass-api.de/api/interpreter"
WIEN_WFS = "https://data.wien.gv.at/daten/geo"
EPW_URLS = {
    "vienna.epw": "https://climate.onebuilding.org/WMO_Region_6_Europe/AUT_Austria/"
    "NO_Lower_Austria/AUT_NO_Wien-Schwechat.AP.110360_TMYx.zip",
    "madrid.epw": "https://climate.onebuilding.org/WMO_Region_6_Europe/ESP_Spain/"
    "MD_Madrid/ESP_MD_Madrid-Barajas-Suarez.AP.082210_TMYx.zip",
}
SURFACE_MATERIAL = {
    "park": "vegetation",
    "garden": "vegetation",
    "grass": "vegetation",
    "water": "water",
    "pedestrian": "concrete",
}

Ring = list[list[float]]


# --- HTTP --------------------------------------------------------------------
def http_get(url: str, retries: int = 4) -> bytes:
    """GET with our User-Agent (Overpass 406s without one) + backoff on 5xx."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:  # 504/429 from a busy Overpass
            last = e
            if e.code not in (429, 502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url}\n  {last}")


def overpass(query: str) -> dict:
    return json.loads(http_get(f"{OVERPASS}?{urllib.parse.urlencode({'data': query})}"))


# --- geometry helpers --------------------------------------------------------
def pt(node: dict) -> list[float]:
    return [round(node["lon"], 6), round(node["lat"], 6)]  # GeoJSON [lon, lat]


def close_ring(ring: Ring) -> Ring:
    return ring if ring and ring[0] == ring[-1] else [*ring, ring[0]]


def ring_area(ring: Ring) -> float:
    """Shoelace |area| in deg² — only used to rank footprints by size."""
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) / 2


def centroid(ring: Ring) -> list[float]:
    xs = [p[0] for p in ring[:-1]]
    ys = [p[1] for p in ring[:-1]]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def point_in_ring(point: list[float], ring: Ring) -> bool:
    x, y = point
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def stitch(segments: list[Ring]) -> list[Ring]:
    """Assemble (possibly split) relation member ways into closed rings by
    endpoint matching. Already-closed members pass straight through."""
    rings: list[Ring] = []
    remaining = [list(s) for s in segments if len(s) >= 2]
    remaining = [s for s in remaining if not (s[0] == s[-1] and rings.append(s))]
    while remaining:
        cur = remaining.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(remaining):
                if cur[-1] == s[0]:
                    cur += s[1:]
                elif cur[-1] == s[-1]:
                    cur += s[-2::-1]
                elif cur[0] == s[-1]:
                    cur = s[:-1] + cur
                elif cur[0] == s[0]:
                    cur = s[:0:-1] + cur
                else:
                    continue
                remaining.pop(i)
                changed = True
                break
        rings.append(close_ring(cur))
    return [r for r in rings if len(r) >= 4]


# --- buildings ---------------------------------------------------------------
def _height_from_tags(tags: dict) -> float:
    for key, scale in (("height", 1.0), ("building:levels", LEVEL_HEIGHT_M)):
        raw = tags.get(key)
        if raw is None:
            continue
        m = re.match(r"[-+]?\d*\.?\d+", str(raw).replace(",", "."))
        if m:
            lo, hi = BUILDING_HEIGHT_RANGE_M
            return round(min(hi, max(lo, float(m.group()) * scale)), 1)
    return BUILDING_FALLBACK_HEIGHT_M


def _kind_for(height: float) -> str:
    return "tower" if height >= 40 else "office" if height >= 20 else "residential"


def _building_feature(geom: dict, tags: dict) -> dict:
    height = _height_from_tags(tags)
    props = {"height_m": height, "kind": _kind_for(height)}
    if tags.get("name"):
        props["name"] = tags["name"]
    return {"type": "Feature", "properties": props, "geometry": geom}


def _relation_geometry(members: list[dict]) -> dict | None:
    outers = stitch(
        [
            [pt(nd) for nd in m["geometry"]]
            for m in members
            if m.get("role") == "outer" and m.get("geometry")
        ]
    )
    inners = stitch(
        [
            [pt(nd) for nd in m["geometry"]]
            for m in members
            if m.get("role") == "inner" and m.get("geometry")
        ]
    )
    polys = []
    for outer in outers:
        holes = [h for h in inners if point_in_ring(centroid(h), outer)]
        polys.append([outer, *holes])
    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def fetch_buildings(bbox: str) -> list[dict]:
    data = overpass(
        f"[out:json][timeout:60];"
        f"(way[building]({bbox});relation[building]({bbox}););out geom;"
    )
    feats: list[dict] = []
    for el in data["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "way" and el.get("geometry"):
            ring = close_ring([pt(nd) for nd in el["geometry"]])
            if len(ring) >= 4:
                feats.append(
                    _building_feature({"type": "Polygon", "coordinates": [ring]}, tags)
                )
        elif el["type"] == "relation" and tags.get("type") == "multipolygon":
            geom = _relation_geometry(el.get("members", []))
            if geom:
                feats.append(_building_feature(geom, tags))
    return feats


# --- trees -------------------------------------------------------------------
def _range_mid(txt: str | None, lo: float, hi: float) -> float | None:
    """Midpoint of a '11-15 m' category string, clamped to the platform range.
    Returns None for 'nicht bekannt' / no digits, so the caller applies the pair
    fallback (the cadastre stores height/crown as ranges, not exact metres)."""
    nums = [int(x) for x in re.findall(r"\d+", txt or "")]
    if not nums:
        return None
    return round(min(hi, max(lo, sum(nums) / len(nums))), 1)


def fetch_trees(bbox_wfs: str) -> list[dict]:
    url = (
        f"{WIEN_WFS}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeName=ogdwien:BAUMKATOGD&srsName=EPSG:4326"
        f"&bbox={bbox_wfs},urn:ogc:def:crs:EPSG::4326&outputFormat=json"
    )
    data = json.loads(http_get(url))
    feats: list[dict] = []
    for f in data["features"]:
        p = f["properties"]
        h = _range_mid(p.get("BAUMHOEHE_TXT"), *TREE_HEIGHT_RANGE_M)
        c = _range_mid(p.get("KRONENDURCHMESSER_TXT"), *TREE_CROWN_RANGE_M)
        # Platform replaces BOTH if either is out of range — pre-apply the pair
        # ourselves so unknown-dimension trees stay valid, not silently defaulted.
        if h is None or c is None:
            h, c = TREE_FALLBACK["height"], TREE_FALLBACK["crownDiameter"]
        lon, lat = f["geometry"]["coordinates"]
        props = {"height": h, "crownDiameter": c}
        if p.get("GATTUNG_ART"):
            props["species"] = p["GATTUNG_ART"]
        if p.get("PFLANZJAHR"):
            props["plantYear"] = p["PFLANZJAHR"]
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 6), round(lat, 6)],
                },
            }
        )
    return feats


# --- surfaces ----------------------------------------------------------------
def fetch_surfaces(bbox: str) -> list[dict]:
    data = overpass(
        f"[out:json][timeout:60];"
        f"(way[leisure=park]({bbox});way[leisure=garden]({bbox});"
        f"way[landuse=grass]({bbox});way[natural=water]({bbox});"
        f"way[highway=pedestrian]({bbox}););out geom;"
    )
    feats: list[dict] = []
    for el in data["elements"]:
        geom = el.get("geometry")
        if not geom or len(geom) < 3:
            continue
        tags = el.get("tags", {})
        key = (
            tags.get("leisure")
            or tags.get("landuse")
            or tags.get("natural")
            or tags.get("highway")
        )
        material = SURFACE_MATERIAL.get(key)
        if not material:
            continue
        props = {"material": material}
        if tags.get("name"):
            props["name"] = tags["name"]
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [close_ring([pt(nd) for nd in geom])],
                },
            }
        )
    return feats


# --- weather + output helpers ------------------------------------------------
def fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def download_epws(dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, url in EPW_URLS.items():
        with zipfile.ZipFile(BytesIO(http_get(url))) as zf:
            epw = next(n for n in zf.namelist() if n.lower().endswith(".epw"))
            (dest / name).write_bytes(zf.read(epw))
            written.append(name)
    return written
