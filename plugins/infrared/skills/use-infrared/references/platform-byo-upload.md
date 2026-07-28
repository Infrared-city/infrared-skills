# Platform file upload — producing correct BYO data

The Infrared **platform** (platform.infrared.city) accepts *files* for a
project's data layers — at project creation ("Bring your own data", where each
layer row takes its own file and multi-file drops are auto-classified) and
afterwards in the project's Data-layers panel. This is the file contract.
It is distinct from the SDK's in-memory BYO path ([byo-inputs.md](byo-inputs.md)).

**Reference data** (validated sets, committed in this repo):
- `cookbook/sample-data/platform-upload/` — synthetic set (rectangles), the
  smallest possible thing that validates.
- `cookbook/sample-data/vienna-demo/` — **real** Vienna open data (OSM
  buildings/surfaces + Baumkataster trees + real EPWs) shaped into four visibly
  different, drag-and-drop scenarios. Use this one for demos.

## Coordinates — every GeoJSON file

- **CRS: EPSG:4326 (WGS84)**, GeoJSON axis order **[longitude, latitude]**.
  That is still the target — but the platform now *repairs* the common
  deviations instead of bouncing them (see [geospatial-crs.md](geospatial-crs.md)):

| Input | What happens |
|---|---|
| Projected coords + a `crs` member with a **supported** EPSG | **auto-reprojected** to WGS84, non-blocking notice |
| Projected coords + an **unsupported** EPSG | rejected, message names the code |
| Metre coords, **no** `crs` member | rejected **at project creation** (a local frame can't say *where* the project is) — but **accepted in an existing project's Data-layers panel**: auto-centred on the site, then you move/rotate it on the map |
| Lat/lon **swapped** | auto-corrected when unambiguous (\|lat\| > 90) or when the project centroid confirms it; otherwise rejected |

- Auto-reprojection covers WGS84/UTM (`EPSG:326xx` / `327xx`, zones 1–60),
  ETRS89/UTM (`25828`–`25838`), DHDN Gauss-Krüger (`31466`–`31469`), plus
  `27700` (British National Grid), `2154` (Lambert-93), `28992` (RD New),
  `3035` (ETRS89-LAEA) and `3857` (Web Mercator). The `crs` member is read in
  the OGC-URN, `EPSG:<code>`, `{type:'EPSG',properties:{code}}`, `CRS84` and
  bare-number forms.
- **Each file is gated on its OWN extent**: ≤ **2.0° per axis**, centroid off
  the poles (|lat| ≤ 85). A file that fails is dropped **and named** — the rest
  of the batch still creates the project.
- The site bounding box is the union of the surviving files, expanded +15% per
  side (min 0.001°). Total extent must be **≤ 10 km²**; above that the upload is
  rejected.
- **Extent > 6 km² is not an error.** All geometry is kept (buildings outside
  the analysis area still shade it), but the *analysis AOI* is centred and
  shrunk to ≤ 6 km² — and shrunk further for elongated shapes until it tiles
  under the platform's tile ceiling. Practical rule: keep what you want
  *analysed* within ~1.2 km of the site centre.
- The site boundary is **derived automatically** from the union bbox of the
  uploaded geometry — you do not upload a boundary.
- Uploading into an **existing** project additionally requires the file's bbox
  to overlap the site bbox (+15%, min 0.01°) — a file from another city is
  rejected rather than rendering an empty map.

## Buildings — `FeatureCollection` of footprints

| Rule | Value |
|---|---|
| Geometry | `Polygon` / `MultiPolygon` (others silently dropped; zero polygons ⇒ reject). MultiPolygons are split into one feature per part |
| Height property | `height_m`, metres — see the resolution order below |
| Missing height | defaults to **10 m** |
| Height clamp | **3–200 m** (clamped, not rejected) |
| Optional | `kind`: `residential` \| `office` \| `tower` (display colour only; defaults to `residential`) |
| Dropped | features with `material: "vegetation"` (those are surfaces) |
| Caps | ≤ 40 MB, ≤ 100,000 features (counted after MultiPolygon splitting) |
| Rings | closed (first == last), exterior ring first, holes after |
| All-degenerate file | rejected (no mesh could be extruded) |

**Height resolution** — the platform no longer needs a literal `height_m`; it
tries, in order, and takes the first hit (keys are case-insensitive, numeric
strings like `"7.7"` are accepted, and a present-but-zero/negative value is
skipped so a later synonym still wins):

1. **A direct height** (metres): `height_m` · `heightm` · `height` · `h` ·
   `building_height` · `buildingheight` · `bldg_height` · `building:height` ·
   `roof_height` · `roofheight` · `gebaeudehoehe` / `gebäudehöhe` · `hoehe` /
   `höhe` · `altura` · `hauteur`.
2. **A top − bottom elevation pair** — **both** must be present, so a lone
   above-sea-level value can't extrude a 340 m tower. Tops: `buildingtop` ·
   `buildingto` (ESRI 10-char truncation) · `z_max` / `zmax` · `maxheight` /
   `max_height` · `relh_max`. Bottoms: `buildingbottom` · `buildingbo` ·
   `ground_height` · `base_height` · `z_min` / `zmin` · `minheight` /
   `min_height` · `relh_min`.
3. **A floor count × 3.0 m**: `building:levels` · `building_levels` · `levels` ·
   `floors` · `num_floors` · `storeys` / `stories` · `geschosse` /
   `geschosszahl` / `geschossza` · `anzahl_geschosse` · `etagen`.

So a raw OSM export with `building:levels` and a QGIS/ArcGIS export with
truncated `BuildingTo`/`BuildingBo` both extrude correctly now — precomputing
`height_m` is no longer required, only the most explicit option.

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
| File size | ≤ **5 MB** — the trees parser is stricter than the 40 MB geometry cap |

`MultiPoint` counts as points when the drop is *classified*, but the trees
parser then rejects the file — emit one `Point` feature per tree.

## Ground surfaces — tagged polygons

Two accepted shapes:

1. One `FeatureCollection` whose polygons carry `properties.material`, or
2. a JSON dict of per-material FCs: `{"asphalt": FC, "water": FC, ...}`.

| Rule | Value |
|---|---|
| Canonical materials | `water` · `concrete` · `asphalt` · `vegetation` · `soil` |
| Synonyms (auto-mapped) | grass/forest/wood/shrub/scrub/tree(s)/park/green → vegetation · road/pavement/tarmac/parking → asphalt · sand/bare_ground/bare/ground/dirt/earth/gravel → soil · pond/lake/river/sea → water · paving/building → concrete |
| Unresolved names | mapped to **concrete** (kept, not dropped) — tag explicitly |
| Untagged features | also mapped to **concrete**, reported as `(unlabeled)` |
| Geometry | polygons only (non-polygons filtered out); clipped to the site; ≤ **40 MB** |
| Polygon cap | **500** in total across all materials, counted after MultiPolygon splitting — later materials are truncated first |

⚠️ **`properties.surface` only decides classification, not the material.** A file
tagged solely with `surface` is routed to the surfaces layer and then lands
entirely in `concrete`, because grouping reads `properties.material` only. Tag
with `material`.

For the dict shape, all member FCs must share one coordinate system — mixing
lon/lat layers with local-metre layers is rejected.

## Weather — EnergyPlus `.epw`

- A real TMY/AMY file is the full **8-line header** (line 1 = `LOCATION,<city>,
  <state>,<country>,<source>,<wmo>,<lat>,<lon>,<tz>,<elevation>`; line 8 =
  `DATA PERIODS,...`) then **8,760** hourly rows (non-leap year) of **35**
  columns — just download and use one.
- What the parser *actually enforces* (looser than a full EPW, so any real file
  passes): a `LOCATION` line must exist; a data row is any line starting with an
  integer year, and every such row must carry **≥ 22 columns** (through wind
  speed) or the whole file is rejected; the file needs **≥ 1** row with a usable
  dry-bulb value. Don't hand-truncate to fewer columns.
- Key columns (0-based): 1 month · 2 day · 3 hour (1–24) · **6 dry-bulb °C** ·
  8 RH % · 13 GHI Wh/m² · 20 wind dir ° · 21 wind speed m/s.
- `99.9` in the dry-bulb column = missing; a file with **no usable dry-bulb
  values is rejected**.
- Real projects: use a measured or TMY file (climate.onebuilding.org, the
  EnergyPlus weather archive). See [04-weather-data.md](04-weather-data.md).

## 3D models — `.obj`

A `.obj` in **local model coordinates** is accepted alongside GeoJSON; it needs
no georeferencing. Dropped on the create card it starts a *model-anchored*
project — you pick the location on the map and the site boundary is derived from
the model footprint. Dropped into an existing project it is auto-centred on the
site. One file can carry buildings, trees **and** ground surfaces at once.

- **Classification** is by `o`/`g` object name plus its `usemtl` names, matched
  case-insensitively on word boundaries: *build/building/bldg/haus/gebäude/
  house/massing/volume/tower/block* → buildings · *tree/baum/bäume/arbre/canopy/
  crown/bush/shrub/hedge* → trees · *ground/terrain/topo/surface/floor/road/
  street/straße/weg/path/asphalt/concrete/paving/pavement/sidewalk/plaza/platz/
  water/pond/lake/river/grass/lawn/soil/sand/gravel/site/context* → surfaces.
  *vegetation/veg/green/greenery/forest/wood* is ambiguous and resolved by
  flatness: z-extent < 0.5 m ⇒ surface, otherwise trees.
- **Unnamed objects** fall back to geometry: flat ⇒ surface; ≥ 3 connected
  components of which ≥ 70 % are tree-plausible (1.5–35 m tall, crown ≤ 25 m)
  ⇒ trees; otherwise buildings. Name your objects if you care about the split —
  you can also override each object's category in the confirm dialog.
- **Units** (m / dm / cm / mm / ft), up-axis, flip and drop-to-ground are
  auto-detected and confirmed by you in the Fix-geometry modal.
- Trees are simplified to canopy archetypes (round / conical / columnar), then
  go through the same 500-tree cap; surfaces go through the same material
  canonicalisation and 500-polygon cap as the GeoJSON path.
- Faces may be tris, quads or n-gons. Negative (relative) face indices are
  rejected; free-form curve elements are skipped with a warning.
- Several OBJs exported from the same model (buildings, then trees) align
  automatically when re-uploaded into the same scenario.

## Multi-file drop — content classification (project creation)

Files — or a whole dropped **folder** (recursed; `.geojson`/`.json`/`.epw`/`.obj`
only, ≤64 files, ≤4 levels deep) — are classified by **content**. The same drop
zone exists in the create card, the Data-layers panel (applies to the active
scenario), and the add-scenario form:

| Content | Layer |
|---|---|
| `.epw` extension | weather |
| `.obj` extension | 3D model (own import path, see above) |
| more Points than polygons | trees |
| ≥ half of the polygons material/surface-tagged, or the dict shape | surfaces |
| polygons otherwise | buildings |
| each ADDITIONAL buildings-like file | a design-variant scenario |

One file per layer (extra buildings files become variants); **at least one
geometry file** (buildings/trees/surfaces/OBJ) is required to place the site.
Every guess lands staged on its layer row and can be swapped before
*Create project*. Max **40 MB** per file.

Failure handling is per-file, not per-batch: a file that is unreadable (bad JSON
/ not a FeatureCollection), fails its layer's validation, or fails its own
placement gate is dropped **and named in a toast** while the rest of the drop
proceeds. Only a drop with nothing usable at all fails outright.

⚠️ One exception: a **second trees, surfaces or weather file in the same drop**
still aborts the whole drop with an error. Only buildings files may repeat (they
become variants). Upload the replacement separately from its layer row.

## Validation status

Both committed sample sets were run through the platform's actual upload parsers
(classification + per-layer deep validation + EPW parse) against `origin/staging`
on 2026-07-03 — all files accepted with **zero fallbacks, zero defaulted
materials, zero dropped features**. The real-data Vienna set additionally covers
building relations/courtyards, 500-tree density, and real Vienna + Madrid EPWs.
The rules above were re-verified against `forge-kit@origin/main` on 2026-07-28.

The Python generators that produced these sets (`demo_platform_upload_files.py`,
`demo_vienna_scenarios.py`, `demo_vienna_osm.py`) were removed from
`cookbook/scripts/` on 2026-07-22 by the automated cookbook sync — the committed
sample data under `cookbook/sample-data/` is unaffected and remains valid.
