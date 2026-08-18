# Platform file upload — how to export a file the platform accepts

<!-- Verified against forge-kit@origin/main fc69c214 (2026-08-18) and
     infrared-core@origin/main c049f50 (2026-08-17). -->

The Infrared **platform** (platform.infrared.city) reads files for the geometry
and the weather of a project. This page is the file contract. Use it to make an
export from Rhino, Grasshopper, QGIS, ArcGIS, Blender, or SketchUp that the
platform accepts at the first try.

This page is about FILES in the platform. It is not about the SDK. For
in-memory payloads in your own Python, read
[byo-inputs.md](byo-inputs.md). The two contracts are different.

To read data OUT of the platform, read [platform-export.md](platform-export.md).

**Reference data** (validated sets, in this repository):

- `cookbook/sample-data/platform-upload/` — a synthetic set of rectangles. It
  is the smallest set that passes validation.
- `cookbook/sample-data/vienna-demo/` — real Vienna open data (OSM buildings
  and surfaces, Baumkataster trees, real EPW files). Use this set for a demo.

---

## 1. Checklist before you export

Do these ten things. Then the upload works.

| # | Do this | Why |
|---|---|---|
| 1 | Export GeoJSON in **EPSG:4326 (WGS84)**, axis order `[longitude, latitude]`. | This is the only geographic frame the platform reads. A projected file with a `crs` member is reprojected. A projected file with no `crs` member is put on your site and you must then move it. |
| 2 | Export OBJ in **metres**. | OBJ has no unit field. The platform guesses the unit. A guess can be wrong. See §8. |
| 3 | Give every OBJ object a name that contains `building`, `tree`, or `ground`. | The name is the first and the strongest classification rule. See §8. |
| 4 | Put the building height in `properties.height_m`, in metres. | Buildings with no height property get 10 m. See §5. |
| 5 | Put the tree size in `properties.height` and `properties.crownDiameter`, in metres. Set **both**. | If one value is bad, the platform replaces **both** with 8 m and 5 m. See §6. |
| 6 | Tag each ground polygon with `properties.material`. Use `water`, `concrete`, `asphalt`, `vegetation`, or `soil`. | An unknown name becomes `concrete`. See §7. |
| 7 | Do **not** tag a building polygon with `material` or `surface`. | A polygon with either key goes to the ground-surface layer, not to the buildings layer. See §4. |
| 8 | Close every polygon ring. Put the outer ring first and the holes after it. | An empty or degenerate ring makes no mesh. |
| 9 | Keep each file below **40 MB**. | 40 MB is the hard cap for each format. See §9. |
| 10 | Keep to **500 trees** and **500 ground polygons**. | The platform keeps the first 500 of each and drops the rest. See §9. |

---

## 2. What the platform accepts

There are exactly three file formats. The registry is
`workflows/scenario-upload/format-adapters/index.ts`.

| Format | Extensions | Layers it can fill |
|---|---|---|
| GeoJSON | `.geojson`, `.json` | buildings, trees, ground materials |
| Wavefront OBJ | `.obj` | buildings, trees, ground materials |
| EnergyPlus Weather | `.epw` | weather |

Every other format fails. There is **no** adapter for `.ifc`, `.bim`, `.shp`,
`.dxf`, `.gltf`, `.glb`, `.3dm`, `.csv`, or `.kml`. Convert to GeoJSON or OBJ
first.

> **Correction to earlier versions of this page.** `.ifc` is no longer a
> registered but disabled format. It is not in the registry at all. The
> platform document `BYO-DRAFT.md` still says "IFC only when its adapter is
> enabled". The code is the authority: there are three adapters.

**You do not have to upload all four layers.** Buildings, trees, ground
materials, and weather are independent. Each layer that you do not upload comes
from the platform fetch source. A project with only a buildings file is a
normal project and it runs.

---

## 3. How an upload works — one draft, one Save

Every entry point opens the same local draft
(`apps/platform/docs/BYO-DRAFT.md`). The entry points are the project-creation
card, the Data-layers panel, and each layer row in the panel.

1. **Select the files.** The browser reads and parses them. Nothing goes to the
   server.
2. **The platform shows one combined model** on the map.
3. **Move each file into position.** Placement is per file. Two files that you
   upload separately are never aligned automatically. They land on the centre of
   the site, one on top of the other. Drag a file to move it. Shift-drag to turn
   it.
