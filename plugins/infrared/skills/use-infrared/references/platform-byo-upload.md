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

## Layers and accepted formats

A project scenario has exactly **four** uploadable layers. There is no terrain
layer, no separate context layer, and no site-boundary upload — the boundary is
derived (see *Coordinates*), and terrain is not user-supplied at all.

| Layer | What it is | Upload formats |
|---|---|---|
| `buildings` | Footprints, extruded to 3D on upload | `.geojson` / `.json` · `.obj` |
| `trees` | Tree points → canopy meshes | `.geojson` / `.json` · `.obj` |
| `materials` | Ground-surface classification polygons | `.geojson` / `.json` · `.obj` |
| `weather` | Hourly climate file | `.epw` |

**Which extensions actually work depends on where you drop them** — this trips
people up, so check the entry point before blaming the file:

| Entry point | Accepts |
|---|---|
| Multi-file drop zone (creation card, Data-layers panel, add-scenario form) | `.geojson` `.json` `.epw` **`.obj`** |
| Data-layers panel — a layer row's Upload button | `.geojson` `.json` **`.obj`** |
| Data-layers panel — the Weather row | `.epw` |
| **Create-project card — a layer row's Upload button** | `.geojson` `.json` only — **`.obj` is NOT accepted here**; use the drop zone |
| Create-project card — the Weather row | `.epw` |

`.ifc` is declared in the format registry but its adapter is a **disabled stub**
— rejected today. Do not offer it. GLB was dropped and is not coming back.
Anything else — `.bim` (DotBim), `.shp`, `.dxf`, `.gltf`, `.csv`, `.kml` — has no
adapter at all and fails as `Unsupported file type`; convert to GeoJSON first.

> `.bim` is **not** a declared-but-disabled format: `format-adapters/index.ts`
> registers only GeoJSON (enabled) plus tree/surface/IFC stubs. That file's own
> header comment claims "GeoJSON, Shapefile, and .bim (DotBim)" and contradicts
> its adapter list — a stale comment in the platform, not a format that exists.
> (`DotBimMesh` in that codebase is an internal in-memory mesh type, unrelated to
> a `.bim` upload.) Outcome for a user is the same — rejected — but don't
> describe it as disabled-but-declared.

An `.obj` dropped on **any** geometry layer row is routed to the shared
multi-kind OBJ importer, not to that row's layer — so dropping a model on the
trees row can still import buildings and surfaces from it.

## How the upload happens

**Two entry paths.** Both end in the same parsers, so the file contract is
identical; what differs is whether a site already exists.

**A. At project creation — "Bring your own data".**
1. Drop your files (or a folder) on the creation card's drop zone, or attach
   them one at a time to the per-layer rows.
2. Each file is classified by **content** onto a layer and lands *staged* on
   that layer's row, showing its filename. Re-assign or replace anything the
   guess got wrong before continuing.
3. The site boundary + centroid are derived from the union of the accepted
   geometry, so **at least one geometry file is required** — an `.epw`-only drop
   cannot create a project.
4. *Create project* commits the staged files. A metric/no-CRS file cannot be
   used here (nothing tells the platform where the project is) — create the
   project from a geo-referenced file or a picked location first.
5. An `.obj` takes a different route: it starts a *model-anchored* project where
   you pick the location on the map and the boundary comes from the model
   footprint.

**B. After creation — the Data-layers panel.** Uploads apply to the **active
scenario**. Use a layer row's Upload button to set/replace one layer, or the
panel's drop zone for several at once. This is the only path that accepts
local-coordinate files: they are auto-centred on the site and you position them
with the on-map placement gimbal, after which the layer stays movable ("Adjust").
Removing an uploaded layer reverts that row to the SDK fetch source.

Uploading never triggers an SDK fetch, and uploaded layers are what the
simulations actually run against.

**You do not have to upload all four layers.** There are four independent layer
kinds — buildings, trees, ground surfaces, weather — and each defaults to the SDK
fetch source (`input-source-registry.ts`: every kind is `default: 'sdk'`,
`defaultBundle: true`). A layer you never upload behaves exactly like one you
uploaded and then removed: it is fetched. So uploading only buildings and trees
is a normal, fully runnable project — the ground map and weather come from the
fetch path, and the scenario runs. Upload only what you actually want to override.

## Where files go on disk

