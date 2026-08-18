# Platform file upload — producing a file the platform accepts

<!-- Verified against forge-kit@origin/main fc69c214 (2026-08-18). -->

How to save a file from Rhino, Grasshopper, QGIS, ArcGIS, Blender, or SketchUp
so that platform.infrared.city accepts it at the first try.

This is the **file** contract for the platform. For in-memory payloads in your
own Python, read [byo-inputs.md](byo-inputs.md) — the two are not
interchangeable. To get data out, read [platform-export.md](platform-export.md).

Validated sample data: `cookbook/sample-data/platform-upload/` (synthetic,
minimal) and `cookbook/sample-data/vienna-demo/` (real Vienna open data).

## Checklist before you write the file

| # | Do this | If you do not |
|---|---|---|
| 1 | Write GeoJSON as **EPSG:4326**, axis order `[longitude, latitude]`. | A file with no `crs` lands on the site centre and you must move it. |
| 2 | Write OBJ in **metres**. | The unit is guessed. A wrong guess also breaks the classification. |
| 3 | Name every OBJ object `building*`, `tree*`, or `ground*`. | Unnamed objects are classified by shape. |
| 4 | Put the building height in `properties.height_m`. | Every building becomes 10 m. |
| 5 | Set **both** `properties.height` and `properties.crownDiameter` on trees. | Both are replaced by 8 m / 5 m. |
| 6 | Tag ground polygons `properties.material` with a canonical name. | The surface becomes `concrete`. |
| 7 | Do **not** put `material` or `surface` on a building polygon. | The building goes to the ground layer. |
| 8 | Close every ring. Outer ring first, holes after. | A degenerate ring makes no mesh. |
| 9 | Keep each file below 40 MB, 500 trees, and 500 ground polygons. | The excess is rejected or truncated. |

## Per application

| Source | Watch for |
|---|---|
| Rhino, Grasshopper | Set document units to metres — Rhino writes millimetres by default. Name layers and objects. |
| QGIS | Save as EPSG:4326. Delete a `surface` field from a buildings layer, or the buildings become ground polygons. |
| ArcGIS | Shapefile truncates field names to 10 characters, hence `buildingto` / `buildingbo`. Write GeoJSON — there is no shapefile adapter. |
| Blender | Scene unit metres, scale 1.0. Name every object. |
| SketchUp | Write OBJ in metres. Name each group. |
| OSM data | `building:levels` and `diameter_crown` work as-is. Convert `circumference` to a height first. |

## Accepted formats

| Format | Extensions | Layers it can fill |
|---|---|---|
| GeoJSON | `.geojson`, `.json` | buildings, trees, ground materials |
| Wavefront OBJ | `.obj` | buildings, trees, ground materials |
| EnergyPlus Weather | `.epw` | weather |

There are exactly three adapters. `.ifc`, `.bim`, `.shp`, `.dxf`, `.gltf`,
`.glb`, `.3dm`, `.csv`, and `.kml` all fail. Convert to GeoJSON or OBJ first.

You do not have to supply all four layers. Any layer you do not upload comes
from the platform fetch source, so a buildings-only project is normal and it
runs.

## How an upload works

Every entry point — the project-creation card, the Data-layers panel, and each
layer row — opens the same local draft.

1. Select the files. The browser parses them. Nothing goes to the server.
2. The platform shows one combined model on the map.
3. Move each file into position. Drag to move, shift-drag to turn.
4. Draw or adjust the site boundary (the AOI).
5. Select **Save**. This is the only step that writes.

Consequences:

- **An unsaved draft is lost when the tab closes.** This is intended.
- **Placement is per file.** Separate uploads are never pre-aligned — they stack
  on the site centre until you move them.
- **Files of the same kind combine.** They do not replace each other. Only
  weather is limited to one file per draft.

## One file, several layers

The platform routes **each feature**, not the whole file.

| Geometry | Properties | Goes to |
|---|---|---|
| `Point` | any | trees |
| `Polygon` / `MultiPolygon` | `material` or `surface` is a non-empty string | ground materials |
| `Polygon` / `MultiPolygon` | neither key | buildings |
| anything else | any | dropped, with `Ignored N unsupported GeoJSON features.` |

So one FeatureCollection can carry buildings, trees, and surfaces together —
and a stray `surface` tag on a building sends that building to the ground
layer. `surface` also sets the material, not only the layer.

Ground materials accept a second shape: an object of per-material collections,
for example `{"asphalt": FeatureCollection, "water": FeatureCollection}`.

## Buildings