4. **Set the site boundary (the AOI).** Draw it, or let the platform suggest
   one. Geometry outside the AOI stays visible. The platform shows a warning and
   offers **Fit AOI to model**.
5. **Select Save.** This is the only step that writes to the server.

Important properties of this flow:

- **Nothing is written before Save.** Import, move, redraw, and fit make no
  server write.
- **An unsaved draft is lost if you close or refresh the tab.** This is
  intended behaviour.
- **Files of the same kind combine. They do not replace each other.** Two
  buildings files in one draft give you one buildings layer with both sets.
- **Only weather is limited to one file per draft.** A second `.epw` gives the
  error `A BYO draft can contain only one weather file.`
- **A file is never renamed into a "variant scenario".** Earlier versions of
  this page said that a second buildings file becomes a design variant. That
  behaviour was removed with the old upload paths.

---

## 4. One file can carry several layers

The platform routes **each feature** of a GeoJSON file, not the whole file. The
rule is in `workflows/scenario-upload/classify-upload-files.ts`
(`partitionDraftFeatureCollection`).

| Feature geometry | Feature properties | Goes to |
|---|---|---|
| `Point` | any | **trees** |
| `Polygon` or `MultiPolygon` | `material` or `surface` is a non-empty string | **ground materials** |
| `Polygon` or `MultiPolygon` | neither key | **buildings** |
| anything else (`LineString`, `MultiPoint`, `MultiLineString`, …) | any | dropped, with the warning `Ignored N unsupported GeoJSON features.` |

Two results follow from this table:

- **A mixed file is valid.** One FeatureCollection can hold your buildings,
  your trees, and your ground surfaces together. The platform splits it into
  three layers.
- **A `material` or `surface` key on a building polygon sends that building to
  the ground layer.** This is the most common silent error in a QGIS or an
  ArcGIS export, because `surface` is a frequent OSM tag. Remove the key from
  building features before you export.

> **Correction.** `properties.surface` now sets the material as well as the
> layer. The partition copies its value into `properties.material`. Earlier
> versions of this page said that a `surface` tag made every polygon
> `concrete`. That is no longer true.

The platform also accepts a second shape for ground materials: a JSON object of
per-material FeatureCollections, for example
`{"asphalt": FeatureCollection, "water": FeatureCollection}`.

---

## 5. Buildings — polygons with a height

Give a `FeatureCollection` of `Polygon` or `MultiPolygon` features. A
MultiPolygon becomes one feature for each part.

**Every key below is in the feature's `properties` object.** It is never at the
top level of the Feature.

```json
{ "type": "Feature",
  "properties": { "height_m": 24, "kind": "office" },
  "geometry": { "type": "Polygon", "coordinates": [[[16.371,48.208],[16.372,48.208],[16.372,48.209],[16.371,48.209],[16.371,48.208]]] } }
```

| Rule | Value |
|---|---|
| Height property | `height_m`, in metres |
| Missing height | 10 m (`DEFAULT_HEIGHT_M`) |
| Height clamp | 3 m to 200 m. The value is clamped, not rejected. |
| Optional `kind` | `residential`, `office`, or `tower`. It sets the display colour only. The value is case-sensitive and it is not validated. Write it in lower case. |
| Feature cap | 100,000 after MultiPolygon splitting |
| File cap | 40 MB |
| Rings | closed (first point equals last point), outer ring first, holes after |

**The platform reads more than `height_m`.** It tries these groups in order and
it takes the first hit. Keys are case-insensitive. A numeric string such as
`"7.7"` is accepted. A zero or a negative value is skipped, so a later name can
still win.

1. **A direct height in metres:** `height_m`, `heightm`, `height`, `h`,
   `building_height`, `buildingheight`, `bldg_height`, `building:height`,
   `roof_height`, `roofheight`, `gebaeudehoehe`, `gebäudehöhe`, `hoehe`,
   `höhe`, `altura`, `hauteur`.
2. **A pair of top and bottom elevations.** Both values must be there. Tops:
   `buildingtop`, `buildingto` (the ESRI 10-character truncation), `z_max`,
   `zmax`, `maxheight`, `max_height`, `relh_max`. Bottoms: `buildingbottom`,
   `buildingbo`, `ground_height`, `base_height`, `z_min`, `zmin`, `minheight`,
   `min_height`, `relh_min`.
