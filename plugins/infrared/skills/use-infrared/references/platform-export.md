# Platform export — what comes out of a project

<!-- Verified against forge-kit@origin/main fc69c214 (2026-08-18). -->

platform.infrared.city can write a project to a ZIP archive, and can read a
project bundle back. To put files *in*, read
[platform-byo-upload.md](platform-byo-upload.md).

## Availability

**Project export and import are a staging surface. They are not in production.**

The dialogs sit behind the build flag `VITE_PROJECT_PORTABILITY`, which the
deploy workflow sets only for the `staging` branch. Do not promise project
export to a customer until Infrared moves the flag to production.

Result GeoTIFF export from a result view is a separate, older path and is not
behind this flag.

## What the export offers

Select at least one choice. The review step lists every ZIP path before the
download starts.

| Choice | Default | Output | Use |
|---|---|---|---|
| Site and buildings | On | `geometry.obj`, `site.geojson`, `exchange.json` | Edit the geometry, make a new scenario |
| Weather | Off | EPW copies | external only |
| Analysis results | Off | one map per result (GeoTIFF, JPEG, or none) plus statistics, and an optional XLSX | external only |
| Reports | Off | PDF and HTML copies; AI reports as Markdown with their figures | external only |
| Project backup | Off | canonical records and stored files | strict restore into the platform |

The map format belongs to "Analysis results": `GeoTIFF`, `JPEG images`, or
`Statistics only`. The two rasters are mutually exclusive. The statistics — KPI
JSON, area GeoJSON, metadata JSON — ship in all three cases.

- Only wind speed, thermal comfort index, direct sun hours, and solar radiation
  have a real KPI definition. Other types still export their map; the missing
  statistics come out as a `portable-kpi-unavailable` warning.
- A result JPEG uses the frozen legend range and colour variant. **It is not
  georeferenced** — the GeoTIFF beside it is the map layer. A grid over 40
  megapixels gives a warning instead of an image.
- `portable/results-summary.xlsx` has one `Overview` sheet plus one sheet per
  scenario, in long format (one row per metric) because analyses do not share a
  KPI shape. It references the exported picture by path; it does not embed it.
- Anything left out is listed in `missing-files.txt` at the ZIP root. The
  download itself always completes.
- The whole ZIP is capped at **2 GB**.

## The geometry exchange triplet

This is the editable part. Each selected scenario gets:

```text
portable/scenarios/0001-scenario-name/exchange/
├── geometry.obj      local metres — X east, Y north, Z up, triangles
├── site.geojson      WGS84 longitude / latitude
└── exchange.json     version, frames, paths, provenance, suggested name
```

`manifest.json` at the ZIP root names the role, source scenario, media type,
frame, encoding, byte size, and SHA-256 of every file.

| `forgekit_role` in `site.geojson` | Holds | Use |
|---|---|---|
| `aoi` | the new scenario boundary | Create the new root scenario with it |
| `bbox` | the exchange extent, for information | Do not use it instead of the AOI |
| `building-footprint` | 2D outline with height values | GIS work. Do not rebuild the 3D mesh from it. |
| `tree` | tree position and source properties | Import as semantic trees |
| `ground-surface` | surface geometry and material | Import as ground materials |

Footprints are a deterministic convex hull of the 3D mesh, stamped
`footprint_method: projected-convex-hull-v1` so a GIS consumer can tell them
apart from a surveyed outline. **Trees are never meshes in the OBJ** — they stay
as `Point` features.

The building output has one choice, `obj` (default) or `geojson`. With
`geojson` there is no `geometry.obj` and the buildings are footprints in
`site.geojson`. Trees and ground surfaces are always `site-geojson`.

`exchange.json` records both frames and the boundary hash. An importer must
reject a missing, invalid, or inconsistent frame, and must not guess the
placement when valid metadata is present.

### Reading the exchange back in

1. Read and validate `exchange.json`.
2. Resolve its relative paths inside the same directory.
3. Validate the site collection and select exactly one AOI feature.
4. Generate a new scenario ID and create an empty root scenario with the AOI.
5. Load `geometry.obj` as buildings in the declared local frame.
6. Load the tree and ground-surface features as semantic draft data.
7. Show the combined draft, then Save once.

Two warnings for an API caller:

- **Do not send `parent_scenario_id`.** A parent ID starts the clone path, which
  copies the source artifacts and results.
- The source project and scenario IDs are provenance only. They do not authorise
  an overwrite and they are not target IDs.

Manual use is valid: create an empty scenario, select `geometry.obj` and
`site.geojson`, and place them by hand. With a valid `exchange.json` the
importer uses its frame and does not ask.

Version 1 covers OBJ meshes and GeoJSON features. GLB, 3DM, IFC, Shapefile,
GeoParquet, 3D tree archetypes, and automatic result import are out of scope.

## Project bundle import

A project backup returns through the bundle-import routes. The browser opens a
session, uploads each item (one PUT for a small item, multipart for a large
one), then commits. The session writes into a hidden staging project that the
normal read and write routes cannot see until the commit publishes it. A failed
commit stays hidden and can replay safely.

**This is a restore path, not an exchange path.** Do not use it to bring in
geometry from another application — use the file upload for that.

## Pitfalls

- **The export does not lock the project.** The catalog is read once, after you
  select Download ZIP. Later edits are not in the archive. Start a new download
  when you need newer state.
- **The exchange never replaces the source scenario.** Reading it back creates a
  new one.
- **Results come out but do not go back in.** There is no automatic result
  import.

## See also

- [platform-byo-upload.md](platform-byo-upload.md) — the upload contract.
- [interpretation/grid-conventions.md](interpretation/grid-conventions.md) —
  reading exported result grids.