There is **no manifest and no required filename** — every GeoJSON is classified
by its *content*, so `export_3.geojson` works as well as `buildings.geojson`.
Names are still worth setting: they are what the staged rows and every error
toast show you, and post-creation they become the variant scenario's name.

A complete single-scenario set is four files in one flat folder:

```
my-site/
  buildings.geojson    FeatureCollection of Polygon/MultiPolygon footprints
  trees.geojson        FeatureCollection of Points
  surfaces.geojson     FeatureCollection of Polygons tagged properties.material
  weather.epw          EnergyPlus weather file
```

- **One file per layer.** Do not split buildings across two files in one drop —
  the second polygon file becomes a *design-variant scenario*, not more
  buildings. Merge them into one FeatureCollection first.
- Extra buildings files are the *only* intentional way to create variants:
  ```
  my-site/
    buildings.geojson    → baseline scenario
    proposal-a.geojson   → a variant scenario
    proposal-b.geojson   → a variant scenario
    trees.geojson  surfaces.geojson  weather.epw
  ```
  **The variant's name depends on where you drop it:** at project creation the
  filename is ignored and variants are named `Variant A`, `Variant B`, … in drop
  order; dropped on the Data-layers panel afterwards, the variant takes the
  filename without its extension. Only the baseline scenario gets the trees /
  surfaces / weather from the same drop — variants carry buildings only.
- Sub-folders are fine (a dropped folder is recursed 4 levels, 64 files max),
  but organise by *scenario*, not by layer — a folder per layer buys nothing
  since classification ignores paths.
- Files starting with `.` are skipped; so is anything that is not
  `.geojson` / `.json` / `.epw` / `.obj`.

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

> **Every key in the table below is read from the feature's `properties` object** —
> `height_m`, `kind` and all the height synonyms live under `properties`, never at
> the Feature's top level. Same as Trees and Surfaces, which spell it out as
> `properties.height` / `properties.material`.
>
> ```json
> { "type": "Feature",
>   "properties": { "height_m": 24, "kind": "office" },
>   "geometry": { "type": "Polygon", "coordinates": [[[16.371,48.208],[16.372,48.208],[16.372,48.209],[16.371,48.209],[16.371,48.208]]] } }
> ```

| Rule | Value |
|---|---|
| Geometry | `Polygon` / `MultiPolygon` (others silently dropped; zero polygons ⇒ reject). MultiPolygons are split into one feature per part |
| Height property | `height_m`, metres — see the resolution order below |
| Missing height | defaults to **10 m** |
| Height clamp | **3–200 m** (clamped, not rejected) |
| Optional | `kind`: `residential` \| `office` \| `tower` (display colour only; defaults to `residential`). **Case-sensitive and unvalidated** — any string passes through as-is, so `"Residential"` is stored verbatim and simply won't match a known colour. Lowercase exactly (`geojson-adapter.ts:203`) |
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

## Multi-file drop — content classification

Files — or a whole dropped **folder** (recursed; `.geojson`/`.json`/`.epw`/`.obj`
only, ≤64 files, ≤4 levels deep) — are classified by **content**, never by
filename or path. The same drop zone and the same classifier serve the create
card, the Data-layers panel (applies to the active scenario), and the
add-scenario form — including the "extra buildings file ⇒ variant scenario"
rule, which fires in all three:

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
*Create project*. Per-file size caps are **per layer**, not a flat 40 MB:
buildings and surfaces **40 MB**, trees **5 MB**. A 10 MB trees file is rejected
by the tree parser even though it is well under the geometry cap — see the
per-layer caps above.

Failure handling is per-file, not per-batch: a file that is unreadable (bad JSON
/ not a FeatureCollection), fails its layer's validation, or fails its own
placement gate is dropped **and named in a toast** while the rest of the drop
proceeds. Only a drop with nothing usable at all fails outright.

⚠️ One exception: a **second trees, surfaces or weather file in the same drop**
still aborts the whole drop with an error. Only buildings files may repeat (they
become variants). Upload the replacement separately from its layer row.

In a mixed GeoJSON + OBJ drop the GeoJSON layers are written first and each kind
is **claimed by its first successful writer** — an OBJ bucket for a kind a
GeoJSON file already filled is skipped with a note. Put a kind in one source or
the other, not both.

## Failure modes — the error you'll see and what causes it

Rejections are per-file and the message names the file. Everything in the first
group **rejects the file**; everything in the second is a **silent correction**
you only notice in the result.

### Hard rejects

