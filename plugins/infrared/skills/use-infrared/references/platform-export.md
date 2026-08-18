# Platform export — what comes out, and how to read it back

<!-- Verified against forge-kit@origin/main fc69c214 (2026-08-18). -->

The Infrared **platform** (platform.infrared.city) can write a project to a ZIP
archive. It can also read a project bundle back. This page states the formats.

To put a file INTO the platform, read
[platform-byo-upload.md](platform-byo-upload.md).

---

## 1. Availability — read this first

**Project export and project import are a staging surface today. They are not
in production.**

The export dialog and the import dialog are behind the build flag
`VITE_PROJECT_PORTABILITY`. The deploy workflow sets the flag to `1` only for
the `staging` branch. The comment in
`.github/workflows/deploy-platform.yml` says it plainly: "Project bundle
import/export remains a staging-only test surface."

So:

- On **staging**, the export and import controls are visible.
- On **production** (platform.infrared.city), they are not visible.
- In local development, you can turn the flag on with the browser key
  `ir-project-portability` set to `1`.

Do not tell a customer that project export is available until Infrared moves the
flag to production. State it as a staging feature.

Result maps have a separate, older route: an analysis result can be exported as
a GeoTIFF from the result view. That path is not behind this flag.

---

## 2. What the export dialog offers

The export dialog has five independent choices. You must select at least one.
The review step lists every path in the ZIP before the download starts.

| Choice | Default | What you get | What you can do with it |
|---|---|---|---|
| Site and buildings | On | `geometry.obj`, `site.geojson`, `exchange.json` | Edit the geometry, then make a new scenario |
| Weather | Off | copies of the EPW files | external use only |
| Analysis results | Off | one map for each result — GeoTIFF, JPEG, or none — plus statistics, and an optional XLSX summary | external use only |
| Reports | Off | completed PDF and safe HTML copies; AI-workflow reports as Markdown with their figures; assistant reports as Markdown | external use only |
| Project backup | Off | canonical records and the stored files | a strict restore into the platform |

The map format is a property of the "Analysis results" choice, not a separate
choice. Select `GeoTIFF` (a georeferenced raster), `JPEG images`, or `Statistics
only`. The two raster formats are mutually exclusive. The statistics — the KPI
JSON, the area GeoJSON, and a metadata JSON — ship in all three cases.

Notes on the results:

- Only four analysis types have a real KPI definition: wind speed, thermal
  comfort index, direct sun hours, and solar radiation. The other types still
  export a map. The missing statistics come out as a
  `portable-kpi-unavailable` warning.
- A result JPEG uses the colours the map paints: the legend range on the grid
  header and the colour variant frozen on the result. JPEG has no transparency,
  so no-data cells are put on white. **The JPEG is not georeferenced.** The
  GeoTIFF beside it is the map layer.
- A grid above 40 megapixels gives a warning instead of an image.
- The optional spreadsheet is `portable/results-summary.xlsx`. It has one
  `Overview` sheet for every scenario, then one sheet for each scenario. The
  rows are long format — one row for each metric — because the analyses do not
  share a KPI shape. Numbers are written as numbers. The workbook points to the
  exported picture by its path in the ZIP; it does not embed it.
- Anything the export could not include is listed in `missing-files.txt` at the
  root of the ZIP. The download itself always completes.

The whole ZIP is capped at **2 GB** (`MAX_PROJECT_EXPORT_BYTES`). Above that,
the export fails with `Project export exceeds 2 GB.`

---

## 3. The geometry exchange triplet

This is the part you can edit in Rhino, Grasshopper, or QGIS. Each selected
scenario gets one directory:

```text
portable/scenarios/0001-scenario-name/exchange/
├── geometry.obj
├── site.geojson
└── exchange.json
```

`manifest.json` sits at the root of the ZIP. It names the role, the source
scenario, the media type, the frame, the encoding, the byte size, and the
SHA-256 hash of every file.

### Coordinate frames

`geometry.obj` uses **local metres**:

- X points east.
- Y points north.
- Z points up.
- Building faces are triangles.

`site.geojson` uses **WGS84 longitude and latitude**.

`exchange.json` records both frames and the hash of the boundary. An importer
must reject a missing, an invalid, or an inconsistent frame. It must not guess
the placement when valid exchange metadata is present.

### What each file is for

| File or feature | What it holds | What to do with it |
|---|---|---|
| `exchange.json` | the exchange version, the frames, the paths, the source project and scenario, the suggested name | Validate it first. Use it to bind the other two files. |
| `geometry.obj` | the full 3D building meshes | Import as buildings in the local metre frame. |
| `site.geojson`, feature with `forgekit_role = "aoi"` | the new scenario boundary | Create the new root scenario with this polygon. |
| `site.geojson`, feature with `forgekit_role = "bbox"` | the extent of the exchange, for information | Do not use it in place of the AOI. |
| `site.geojson`, feature with `forgekit_role = "building-footprint"` | a 2D building outline with height values, ready for GIS | Use it for mapping and 2D GIS work. Do not rebuild the 3D mesh from it. |
| `site.geojson`, feature with `forgekit_role = "tree"` | the tree position and the source properties | Import as semantic trees. |
| `site.geojson`, feature with `forgekit_role = "ground-surface"` | the ground-surface geometry and the material properties | Import as ground materials. |
| reports, results, weather copies | external reference files | Do not import them as geometry. |
| canonical restore records | the project backup | Ignore them in the geometry flow. |