3. **A floor count, multiplied by 3.0 m:** `building:levels`,
   `building_levels`, `levels`, `floors`, `num_floors`, `storeys`, `stories`,
   `geschosse`, `geschosszahl`, `geschossza`, `anzahl_geschosse`, `etagen`.

A raw OSM export with `building:levels` and an ArcGIS export with truncated
`BuildingTo` and `BuildingBo` both extrude correctly. You do not have to
compute `height_m` first.

---

## 6. Trees — `Point` features

Each tree is one `Point` feature. Do not use `MultiPoint`: the platform counts
it as an unsupported feature and drops it.

### Accepted property keys

The importer (`packages/primitives/vegetation/core/vegetation.import-utils.ts`)
reads these keys. The first key with a **positive finite** number wins.

| Value | Keys, in order of priority | Unit | Valid range |
|---|---|---|---|
| Tree height | `height`, `height_m` | metre | 1 to 30 |
| Crown diameter | `crownDiameter`, `diameter_crown`, `diameter_m`, `crown_m` | metre | 1 to 20 |

Notes on the aliases:

- `crownDiameter` is the canonical name. `diameter_crown` is the OSM key.
  `diameter_m` comes from the platform GIS fetch. `crown_m` comes from the
  Infrared city-library files.
- `crown_m` is a **diameter**, not a radius.
- A value found under an alias is written back to the canonical key. Everything
  after the import sees `height` and `crownDiameter`.

The SDK reads the same key names, but its ranges and its defaults are
different: the SDK has no 1–30 m / 1–20 m gate, and a tree with no size keys
simulates at the server default of 6 m by 4 m. See
[byo-inputs.md](byo-inputs.md). Do not carry a number from one page to the
other.

### The fallback rule — set both values

If the height **or** the crown diameter is missing, unreadable, or outside its
range, the platform replaces **both** values with the fallback: **8 m height and
5 m crown diameter**. It does this to keep the proportions of the tree correct.
This is why a file with a good height and no crown diameter gives you a forest
of identical trees.

### `properties.circumference` does not work on upload

The platform renderer can derive a height from a trunk circumference in metres
(`height ≈ 12 × circumference + 3`). **The importer does not read that key.** A
tree file with only `circumference` gets the 8 m fallback, and the fallback is
written into `height` before the renderer sees the feature. Convert the
circumference to a height in your export.

### Trees outside the site are kept, not dropped

The platform imports trees with clipping turned off. A tree outside the AOI is
kept and marked `properties.outsideBoundary = true`. A tree near the edge still
shades the result, because the tiler adds a context margin. A distant tree is
for reference only.

The 500-tree cap runs after this step, and it takes the trees **inside** the
AOI first. Trees outside the AOI can never push a real tree out of the run.

### Tree shape — what to write in `properties.archetype`

**Write `round`, `conical`, or `columnar`, or write nothing.** The platform
renderer (`vegetation.feature-dims.ts`) accepts only these three values. An
unknown value becomes `round`.

The Infrared Core registry
(`infrared-core: public/rust/crates/ir-simprep/data/archetypes.registry.json`,
version `archetypes-2026-06-13`) uses four different names: `broadleaf`,
`conifer`, `columnar`, and `palm`.

**The two vocabularies do not agree.** Only `columnar` is in both. If you write
`broadleaf`, `conifer`, or `palm` into a tree file, the platform ignores the
value and draws a round tree. Report this disagreement to Infrared rather than
work around it.

The OBJ import fits an archetype from the shape of each tree mesh: a constant
width gives `columnar`, a width that is widest at the bottom gives `conical`,
and a width that is widest in the middle or at the top gives `round`.

---

## 7. Ground surfaces — tagged polygons

Give one of these two shapes:

1. a `FeatureCollection` whose polygons carry `properties.material` (or
   `properties.surface`), or
2. a JSON object of per-material FeatureCollections, for example
   `{"asphalt": FeatureCollection, "water": FeatureCollection}`.

