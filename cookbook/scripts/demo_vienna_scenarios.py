"""Build a REAL-DATA demo/test set for the Infrared platform BYO file upload.

Unlike ``demo_platform_upload_files.py`` (synthetic rectangles — fine for the
validators, unconvincing on a map), this fetches real Vienna open data around
Karlsplatz / Resselpark and manipulates it into four visibly different
scenarios you can drag onto platform.infrared.city → "Bring your own data".

Data comes from the ``demo_vienna_osm`` sibling module (OSM/Overpass buildings +
surfaces, Stadt Wien Baumkataster trees, onebuilding.org EPWs). Every file is
shaped to the platform's upload parsers — see the ``use-infrared`` reference
``references/platform-byo-upload.md``. Stdlib only.

Output tree (each scenario folder is one drag-and-drop; caps: buildings ≤50k /
20 MB, trees ≤500, surfaces ≤500):

    vienna-demo/
      scenarios/{01-baseline,02-towers,03-green,04-redevelopment}/
        buildings.geojson  trees.geojson  surfaces.geojson
      create-with-variants/   # one drop → baseline + 2 building-variant scenarios
        buildings/trees/surfaces.geojson  variant-towers.geojson  variant-redevelopment.geojson
      weather/{vienna.epw,madrid.epw}     # real TMYx (skip with --no-epw)

Usage:
    python demo_vienna_scenarios.py                 # ./vienna-demo, fetch EPWs
    python demo_vienna_scenarios.py --no-epw --out ./out
    python demo_vienna_scenarios.py --bbox 48.1968 16.3685 48.2008 16.3745
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from demo_vienna_osm import (
    BUILDING_HEIGHT_RANGE_M,
    TREE_CROWN_RANGE_M,
    TREE_HEIGHT_RANGE_M,
    centroid,
    download_epws,
    fc,
    fetch_buildings,
    fetch_surfaces,
    fetch_trees,
    point_in_ring,
    ring_area,
)

# Extra species for the "green" scenario's new plantings (real Vienna street
# trees) — kept as a harmless `species` property, mirroring the cadastre data.
NEW_TREE_SPECIES = [
    ("Acer platanoides (Spitzahorn)", 16, 9),
    ("Platanus x acerifolia (Platane)", 22, 14),
    ("Quercus robur (Stieleiche)", 18, 12),
    ("Betula pendula (Hängebirke)", 12, 6),
    ("Prunus avium (Vogelkirsche)", 9, 5),
    ("Fraxinus excelsior (Esche)", 20, 11),
]
BBox = tuple[float, float, float, float]


def _outer_ring(feature: dict) -> list[list[float]]:
    g = feature["geometry"]
    return g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]


# --- scenario manipulations (deterministic) ----------------------------------
def make_towers(buildings: list[dict], count: int = 8) -> list[dict]:
    """Turn the `count` largest footprints into ×3 towers (clamped 200 m)."""
    ranked = sorted(
        range(len(buildings)),
        key=lambda i: ring_area(_outer_ring(buildings[i])),
        reverse=True,
    )
    out = json.loads(json.dumps(buildings))
    for i in ranked[:count]:
        h = min(BUILDING_HEIGHT_RANGE_M[1], out[i]["properties"]["height_m"] * 3)
        out[i]["properties"]["height_m"] = round(h, 1)
        out[i]["properties"]["kind"] = "tower"
    return out


def make_green(
    trees: list[dict],
    surfaces: list[dict],
    buildings: list[dict],
    bbox: BBox,
    rng: random.Random,
) -> tuple[list, list]:
    """Dense new planting (varied species/sizes) + every non-water surface → vegetation."""
    building_rings = [
        b["geometry"]["coordinates"][0]
        for b in buildings
        if b["geometry"]["type"] == "Polygon"
    ]
    s, w, n, e = bbox
    new_trees = json.loads(json.dumps(trees))
    # Keep the total under the platform's 500-tree cap so nothing gets truncated.
    cap_add = max(0, min(140, 500 - len(new_trees)))
    added = 0
    for _ in range(2000):
        if added >= cap_add:
            break
        lon, lat = round(rng.uniform(w, e), 6), round(rng.uniform(s, n), 6)
        if any(point_in_ring([lon, lat], r) for r in building_rings):
            continue
        species, base_h, base_c = rng.choice(NEW_TREE_SPECIES)
        new_trees.append(
            {
                "type": "Feature",
                "properties": {
                    "height": round(
                        min(TREE_HEIGHT_RANGE_M[1], base_h * rng.uniform(0.6, 1.15)), 1
                    ),
                    "crownDiameter": round(
                        min(TREE_CROWN_RANGE_M[1], base_c * rng.uniform(0.6, 1.15)), 1
                    ),
                    "species": species,
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
        added += 1
    green_surf = json.loads(json.dumps(surfaces))
    for f in green_surf:
        if f["properties"]["material"] != "water":
            f["properties"]["material"] = "vegetation"
    return new_trees, green_surf


def make_redevelopment(
    buildings: list[dict], surfaces: list[dict], bbox: BBox
) -> tuple[list, list]:
    """Clear the eastern third of the block; the cleared footprints become a park."""
    s, w, n, e = bbox
    clear_from = w + (e - w) * 0.62
    kept, removed = [], []
    for b in buildings:
        (removed if centroid(_outer_ring(b))[0] >= clear_from else kept).append(b)
    new_surf = json.loads(json.dumps(surfaces))
    for b in removed:
        g = b["geometry"]
        # Turn each cleared footprint into a vegetation surface; flatten
        # MultiPolygon parts so every surface stays a single Polygon.
        parts = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for rings in parts:
            new_surf.append(
                {
                    "type": "Feature",
                    "properties": {
                        "material": "vegetation",
                        "name": "Redevelopment park",
                    },
                    "geometry": {"type": "Polygon", "coordinates": rings},
                }
            )
    return kept, new_surf


# --- output ------------------------------------------------------------------
def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))


def write_dataset(
    out: Path, base: dict, towers_b: list, green: tuple, redev: tuple
) -> None:
    b, t, sfc = base["buildings"], base["trees"], base["surfaces"]
    scenarios = {
        "01-baseline": (b, t, sfc),
        "02-towers": (towers_b, t, sfc),
        "03-green": (b, green[0], green[1]),
        "04-redevelopment": (redev[0], t, redev[1]),
    }
    for name, (bf, tf, sf) in scenarios.items():
        _write(out / "scenarios" / name / "buildings.geojson", fc(bf))
        _write(out / "scenarios" / name / "trees.geojson", fc(tf))
        _write(out / "scenarios" / name / "surfaces.geojson", fc(sf))
    # One multi-file drop → baseline project + 2 building-variant scenarios.
    cwv = out / "create-with-variants"
    _write(cwv / "buildings.geojson", fc(b))
    _write(cwv / "trees.geojson", fc(t))
    _write(cwv / "surfaces.geojson", fc(sfc))
    _write(cwv / "variant-towers.geojson", fc(towers_b))
    _write(cwv / "variant-redevelopment.geojson", fc(redev[0]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=[48.1968, 16.3685, 48.2008, 16.3745],
        metavar=("S", "W", "N", "E"),
        help="Karlsplatz/Resselpark by default",
    )
    p.add_argument("--out", type=Path, default=Path("vienna-demo"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument(
        "--no-epw", action="store_true", help="skip the ~3 MB weather download"
    )
    args = p.parse_args()

    s, w, n, e = args.bbox
    bbox = f"{s},{w},{n},{e}"
    rng = random.Random(args.seed)

    print("Fetching buildings (OSM/Overpass)…")
    buildings = fetch_buildings(bbox)
    print(f"  {len(buildings)} buildings")
    print("Fetching trees (Wien Baumkataster)…")
    trees = fetch_trees(bbox)
    print(f"  {len(trees)} trees")
    print("Fetching surfaces (OSM/Overpass)…")
    surfaces = fetch_surfaces(bbox)
    print(f"  {len(surfaces)} surface polygons")

    base = {"buildings": buildings, "trees": trees, "surfaces": surfaces}
    towers_b = make_towers(buildings)
    green = make_green(trees, surfaces, buildings, (s, w, n, e), rng)
    redev = make_redevelopment(buildings, surfaces, (s, w, n, e))

    write_dataset(args.out, base, towers_b, green, redev)
    print(f"\nWrote scenarios + create-with-variants under {args.out}/")

    if not args.no_epw:
        print("Downloading real EPWs (Vienna + Madrid TMYx)…")
        for name in download_epws(args.out / "weather"):
            print(f"  weather/{name}")
    else:
        (args.out / "weather").mkdir(parents=True, exist_ok=True)

    print(
        "\nDemo drops:\n"
        "  • scenarios/01-baseline/  → drop the folder on 'Bring your own data'.\n"
        "  • create-with-variants/   → one drop = baseline + towers + redevelopment scenarios.\n"
        "  • weather/madrid.epw      → drop on a scenario's weather row: Madrid's climate in Vienna."
    )


if __name__ == "__main__":
    main()
