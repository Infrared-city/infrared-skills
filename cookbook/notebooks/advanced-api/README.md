# Infrared SDK — Advanced API Demo Notebooks

Eight runnable Jupyter notebooks that drive Infrared's **advanced**
simulation inputs by hand-building the async JSON payload and POSTing it to
the **same** async endpoints the SDK uses.

> Since infrared-sdk 0.4.12 the facade/roof/sensor, terrain, and context fields are natively typed on the SDK models (see the top-level `11_facade_and_terrain.ipynb` / `12_surface_results_rendering.ipynb`); these notebooks remain useful for the still-direct-API-only knobs — `partial-cells`, `min-coverage`, `physics:"advanced"`, `canopy-transmissivity` — and as wire-contract reference.

These complement the top-level `public-demos/` notebooks (standard SDK path):
here we drive the inputs directly on the wire — including the physics
knobs the typed models don't carry.

## What "advanced" adds

| Field (wire, kebab-case) | Models | What it does |
| --- | --- | --- |
| `analysis-surfaces` (`facades`/`roofs`/`all`) | SR, DA, DSH, SVF | synthesize a UV sensor grid on building facades / roofs |
| `surface-grid-size`, `surface-offset` | SR, DA, DSH, SVF | cell pitch / lift-off of the synthesized grid |
| `partial-cells`, `min-coverage` | SR, DA, DSH, SVF | clip boundary cells to the surface outline; prune slivers |
| `sensor-points`, `sensor-normals` | SR, DA, DSH, SVF | bring-your-own measurement locations (flat output) |
| `ground-geometry` | all (incl. UTCI/TCS) | terrain mesh — occluder on sensor paths, drape on the grid |
| `context-geometry` | SR, DA, DSH, SVF | occluder-only geometry (shadows in, no sensors) |
| `physics:"advanced"`, `canopy-transmissivity` | UTCI | hourly time-stepping thermal tier + canopy ray-march |
| multi-month / annual `time-period` | SR, DA, DSH, UTCI, TCS | windows beyond a single month |

## The notebooks

| # | Notebook | Covers |
| --- | --- | --- |
| 0 | `00_setup.ipynb` | auth, base URL, the shared helper modules, the wire contract |
| 1 | `01_solar_radiation_advanced.ipynb` | facade / roof synthesis, partial cells, BYO sensor points; result payload + colored-mesh render |
| 2 | `02_daylight_availability_advanced.ipynb` | facade daylight sensors |
| 3 | `03_direct_sun_hours_advanced.ipynb` | facade sun-hours **+ multi-month window** |
| 4 | `04_sky_view_factors_advanced.ipynb` | facade SVF (time-independent) |
| 5 | `05_thermal_comfort_utci_advanced.ipynb` | UTCI `physics:"v1"` vs `"advanced"`, the per-cell delta |
| 6 | `06_terrain_ground_geometry.ipynb` | `ground-geometry` terrain drape vs flat baseline (synthesized terrain) |
| 7 | `07_context_geometry_occluders.ipynb` | surrounding-block `context-geometry`; before/after shadowing delta |
| 8 | `08_realistic_urban_scenario.ipynb` | everything combined: target facades + context + terrain + multi-month, on SR and UTCI |

Each notebook is **self-contained**: intro → setup → standard run → advanced
run(s) → a described result payload → a render. Geometry is fetched through the
public SDK and cached under `./.cache/`, so they run cold for any SDK user.

## Setup

```bash
pip install infrared-sdk
pip install -r ../requirements.txt   # matplotlib, numpy, python-dotenv, ...
pip install jupyter nbconvert        # to execute the notebooks
```

Set your key (never hard-coded in the notebooks):

```bash
export INFRARED_API_KEY="<your key>"
```

### Base URL — pick the right one

The advanced features deploy to **staging** first, so the notebooks default to
staging. The single `INFRARED_BASE_URL` drives both the SDK client (geometry
fetch) and the hand-built async POSTs.

| Environment | `INFRARED_BASE_URL` |
| --- | --- |
| **staging** (default) | `https://api-test.infrared.city` — host root, **no** `/v2` |
| **production** | `https://api.infrared.city/v2` — everything under `/v2` |

> Getting the `/v2` wrong 404s everywhere: staging routes live at the host
> root; production routes live under `/v2`.

## The result payloads (quick reference)

* **Grid runs** (no surface fields, and `ground-geometry`-only drape):
  `{ "output": [[...512...], ...], "min-legend", "max-legend" }` — `null` cells
  are no-data.
* **`sensor-points`**: `{ "output": [v0, v1, ...], "sensor-count", ... }` — one
  value per point, **input order**.
* **`analysis-surfaces`**: `{ "surfaces": {"<uuid>/<idx>": frame}, "aggregates",
  "min-legend", "max-legend", "sensor-count" }`. Each **frame** is a planar UV
  grid `{origin, u-axis, v-axis, grid-size, nu, nv, values, cell-area,
  cell-tris, area, mean, peak}`; `values` is `nu*nv` row-major (`null` outside
  the outline). `cell-area` and `cell-tris` are **aligned 1:1 with `values`**
  (same length, `null` where `values` is `null`).

> `partial-cells` clipping is serialized on the wire (since the `cell-tris` /
> `cell-area` fields landed): every kept cell carries `cell-area` ∈ (0, 1] (its
> in-surface area fraction) and `cell-tris` — the cell's exact clipped footprint
> as a flat `[x, y, z, …]` world-coord triangle list (`len % 9 == 0`). So you
> render each cell straight from its clipped polygon — boundary cells are real
> polygons, not full squares. Helper: `ir_advanced.reconstruct_cells` (returns
> a colored triangle soup; falls back to the grid quad for any cell missing
> tris, treating `origin` as the cell-(0,0) centre and iterating in wire order
> `k = iv*nu + iu`).

## Helper modules (committed alongside the notebooks)

* `ir_advanced.py` — client/auth, geometry fetch+cache, the async wire contract
  (`submit` → `wait` → `fetch_results`, combined as `run_job`), and
  `reconstruct_cells()` (cell-tris → world-space colored triangle soup).
* `ir_render.py` — `surface_mesh()` (Lambert-shaded colored cell mesh on the
  building geometry in 3D, edges off), `grid_heatmap()`, `terrain_3d()`,
  `footprints_2d()`.
* `ir_terrain.py` — synthesize an illustrative terrain mesh (the SDK has no DEM
  fetch).
* `ir_context.py` — split a larger building fetch into target vs context.
* `_build_notebooks.py` — regenerates the `.ipynb` files (reproducibility; not
  needed to run them).

## Caveats

* `partial-cells`, `min-coverage`, `physics:"advanced"` and
  `canopy-transmissivity` are **direct-API today** — not on the SDK's typed
  models. The facade/sensor/terrain/context fields shown here ARE typed on
  the SDK since 0.4.12; the wire contract is identical either way.
* `context-geometry` on **advanced/detail UTCI** just merged (PR #119) but is
  not live until the next staging re-deploy. For context occlusion on a thermal
  run today, use `physics:"v1"`.
* The terrain in notebook `06`/`08` is **synthesized** ("illustrative") — swap
  in a real DEM re-projected to the tile-local meter frame for a production
  study.