| Rule | Value |
|---|---|
| Canonical materials | `water`, `concrete`, `asphalt`, `vegetation`, `soil` |
| Synonyms, mapped automatically | grass, forest, wood, shrub, scrub, tree, trees, park, green → `vegetation` · road, pavement, tarmac, parking → `asphalt` · sand, bare_ground, bare, ground, dirt, earth, gravel → `soil` · pond, lake, river, sea → `water` · paving, building → `concrete` |
| Unknown name | mapped to `concrete`, and kept. The platform names it in a warning. |
| No name at all | mapped to `concrete`, and reported as `(unlabeled)` |
| Geometry | polygons only. Other geometry is filtered out. |
| Polygon cap | 500 in total across all materials. Later materials are truncated first. |
| File cap | 40 MB |

Surfaces are not clipped to the AOI. A surface fully outside the AOI is kept for
reference, but it does **not** change the result: ground materials have no
context margin. A surface that crosses the boundary is kept whole, and only the
part inside the AOI changes the result.

In the object shape, all members must use one coordinate system. A mix of
longitude/latitude members and local-metre members is rejected.

---

## 8. OBJ — units and object names

An OBJ file holds local coordinates. It needs no georeferencing. One OBJ can
carry buildings, trees, and ground surfaces together.

### Units — the trap

**An OBJ file carries no unit.** The platform guesses the unit from the size of
the model (`lib/obj-import/unit-detect.ts`). It tests `m`, `mm`, `ft`, `cm`, and
`dm`. It scores each unit on two tests:

- the horizontal extent of the site must be between 10 m and 20 km, and it is
  best between 40 m and 3 km;
- the tallest object must be between 1 m and 500 m, and it is best between 3 m
  and 120 m.

It then multiplies each score by a preference: `m` 1.0, `mm` 0.9, `ft` 0.8,
`cm` 0.7, `dm` 0.4.

**A large model in metres can score better as feet.** A site of about 5 km with
200 m towers is one example: in metres the extent and the height are both above
the ideal band, and in feet both fall inside it. The platform then selects
"feet" and the model comes in at 30 % of its true size.

**A wrong unit also changes the classification.** The classifier measures
heights in metres to decide what an object is
(`lib/obj-import/classify-objects.ts`). A building that reads as 3 m tall
because of a feet-to-metres error can pass the tree test instead. This is how a
building model becomes "trees".

**What to do in your export:**

- Set the model units to **metres** in Rhino, Blender, or SketchUp before you
  export. Rhino exports millimetres by default.
- Keep the model near the origin and keep it to a real site size. A site
  between 40 m and 3 km across, with the tallest object between 3 m and 120 m,
  scores best as metres and is guessed correctly.
- If your site is larger than about 3 km, expect a wrong guess. Correct it in
  the **Review model** dialog.

### Object names — the classification

The platform reads the `o` and `g` object name together with the `usemtl`
material names. It matches on word boundaries and it ignores case.

| Name contains | Class |
|---|---|
| build, building, buildings, bldg, haus, gebäude, gebaeude, house, houses, massing, volume, tower, block | **buildings** |
| tree, trees, baum, bäume, baeume, arbre, canopy, crown, bush, bushes, shrub, hedge | **trees** |
| ground, terrain, topo, surface, floor, road, roads, street, streets, straße, strasse, weg, path, asphalt, concrete, paving, pavement, sidewalk, plaza, platz, water, pond, lake, river, grass, lawn, soil, sand, gravel, site, context | **ground surfaces** |
| vegetation, veg, green, greenery, forest, wood | ambiguous. A z-extent below 0.5 m gives a surface. More gives trees. |

A building name wins over a tree name in the same string.

**If no name matches**, the platform uses the geometry:

1. a z-extent below 0.5 m gives a **surface**;
2. three or more separate parts, of which 70 % or more are 1.5 m to 35 m tall
   with a crown of 25 m or less, give **trees**;
3. everything else gives **buildings**.

Name your objects. It is the only way to control the split.

### The Review model dialog — a known trap

**Review model** is optional. The platform applies the guessed unit and the
guessed classification straight away. Open the dialog to correct them.

The dialog opens on a list titled **Unassigned objects**. That list holds only
the objects that fell through to buildings by default. There is a **Show all
(N)** link above it.

> **Known bug — read this before you use the dialog.**
> When you assign a category to an object, that object leaves the "unassigned"
> list. If it was the last one, the whole list disappears — and the **Show all**
> link disappears with it, because the link is inside the list component
> (`obj-object-list.tsx` returns nothing for an empty list). You then cannot
> change the category back.
>
> **Work around it: select "Show all (N)" FIRST, before you assign anything.**
> The full list does not empty itself, so every object stays reachable.
> If the list is already gone, select Cancel and import the file again.