| Error | Cause | Fix |
|---|---|---|
| `File too large — max 40 MB.` | Buildings/surfaces file over the cap | Simplify or split |
| `File is too large (… MB). Maximum allowed size is 5 MB.` | Trees file over the **5 MB** tree-specific cap | Thin the point set |
| `Too many features (…). Max 100,000` | Buildings file over the feature cap | Split or simplify |
| `File is not valid JSON.` / `Invalid JSON.` | Truncated or non-JSON file | Re-export |
| `Expected a GeoJSON FeatureCollection.` / `The file has no features.` | Bare geometry, bare Feature, or an empty FC | Wrap in a FeatureCollection with ≥ 1 feature |
| `No building polygons found in this file.` | A trees/surfaces file sent to the buildings row | Use the drop zone or the right row |
| `Tree imports must contain only Point features. Found '<type>'.` | Any non-`Point` in a trees file (incl. `MultiPoint`) | One `Point` per tree |
| `Coordinates use EPSG:<n>, an unsupported projected CRS.` | Declared CRS outside the supported set | Re-export as EPSG:4326 |
| `This file's coordinates aren't longitude/latitude …` | Projected metres, no `crs`, no safe swap — **at project creation** | Create from a geo-referenced file/location, then upload via Data layers |
| `This file appears mislocated for this project — … lat/lon order …` | Swapped axes confirmed against the project centroid | Re-export as `[lon, lat]` |
| `This geometry looks mislocated (implausibly large span or near a pole).` | File spans > 2°/axis or sits near a pole | Crop; check the CRS |
| `Uploaded geometry spans … km² — exceeds the 10 km² upload cap.` | Union extent too large | Crop or split into projects |
| `This geometry doesn't overlap your site …` | File belongs to a different site | Start a new project from it |
| `No valid building footprints found — every polygon was empty or degenerate.` | Zero-area / malformed rings | Fix ring geometry |
| `No trees could be imported …` / `No polygons fell inside the site boundary.` | Everything clipped away | Check it overlaps the site |
| `This surfaces file mixes lon/lat layers with local-coordinate layers` | Dict form with inconsistent CRS across members | One coordinate system for all members |
| `only one .epw weather file per project.` | Two `.epw`s in one drop | Drop one |
| `you already added a <kind> file — replace it from the <kind> row instead.` | A 2nd trees/surfaces file in one drop — **aborts the whole drop** | Upload it separately |
| `Not a valid .epw weather file — …` / `no usable weather readings.` | Missing `LOCATION`, a data row under 22 columns, or all dry-bulb values missing | Use an unmodified TMY/AMY file |
| `No plausible unit found …` | OBJ whose extent is implausible at every unit | Check the export scale |
| format `not enabled yet` | `.ifc` — registered but a disabled stub | Convert to GeoJSON |
| `Unsupported file type.` | `.bim`, `.shp`, `.dxf`, `.gltf`, `.csv`, `.kml` — no adapter at all | Convert to GeoJSON |

### Silent corrections — no error, wrong-looking result

| Symptom | Cause |
|---|---|
| Buildings all the same height | No recognised height property ⇒ everyone gets the 10 m default |
| One building far too short/tall | Value clamped into 3–200 m |
| A building is missing | Non-polygon geometry, or `material: "vegetation"` — both dropped |
| Trees all identical (8 m / 5 m crown) | `height`/`crownDiameter` missing or out of range ⇒ **both** replaced |
| Fewer trees than expected | Clipped to the site, then capped at 500 |
| Every surface came in as `concrete` | Tagged with `properties.surface` instead of `properties.material`, or unrecognised names |
| Surfaces missing | Aggregate 500-polygon cap — later materials truncated first |
| Analysis covers less than you uploaded | Extent > 6 km² ⇒ AOI centred and shrunk; geometry kept as context |
| Geometry landed centred on the site, not where you meant | Metric no-CRS file auto-placed — use *Adjust* to position it |

## Validation status

Both committed sample sets were run through the platform's actual upload parsers
(classification + per-layer deep validation + EPW parse) against `origin/staging`
on 2026-07-03 — all files accepted with **zero fallbacks, zero defaulted
materials, zero dropped features**. The real-data Vienna set additionally covers
building relations/courtyards, 500-tree density, and real Vienna + Madrid EPWs.
The rules above were re-verified against `forge-kit@origin/main` on 2026-07-28.
