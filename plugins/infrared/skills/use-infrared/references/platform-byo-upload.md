# Platform file upload — producing correct BYO data

The Infrared **platform** (platform.infrared.city) accepts *files* for a
project's data layers — at project creation ("Bring your own data", where each
layer row takes its own file and multi-file drops are auto-classified) and
afterwards in the project's Data-layers panel. This is the file contract.
It is distinct from the SDK's in-memory BYO path ([byo-inputs.md](byo-inputs.md)).

**Reference implementations** (rules as runnable code, stdlib Python):
- `cookbook/scripts/demo_platform_upload_files.py` — synthetic set (rectangles),
  smallest possible thing that validates. Committed: `cookbook/sample-data/platform-upload/`.
- `cookbook/scripts/demo_vienna_scenarios.py` (+ `demo_vienna_osm.py`) — **real**
  Vienna open data (OSM buildings/surfaces + Baumkataster trees + real EPWs) shaped
  into four visibly different, drag-and-drop scenarios. Committed:
  `cookbook/sample-data/vienna-demo/`. Use this one for demos.

## Coordinates — every GeoJSON file

- **CRS: EPSG:4326 (WGS84)**, GeoJSON axis order **[longitude, latitude]**.
- Projected/metre coordinates (UTM, national grids) are **rejected** — values
  outside lon ±180 / lat ±90. Lat/lon-swapped files are detected and rejected.
  Reproject BEFORE exporting (see [geospatial-crs.md](geospatial-crs.md)).
- The combined extent of ALL files must span **≤ 2.0° per axis**, stay off the
  poles, and the site bounding box (auto-expanded +15% per side, min 0.001°)
  must be **≤ 4.0 km²**. Practical rule: keep everything within ~1.5 km of the
  site centre.
- The site boundary is **derived automatically** from the union bbox of the
  uploaded geometry — you do not upload a boundary.

## Buildings — `FeatureCollection` of footprints

| Rule | Value |
|---|---|
| Geometry | `Polygon` / `MultiPolygon` (others silently dropped; zero polygons ⇒ reject) |
| Height property | `height_m` (also read: `height`, `h`), metres |
| Missing height | defaults to **9 m** — `building:levels` is **not** read on upload, so precompute `height_m` yourself (e.g. `levels × 3`) before export |
| Height clamp | **3–200 m** (clamped, not rejected) |
| Optional | `kind`: `residential` \| `office` \| `tower` (display colour only) |
| Dropped | features with `material: "vegetation"` (those are surfaces) |
| Caps | ≤ 20 MB, ≤ 50,000 features |
| Rings | closed (first == last), exterior ring first, holes after |

Footprints are extruded to 3D on upload — one mesh per polygon — and the
uploaded buildings are what simulations run against.

## Trees — `FeatureCollection` of `Point`s ONLY

| Rule | Value |
|---|---|
| Geometry | `Point`, one per tree. **Any non-Point feature rejects the file** |
| `properties.height` | metres, valid **1–30** |
| `properties.crownDiameter` | metres, valid **1–20** |
| Either missing/out-of-range | **BOTH** replaced by fallback (8 m / 5 m) — always set both |
| Clipping | points outside the site are dropped |
| Cap | **500 trees** kept (post-clip) |
| File size | ≤ **5 MB** — the trees parser is stricter than the 20 MB geometry cap |

## Ground surfaces — tagged polygons

Two accepted shapes:

1. One `FeatureCollection` where every polygon has `properties.material`
   (also read: `properties.surface`), or
2. a JSON dict of per-material FCs: `{"asphalt": FC, "water": FC, ...}`.

| Rule | Value |
|---|---|
| Canonical materials | `water` · `concrete` · `asphalt` · `vegetation` · `soil` |
| Synonyms (auto-mapped) | grass/forest/wood/shrub/scrub/tree(s)/park/green → vegetation · road/pavement/tarmac/parking → asphalt · sand/bare_ground/bare/ground/dirt/earth/gravel → soil · pond/lake/river/sea → water · paving/building → concrete |
| Unresolved names | mapped to **concrete** (kept, not dropped) — tag explicitly |
| Geometry | polygons only; ≤ **500** polygons; ≤ **20 MB**; clipped to the site |

## Weather — EnergyPlus `.epw`

- A real TMY/AMY file is the full **8-line header** (line 1 = `LOCATION,<city>,
  <state>,<country>,<source>,<wmo>,<lat>,<lon>,<tz>,<elevation>`; line 8 =
  `DATA PERIODS,...`) then **8,760** hourly rows (non-leap year) of **35**
  columns — just download and use one.
- What the parser *actually enforces* (looser than a full EPW, so any real file
  passes): a `LOCATION` line must exist; a data row is any line starting with an
  integer year and carrying **≥ 22 columns** (through wind speed); the file needs
  **≥ 1** such row with a usable dry-bulb value. Don't hand-truncate to fewer.
- Key columns (0-based): 1 month · 2 day · 3 hour (1–24) · **6 dry-bulb °C** ·
  8 RH % · 13 GHI Wh/m² · 20 wind dir ° · 21 wind speed m/s.
- `99.9` in the dry-bulb column = missing; a file with **no usable dry-bulb
  values is rejected**.
- Real projects: use a measured or TMY file (climate.onebuilding.org, the
  EnergyPlus weather archive). See [04-weather-data.md](04-weather-data.md).

## Multi-file drop — content classification (project creation)

Files — or a whole dropped **folder** (recursed; `.geojson`/`.json`/`.epw` only, ≤64 files) — are classified by **content**. The same drop zone exists in the create card, the Data-layers panel (applies to the active scenario), and the add-scenario form:

| Content | Layer |
|---|---|
| `.epw` extension | weather |
| more Points than polygons | trees |
| ≥ half of the polygons material/surface-tagged, or the dict shape | surfaces |
| polygons otherwise | buildings |
| each ADDITIONAL buildings-like file | a design-variant scenario |

One file per layer (extra buildings files become variants); **at least one
geometry file** (buildings/trees/surfaces) is required to place the site. Every
guess lands staged on its layer row and can be swapped before *Create project*.

## Validation status

Both committed sample sets were run through the platform's actual upload parsers
(classification + per-layer deep validation + EPW parse) against `origin/staging`
on 2026-07-03 — all files accepted with **zero fallbacks, zero defaulted
materials, zero dropped features**. The real-data Vienna set additionally covers
building relations/courtyards, 500-tree density, and real Vienna + Madrid EPWs.
Regenerate for any location:

```bash
# synthetic (fast, offline)
python cookbook/scripts/demo_platform_upload_files.py --center <lon> <lat> --radius 200
# real data (fetches OSM + Wien Baumkataster + EPWs)
python cookbook/scripts/demo_vienna_scenarios.py --bbox <S> <W> <N> <E>
```