Work in this order in the dialog:

1. Set **Units** first. A unit change re-plans and re-classifies everything.
2. Set **Up axis**, **Flip vertical**, **Swap footprint axes**, and **Drop to
   ground**.
3. Select **Show all (N)**.
4. Correct the categories. Machine-numbered names such as `ctx_0` to `ctx_289`
   are grouped into one row, and one click assigns the whole group.
5. Select **Apply**.

### Other OBJ rules

- Faces can be triangles, quadrilaterals, or n-gons.
- Negative (relative) face indices are rejected.
- Free-form curve elements are skipped, with a warning.
- The file cap is 40 MB.
- The platform centres the model on the site and puts its lowest point at
  ground level (`obj-anchor-math.ts`). Move it from there.

---

## 9. Coordinates, placement, and the site boundary

### GeoJSON coordinates

Use **EPSG:4326 (WGS84)** with the axis order `[longitude, latitude]`. The
platform repairs the common deviations:

| Input | Result |
|---|---|
| Projected coordinates with a `crs` member for a supported EPSG code | reprojected to WGS84, with a notice |
| Projected coordinates with an unsupported EPSG code | rejected. The message names the code. |
| Metre coordinates with no `crs` member | put on the centre of your site. You then move the file on the map. |
| Longitude and latitude in the wrong order | corrected when the platform is sure. Otherwise rejected. |

Automatic reprojection covers WGS84/UTM (`EPSG:326xx` and `327xx`, zones 1 to
60), ETRS89/UTM (`25828` to `25838`), DHDN Gauss-Krüger (`31466` to `31469`),
`27700` (British National Grid), `2154` (Lambert-93), `28992` (RD New), `3035`
(ETRS89-LAEA), and `3857` (Web Mercator). The `crs` member is read in the
OGC-URN form, the `EPSG:<code>` form, the `{type:'EPSG',properties:{code}}`
form, the `CRS84` form, and as a bare number.

Two gates reject a file before anything else happens:

- a span of more than **2° on either axis** gives `This geometry looks
  mislocated (implausibly large span or near a pole).`;
- a centroid above **85° of latitude** gives the same message.

### The site boundary

The AOI is the polygon that the platform tiles, prices, and runs. It is **not**
the extent of your geometry.

- **A project has one boundary.** All scenarios in a project share it. An
  explicit boundary edit writes to every scenario in the project.
- For a new project, the first georeferenced file sets the boundary from its own
  bounds. A point or a zero-width extent gets a 100 m envelope.
- For a file with no georeferencing, such as an OBJ, the platform suggests a
  rectangle around the model with a **30 m** margin, centred on the map camera.
  If the map has published no centre yet, the draft asks you to pick or draw the
  site.
- **Fit AOI to model** derives an AOI from the draft geometry. It caps the area
  at **6 km²** (`MAX_PROJECT_AREA_KM2`) and it shrinks a long, thin shape more
  until the AOI tiles into 128 cells or fewer (`SITE_TILE_LIMIT`).

### Geometry outside the AOI

Geometry outside the AOI is **kept and drawn**. The platform never clips it,
rejects it, or deletes it. It shows the warning `Some geometry is outside the
site.` and offers **Fit AOI to model**.

The warning is a bounding-box test on four corners for each layer. It is a hint,
not exact coverage. A turned model can raise a false warning. A shape that dips
into a hole in the AOI can escape the warning.

If the data has no ground in common with the site at all, the platform shows
`This data is far from your site — it is drawn at its own location.` This
happens with a correctly georeferenced file for a different city.

Practical rule: keep the part that you want **analysed** within about 1.2 km of
the centre of the site. Keep the surrounding buildings in the file: they still
shade the result.

---

## 10. Size limits

Every number below comes from the code. Nothing here is an estimate.