A `FeatureCollection` of `Polygon` or `MultiPolygon`. Each MultiPolygon part
becomes its own feature. **Every key below sits in `properties`**, never at the
top level of the Feature.

```json
{ "type": "Feature",
  "properties": { "height_m": 24, "kind": "office" },
  "geometry": { "type": "Polygon", "coordinates": [[[16.371,48.208],[16.372,48.208],[16.372,48.209],[16.371,48.209],[16.371,48.208]]] } }
```

| Rule | Value |
|---|---|
| Missing height | 10 m |
| Height clamp | 3–200 m, clamped and not rejected |
| Optional `kind` | `residential`, `office`, `tower` — display colour only, lower case, not validated |
| Feature cap | 100,000 after MultiPolygon splitting |

**You do not have to precompute `height_m`.** The platform tries three groups in
order and uses the first value found. Keys are case-insensitive. Numeric
strings are accepted. A zero or negative value falls through to the next name.

1. **Direct height, metres** — `height_m`, `heightm`, `height`, `h`,
   `building_height`, `buildingheight`, `bldg_height`, `building:height`,
   `roof_height`, `roofheight`, `gebaeudehoehe`, `gebäudehöhe`, `hoehe`, `höhe`,
   `altura`, `hauteur`.
2. **Top and bottom elevation, both required** — tops: `buildingtop`,
   `buildingto`, `z_max`, `zmax`, `maxheight`, `max_height`, `relh_max`;
   bottoms: `buildingbottom`, `buildingbo`, `ground_height`, `groundheight`,
   `base_height`, `baseheight`, `z_min`, `zmin`, `minheight`, `min_height`,
   `relh_min`.
3. **Floor count × 3.0 m** — `building:levels`, `building_levels`, `levels`,
   `floors`, `num_floors`, `numfloors`, `storeys`, `stories`, `geschosse`,
   `geschosszahl`, `geschossza`, `anzahl_geschosse`, `etagen`.

A raw OSM file with `building:levels` and an ArcGIS file with the truncated
`BuildingTo` / `BuildingBo` both extrude correctly.

## Trees

One `Point` feature per tree. `MultiPoint` counts as unsupported and is dropped.

| Value | Keys, first positive number wins | Valid range |
|---|---|---|
| Height (m) | `height`, `height_m` | 1–30 |
| Crown **diameter** (m) | `crownDiameter`, `diameter_crown`, `diameter_m`, `crown_m` | 1–20 |

All four crown keys are diameters, not radii. A value found under an alias is
written back to the canonical key.

**Set both values.** If either one is missing, unreadable, or out of range, the
platform replaces **both** with 8 m and 5 m to keep the proportions correct.
This is why a file with good heights and no crown diameter gives identical
trees.

**`properties.circumference` does not work on upload.** The renderer can derive
a height from it, but the importer never reads it — the 8 m fallback is written
into `height` first. Convert circumference to a height before you write the
file.

**Trees outside the AOI are kept**, marked `outsideBoundary`, and drawn. A tree
near the edge still shades the result through the tiler context margin. The
500-tree cap runs afterwards and takes trees inside the AOI first, so reference
trees can never evict simulated ones.

**Tree shape:** write `round`, `conical`, or `columnar` in
`properties.archetype`, or write nothing. Those are the only values the platform
renderer accepts; anything else silently becomes `round`. The Infrared Core
registry (`archetypes-2026-06-13`) uses a different vocabulary — `broadleaf`,
`conifer`, `columnar`, `palm`. The two vocabularies overlap only at `columnar`,
so a registry name gives you round trees. There is no workaround.

The OBJ import fits the archetype from the mesh: constant width → `columnar`,
widest at the bottom → `conical`, widest in the middle or top → `round`.

## Ground surfaces

| Rule | Value |
|---|---|
| Canonical materials | `water`, `concrete`, `asphalt`, `vegetation`, `soil` |
| Synonyms | grass, forest, wood, shrub, scrub, tree(s), park, green → `vegetation` · road, pavement, tarmac, parking → `asphalt` · sand, bare_ground, bare, ground, dirt, earth, gravel → `soil` · pond, lake, river, sea → `water` · paving, building → `concrete` |
| Unknown or untagged | mapped to `concrete` and kept, with a warning |
| Polygon cap | 500 in total. Later materials are truncated first. |

Surfaces are not clipped. A surface outside the AOI is kept for reference but it
does **not** change the result — ground materials have no context margin. A
surface crossing the boundary is kept whole, and only the part inside counts.

In the object shape, every member must use one coordinate system.

## OBJ — units and object names

An OBJ holds local coordinates and needs no georeferencing. One file can carry
buildings, trees, and surfaces together.