Each building footprint is a horizontal convex hull of its 3D mesh, computed
deterministically. Its properties hold the source key, the base elevation, the
top elevation, the height, and an OSM ID when the source has one. The
`footprint_method` value is `projected-convex-hull-v1`. Use that value to tell
this approximation apart from a surveyed outline.

**Trees are not meshes in the OBJ.** They stay as semantic `Point` features in
`site.geojson`. Version 1 does not guess a 3D tree shape.

### Buildings as OBJ or as GeoJSON

The building output has one choice
(`exchange-building-format.ts`): `obj` or `geojson`. The default is `obj`.

- With `obj`, the buildings are meshes in `geometry.obj`, and `exchange.json`
  records `layers.buildings = ["geometry-obj"]`.
- With `geojson`, there is no `geometry.obj`. The buildings are footprints in
  `site.geojson`, and `exchange.json` records
  `layers.buildings = ["site-geojson"]`.

Trees and ground surfaces are always `site-geojson`.

### Reading the exchange back in

Follow this order:

1. Read and validate `exchange.json`.
2. Resolve its relative paths for `geometry.obj` and `site.geojson` inside the
   same directory.
3. Validate the site FeatureCollection. Select exactly one AOI feature.
4. Generate a new scenario ID.
5. Create an empty root scenario with the AOI and the suggested name.
6. Load `geometry.obj` as building draft data, in the declared local frame.
7. Load the tree and ground-surface features as semantic draft data.
8. Show the combined draft to the user.
9. Save once.

Two warnings for a caller of the API:

- **Do not send `parent_scenario_id`.** A parent ID starts the clone path, which
  copies the source artifacts and the results. The exchange must create an empty
  root scenario.
- The source project ID and the source scenario ID in `exchange.json` are
  provenance only. They do not authorise an overwrite and they are not target
  IDs.

Manual use is valid. A user can create an empty scenario, select `geometry.obj`
and `site.geojson`, and confirm the placement by hand. When `exchange.json` is
present and valid, the importer uses its frame and does not ask for a manual
placement.

### Version 1 limits

Version 1 supports Wavefront OBJ for editable 3D building meshes, and GeoJSON
for 2D footprints and site features. GLB, 3DM, IFC, Shapefile, GeoParquet, 3D
tree archetypes, and automatic result import are out of scope.

---

## 4. Project bundle import

A project backup goes back in through the bundle import routes
(`apps/platform/docs/BUNDLE-IMPORT.md`, migration `0009`).

The browser creates a session with `POST /warehouse/bundle-imports`. The session
makes a hidden staging project. The normal read and write routes need
`import_state='ready'`, so they cannot see or change a staging record.

For a small item, the browser sends the bytes to:

```http
PUT /warehouse/bundle-imports/:sessionId/items/:ordinal/blob
```

For a large item, the browser uses the multipart routes:

```http
POST /warehouse/bundle-imports/:sessionId/items/:ordinal/multipart
PUT  /warehouse/bundle-imports/:sessionId/items/:ordinal/parts/:partNumber
POST /warehouse/bundle-imports/:sessionId/items/:ordinal/complete
```

Then:

```http
POST /warehouse/bundle-imports/:sessionId/commit
```

The commit verifies the uploaded objects, writes the canonical records in
batches, and publishes the project, the scenarios, and the session in one final
step. A failed commit stays hidden and it can replay safely.

**This is a restore path, not an exchange path.** It rebuilds an Infrared
project. Do not use it to bring in geometry from another application. Use the
file upload for that.

---

## 5. What the export does not do

- **It does not lock the project.** The platform reads the catalog once, after
  you select Download ZIP. It does not scan storage first, repeat the read,
  refresh your selection, or reconcile a later edit. Changes made after the
  click are not in the ZIP. Start a new download when you need newer state.
- **It does not replace the source scenario.** A geometry exchange creates a new
  scenario when you read it back.
- **It does not send geometry to a conversion service.** The export runs in the
  browser. The source files stay on Cloudflare R2.
- **It does not import results.** Result maps come out. They do not go back in.

---

## 6. What this page does not state

- Whether Infrared plans to move `VITE_PROJECT_PORTABILITY` to production, and
  when. The flag is staging-only in the code that was read.
- The exact contents of the project-backup records. They are an internal restore
  format and no public contract is declared for them.
- A per-file size limit inside the ZIP. Only the 2 GB total is declared.