| Limit | Value | Where |
|---|---|---|
| GeoJSON file | 40 MB | `geojson-adapter.ts` |
| OBJ file | 40 MB | `obj-adapter.ts` |
| EPW file | 40 MB | `epw-adapter.ts` |
| Building features | 100,000, counted after MultiPolygon splitting | `geojson-adapter.ts` |
| Trees kept | 500, inside the AOI first | `MAX_TREE_COUNT` |
| Ground polygons kept | 500 in total | `MAX_POLYGON_COUNT` |
| Analysis AOI area | 6 km² | `MAX_PROJECT_AREA_KM2` |
| Tiles for one AOI | 128 non-empty cells | `SITE_TILE_LIMIT` |
| Body sent through the API Worker | up to 32 MB | `PRESIGN_THRESHOLD_BYTES` |
| Body sent straight to storage with a presigned URL | above 32 MB, up to 1 GiB | `PRESIGN_MAX_BYTES` |
| Life of a presigned upload URL | 900 s (15 minutes) | `PRESIGN_TTL_S` |

Notes:

- The 32 MB threshold and the 1 GiB cap are **server** limits for the saved
  artifact. The client rejects your file at 40 MB first, so you will not meet
  them with a normal geometry file.
- **There is no 5 MB cap on a trees file today.** The 5 MB cap lives in
  `parseTreesGeoJson`, and the draft path does not call it. Only the 40 MB
  GeoJSON cap applies. Earlier versions of this page said 5 MB.
- **There is no 10 km² rejection today.** `MAX_UPLOAD_AREA_KM2 = 10` is still
  declared but nothing reads it. The AOI is bounded instead, at Fit time.

---

## 11. Weather — EnergyPlus `.epw`

Use a real TMY or AMY file. Download one and do not edit it.

A complete file has an 8-line header (line 1 is `LOCATION,<city>,<state>,
<country>,<source>,<wmo>,<lat>,<lon>,<tz>,<elevation>`, line 8 is `DATA
PERIODS,...`), then 8,760 hourly rows of 35 columns for a non-leap year.

The parser is looser than the full standard, so a real file always passes. It
needs a `LOCATION` line, and it needs at least one row with a usable dry-bulb
temperature. A `99.9` in the dry-bulb column means "missing". Do not truncate
the columns by hand.

Key columns, counted from 0: 1 month · 2 day · 3 hour (1 to 24) · **6 dry-bulb
°C** · 8 relative humidity % · 13 global horizontal irradiance Wh/m² · 20 wind
direction ° · 21 wind speed m/s.

Sources: climate.onebuilding.org and the EnergyPlus weather archive. See
[04-weather-data.md](04-weather-data.md).

**One limit to state to a user:** an uploaded EPW file is used by the SDK
analyses. AI-backed workflows use weather that AIBackend selects. An EPW upload
does not change an AI-backed workflow.

---

## 12. Common failures and what they mean

### Rejections — the file, or the draft, does not load

| Message | Cause | Fix |
|---|---|---|
| `<name>: this format cannot be added to a BYO draft.` | The extension is not `.geojson`, `.json`, `.obj`, or `.epw`. | Convert to GeoJSON or OBJ. |
| `<name>: file exceeds the <format> size limit.` | The file is above 40 MB. | Simplify or split the file. |
| `File too large — max 40 MB.` | The same cap, raised inside the adapter. | Simplify or split the file. |
| `File is not valid JSON.` | The file is truncated or it is not JSON. | Export it again. |
| `Expected a GeoJSON FeatureCollection or material-layer object.` | The root is a bare Feature, a bare geometry, or something else. | Wrap the data in a `FeatureCollection`. |
| `Too many features (N). Max 100,000 — split or simplify the file.` | Too many building polygons. | Split or simplify the file. |
| `No building polygons found in this file.` | The buildings parser found nothing. The BYO draft path routes features before this check, so you see this only through an older entry point. | Check that your building features have no `material` or `surface` key. |
| `This file has no supported non-empty draft geometry.` | Every feature was unsupported. | Use `Point`, `Polygon`, or `MultiPolygon` features. |
| `Coordinates use EPSG:<n>, an unsupported projected CRS.` | The declared CRS is outside the supported set. | Export again as EPSG:4326. |
| `This file's coordinates aren't longitude/latitude …` | Projected metres, no `crs` member, and no safe repair. | Add a `crs` member, or export as WGS84. |
| `This file appears mislocated for this project — … lat/lon order …` | The axes are swapped. | Export as `[longitude, latitude]`. |
| `This geometry looks mislocated (implausibly large span or near a pole).` | The file spans more than 2° on an axis, or it sits near a pole. | Crop the data. Check the CRS. |
| `No valid building footprints found — every polygon was empty or degenerate.` | Zero-area or malformed rings. | Repair the ring geometry. |
| `Not a valid GeoJSON FeatureCollection of Point features.` | A trees layer failed its schema check. | Use one `Point` feature for each tree. |
| `This surfaces file mixes lon/lat layers with local-coordinate layers` | The object shape uses two coordinate systems. | Use one coordinate system for all members. |
| `A BYO draft can contain only one weather file.` | Two `.epw` files in one draft. | Use one file. |
| `Not a valid .epw weather file — …` / `This .epw file has no usable weather readings.` | No `LOCATION` line, or every dry-bulb value is missing. | Use an unedited TMY or AMY file. |
| `The OBJ file has no importable geometry.` | The OBJ holds no faces that the platform can use. | Export buildings, tree meshes, or ground surfaces. |
| `No plausible unit found — the model is unrealistically small or large in every candidate unit (m/dm/cm/mm/ft).` | The model is an impossible size at every unit. | Check the export scale. |
| `Uploaded geometry has no readable coordinates.` | A local-metre file with no usable coordinates. | Export it again. |