### Units

**OBJ carries no unit.** The platform scores each candidate on two tests — site
extent (10 m to 20 km, ideal 40 m to 3 km) and tallest object (1 to 500 m,
ideal 3 to 120 m) — then multiplies by a preference:

| Unit | m | mm | ft | cm | dm |
|---|---|---|---|---|---|
| Preference | 1.0 | 0.9 | 0.8 | 0.7 | 0.4 |

**A large metric model can score better as feet.** Take a 5 km site with 200 m
towers. In metres both measurements are above the ideal band. In feet both fall
inside it. "Feet" then wins, and the model arrives at 30 % of its true size.

**A wrong unit also changes the classification**, because the classifier
measures heights in metres. A building that reads as 3 m tall passes the tree
test instead. This is how a building model becomes "trees".

Write the file in metres. Keep the model near the origin. Keep it to a real
site size. Above about 3 km, expect a wrong guess and correct it in **Review model**.

### Object names

The platform reads the `o` / `g` name together with the `usemtl` names, on word
boundaries, ignoring case. A building name wins over a tree name.

| Name contains | Class |
|---|---|
| build, building(s), bldg, haus, gebäude, gebaeude, house(s), massing, volume, tower, block | buildings |
| tree(s), baum, bäume, baeume, arbre, canopy, crown, bush(es), shrub, hedge | trees |
| ground, terrain, topo, surface, floor, road(s), street(s), straße, strasse, weg, path, asphalt, concrete, paving, pavement, sidewalk, plaza, platz, water, pond, lake, river, grass, lawn, soil, sand, gravel, site, context | ground surfaces |
| vegetation, veg, green, greenery, forest, wood | ambiguous — z-extent under 0.5 m gives a surface, more gives trees |

With no name match the platform uses the geometry: z-extent under 0.5 m gives a
**surface**; three or more parts of which 70 % are 1.5–35 m tall with a crown of
25 m or less give **trees**; everything else gives **buildings**.

Faces may be triangles, quads, or n-gons. Negative face indices are rejected.
Free-form curves are skipped with a warning. The platform centres the model on
the site and grounds its lowest point.

### Review model — work in this order

**Review model** is optional; the platform applies its guesses immediately.
Inside the dialog:

1. Set **Units** first. A unit change re-plans and re-classifies everything.
2. Set the orientation controls (up axis, flip, swap axes, drop to ground).
3. Select **Show all (N)** — see the warning below.
4. Correct the categories. Machine-numbered names such as `ctx_0` … `ctx_289`
   collapse into one row, and one click assigns the whole group.
5. Select **Apply**.

> **Known bug.** The dialog opens on "Unassigned objects". Assigning a category
> removes that object from the list, and when the list empties, the whole
> component disappears — taking the **Show all** link with it. You then cannot
> change a category back. **Select "Show all (N)" before you assign anything.**
> If the list is already gone, Cancel and import the file again.

## Coordinates and the site boundary

Use EPSG:4326 with `[longitude, latitude]`. The platform repairs the common
deviations:

| Input | Result |
|---|---|
| Projected + `crs` for a supported EPSG | reprojected, with a notice |
| Projected + unsupported EPSG | rejected; the message names the code |
| Metres, no `crs` | centred on your site; you then move it on the map |
| Swapped axes | corrected when unambiguous, otherwise rejected |

Supported for automatic reprojection: WGS84/UTM (`326xx`, `327xx`), ETRS89/UTM
(`25828`–`25838`), Gauss-Krüger (`31466`–`31469`), `27700`, `2154`, `28992`,
`3035`, `3857`. A span over **2° per axis** or a centroid above **85° latitude**
is rejected before anything else.

The AOI is the polygon that is tiled, priced, and run. It is **not** the extent
of your geometry.

- **A project has one boundary.** An explicit edit writes to every scenario in
  the project.
- A new project takes its boundary from the first georeferenced file. A file
  with no georeferencing gets a suggested rectangle with a 30 m margin, centred
  on the map camera.
- **Fit AOI to model** caps the area at 6 km² and shrinks a long, thin shape
  further until it tiles into 128 cells or fewer.
- **Geometry outside the AOI is kept and drawn.** It is never clipped or
  deleted. You get `Some geometry is outside the site.` and the offer to fit.
  Data with no ground in common gives `This data is far from your site — it is
  drawn at its own location.`

Practical rule: keep what you want *analysed* within about 1.2 km of the site
centre, and keep the surrounding buildings in the file — they still shade the
result.

## Limits