### Silent corrections — no error, but the result looks wrong

| What you see | Cause |
|---|---|
| All buildings have the same height. | No height property was recognised. Every building got the 10 m default. |
| One building is far too short or too tall. | The value was clamped into the 3 m to 200 m range. |
| A building is in the ground layer. | The feature carries `properties.material` or `properties.surface`. |
| A building is missing. | Its geometry is not a `Polygon` or a `MultiPolygon`, so it was dropped as an unsupported feature. |
| All trees are the same (8 m, 5 m crown). | The height or the crown diameter was missing or out of range, so **both** were replaced. |
| Trees are round when you expected conifers. | `properties.archetype` used a registry name (`broadleaf`, `conifer`, `palm`) that the renderer does not know. |
| There are fewer trees than you exported. | The 500-tree cap. Trees inside the AOI are kept first. |
| Every surface is `concrete`. | The material name is not in the canonical list and is not a known synonym. |
| Surfaces are missing. | The 500-polygon cap. Later materials are truncated first. |
| Buildings became trees, and everything is too small. | The OBJ unit was guessed wrong. A wrong unit also changes the classification. Set the unit in **Review model**. |
| Your model sits on the site centre, not where you meant. | A file with no georeferencing is centred on the site. Drag it into position before you Save. |
| Two files sit on top of each other. | Placement is per file, and separate uploads are never pre-aligned. Move each one. |
| The analysis covers less than you uploaded. | **Fit AOI to model** capped the AOI at 6 km². The geometry outside it is kept as context. |

---

## 13. Notes for each source application

**Rhino and Grasshopper.** Set the document units to metres before you export
OBJ. Rhino writes millimetres by default. Name each layer or object with
`building`, `tree`, or `ground`. Export Y-up or Z-up: the platform detects the
up axis and you confirm it.

**QGIS.** Export as GeoJSON with the CRS set to EPSG:4326. Delete a `surface`
field from a buildings layer before you export, or the buildings become ground
polygons. Keep the height field: `height`, `building:levels`, or any name in
§5.

**ArcGIS.** A shapefile export truncates a field name to 10 characters. The
platform reads `buildingto` and `buildingbo` for this reason. Export to GeoJSON,
not to a shapefile: there is no shapefile adapter.

**Blender.** Set the scene unit to metres and the scale to 1.0. Turn OFF "Y
forward / Z up" conversion only if you want Z up in the file; the platform
detects either. Name each object.

**SketchUp.** Export OBJ in metres. SketchUp writes one group for each object,
so give each group a useful name.

**OSM data.** A raw OSM export works. `building:levels` extrudes correctly and
`diameter_crown` is read as the crown diameter. Convert `circumference` to a
height first (see §6).

---

## 14. What this page does not state

These points are not specified in the code that was read, so no claim is made
about them:

- The behaviour of the `.epw` header beyond the `LOCATION` line and the
  dry-bulb column. The parser is looser than the standard.
- Whether a very large OBJ (near 40 MB) completes the browser parse inside a
  usable time. There is no time limit in the code.
- The exact tile count for a given AOI shape. Only the 128-cell ceiling is
  declared.