| Limit | Value |
|---|---|
| GeoJSON / OBJ / EPW file | 40 MB each |
| Building features | 100,000 |
| Trees kept | 500, inside the AOI first |
| Ground polygons kept | 500 in total |
| Analysis AOI area | 6 km² |
| Tiles per AOI | 128 non-empty cells |
| Body through the API worker | up to 32 MB; above that a presigned upload, up to 1 GiB |

The 32 MB and 1 GiB values are server limits for the saved artifact. The client
rejects your file at 40 MB first, so a normal geometry file never meets them.

## Weather

Use an unedited TMY or AMY file (climate.onebuilding.org, the EnergyPlus
archive). A full file is an 8-line header (line 1 `LOCATION,…`, line 8 `DATA
PERIODS,…`) then 8,760 hourly rows of 35 columns.

The parser is looser than the standard, so any real file passes: it needs a
`LOCATION` line and at least one usable dry-bulb value. `99.9` means missing.
Do not truncate columns by hand.

| Column (from 0) | 1 | 2 | 3 | **6** | 8 | 13 | 20 | 21 |
|---|---|---|---|---|---|---|---|---|
| Holds | month | day | hour | **dry-bulb °C** | RH % | GHI Wh/m² | wind direction ° | wind speed m/s |

See [04-weather-data.md](04-weather-data.md).

An uploaded EPW drives the SDK analyses. **AI-backed workflows use weather that
AIBackend selects** — an EPW upload does not change them.

## Pitfalls

Hard rejects — the message names the file:

| Message | Cause |
|---|---|
| `<name>: this format cannot be added to a BYO draft.` | Extension is not `.geojson`, `.json`, `.obj`, `.epw` |
| `<name>: file exceeds the <format> size limit.` / `File too large — max 40 MB.` | Over 40 MB |
| `File is not valid JSON.` | Truncated or non-JSON |
| `Expected a GeoJSON FeatureCollection or material-layer object.` | Bare Feature, bare geometry, or another root |
| `Too many features (N). Max 100,000` | Too many building polygons |
| `This file has no supported non-empty draft geometry.` | Every feature was unsupported |
| `Coordinates use EPSG:<n>, an unsupported projected CRS.` | CRS outside the supported set |
| `This file's coordinates aren't longitude/latitude …` | Projected metres, no `crs`, no safe repair |
| `This file appears mislocated for this project — … lat/lon order …` | Swapped axes |
| `This geometry looks mislocated (implausibly large span or near a pole).` | Over 2° per axis, or near a pole |
| `No valid building footprints found — every polygon was empty or degenerate.` | Zero-area or malformed rings |
| `Not a valid GeoJSON FeatureCollection of Point features.` | A trees layer failed its schema check |
| `This surfaces file mixes lon/lat layers with local-coordinate layers` | Two coordinate systems in the object shape |
| `A BYO draft can contain only one weather file.` | Two `.epw` files |
| `Not a valid .epw weather file — …` / `This .epw file has no usable weather readings.` | No `LOCATION` line, or every dry-bulb value missing |
| `The OBJ file has no importable geometry.` | No usable faces |
| `No plausible unit found …` | Impossible size at every unit |

Silent corrections — no error, but the result looks wrong:

| What you see | Cause |
|---|---|
| All buildings the same height | No height key recognised — everyone got 10 m |
| One building far too short or tall | Clamped into 3–200 m |
| A building landed in the ground layer | It carries `material` or `surface` |
| A building is missing | Its geometry is not a `Polygon` / `MultiPolygon` |
| All trees identical (8 m, 5 m) | Height or crown missing / out of range — **both** replaced |
| Trees round when you expected conifers | `archetype` used a registry name the renderer does not know |
| Fewer trees than the file holds | The 500 cap, inside the AOI first |
| Every surface is `concrete` | Material name not canonical and not a known synonym |
| Surfaces missing | The 500-polygon cap — later materials truncated first |
| Buildings became trees, everything too small | Wrong OBJ unit — it also drives the classification |
| Model sits on the site centre | A file with no georeferencing is auto-centred. Drag it before Save. |
| Two files stacked on each other | Placement is per file. Move each one. |
| Analysis covers less than you uploaded | Fit capped the AOI at 6 km²; the rest is kept as context |

## See also

- [byo-inputs.md](byo-inputs.md) — the SDK path. Same tree key names, but no
  1–30 / 1–20 gate, and untagged trees default to 6 m × 4 m. Do not carry a
  number between the two pages.
- [geospatial-crs.md](geospatial-crs.md) — reprojection recipes.
- [platform-export.md](platform-export.md) — getting data back out.
