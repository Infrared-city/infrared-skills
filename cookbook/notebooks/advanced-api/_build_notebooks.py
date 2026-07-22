"""Generate the advanced-API demo notebooks (.ipynb) with nbformat.

This is a *build tool*, not part of the shipped demos. It writes one notebook
per model + the realistic scenarios. Run, then execute with nbconvert.
Kept in the folder for reproducibility; safe to ignore as a user.
"""

from __future__ import annotations

import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
from pathlib import Path

HERE = Path(__file__).resolve().parent


def nb(cells):
    n = new_notebook()
    n.cells = cells
    n.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    }
    return n


def md(s):
    return new_markdown_cell(s.strip("\n"))


def code(s):
    return new_code_cell(s.strip("\n"))


# Shared setup cell used by every notebook (self-contained).
SETUP = """
# --- Setup: auth, base URL, geometry (self-contained) -----------------------
# Set your key in the environment first:  export INFRARED_API_KEY=...
# Optionally load a .env file (pip install python-dotenv):
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
# Default base URL = STAGING (host root, NO /v2) where advanced features deploy
# first. For production set INFRARED_BASE_URL=https://api.infrared.city/v2
os.environ.setdefault("INFRARED_BASE_URL", "https://api-test.infrared.city")

import matplotlib
import numpy as np
import ir_advanced as ia
import ir_render as ir

print("base URL :", ia.base_url())
client = ia.make_client()
buildings = ia.fetch_buildings(client, ia.VIENNA_KARLSPLATZ, "karlsplatz_buildings.json")
print(f"buildings: {len(buildings)} (Vienna Karlsplatz AOI, fetched via SDK + cached)")
""".strip("\n")


WEATHER = """
# Weather: nearest TMY file to the AOI, filtered to the analysis window.
from infrared_sdk.models import TimePeriod, Location
weather_id = ia.fetch_weather_identifier(client)
print("weather file:", weather_id)
""".strip("\n")


# ===========================================================================
# 00 - setup / shared helpers
# ===========================================================================


def build_00():
    return nb(
        [
            md("""
# 00 - Setup & Shared Helpers for the Advanced API

This folder demonstrates Infrared's **advanced** simulation inputs on the
raw wire. Since infrared-sdk 0.4.12 the facade/sensor/terrain/context fields
are natively typed on the SDK models; only `partial-cells`, `min-coverage`,
`physics:"advanced"` and `canopy-transmissivity` remain direct-API-only.
Payloads here are hand-built and POSTed to the
*same* async endpoints the SDK uses.

**What "advanced" adds**

| Field | Models | What it does |
|---|---|---|
| `analysis-surfaces` (`facades`/`roofs`/`all`) | SR, DA, DSH, SVF | synthesize a UV sensor grid on building facades / roofs |
| `sensor-points` / `sensor-normals` | SR, DA, DSH, SVF | bring-your-own measurement locations |
| `ground-geometry` | all (incl. UTCI/TCS) | terrain mesh - occluder on sensor paths, drape on the grid |
| `context-geometry` | SR, DA, DSH, SVF | occluder-only geometry (shadows in, no sensors) |
| `physics:"advanced"` | UTCI | hourly time-stepping thermal tier + canopy ray-march |
| multi-month / annual `time-period` | SR, DA, DSH, UTCI, TCS | windows beyond a single month |

**This notebook** just shows the shared helper modules every other notebook
imports. Read it once, then jump to a per-model notebook.
"""),
            md("""
## Configuration (environment variables - never hard-coded)

* `INFRARED_API_KEY` - your key. Request access at <https://infrared.city>.
* `INFRARED_BASE_URL` - optional. Defaults to **staging**
  `https://api-test.infrared.city` (host root, **no** `/v2`), where the
  advanced features are deployed first.
  For **production** set `https://api.infrared.city/v2` (everything under `/v2`).

> The single base URL drives both the SDK client (geometry fetch) and the
> hand-built async POSTs. Get the `/v2` right for your environment (staging =
> no `/v2`, prod = `/v2`); the wrong one 404s everywhere.
"""),
            code(SETUP),
            md("""
## The two helper modules

* **`ir_advanced.py`** - client/auth, geometry fetch+cache (relative to this
  folder), the direct-API wire contract (`submit -> wait -> fetch_results`,
  combined as `run_job`), and `reconstruct_cells()` which turns an
  `analysis-surfaces` result into a world-space colored triangle soup (one
  clipped `cell-tris` footprint per kept cell).
* **`ir_render.py`** - `surface_mesh()` (Lambert-shaded colored cell mesh on the
  building geometry in 3D), `grid_heatmap()` (2D heatmap for the 512x512 grid
  models), `terrain_3d()`, and `footprints_2d()` (plan view).

Everything is self-contained: geometry is fetched through the public SDK and
cached under `./.cache/`, so these notebooks run cold for any SDK user.
"""),
            code("""
# Quick tour of what's available.
print("ir_advanced:", [x for x in dir(ia) if not x.startswith("_") and x[0].islower()])
print()
print("ir_render  :", [x for x in dir(ir) if not x.startswith("_") and x[0].islower()])
print()
print("AOI polygon (Vienna Karlsplatz):")
print(ia.VIENNA_KARLSPLATZ["coordinates"][0])
w, h = ia.aoi_bounds_local(ia.VIENNA_KARLSPLATZ)
print(f"AOI local extent ~ {w:.0f} m (E-W) x {h:.0f} m (S-N)")
"""),
            md("""
## The async wire contract (what `run_job` does under the hood)

```
submit  : POST {base}/async/{type}    body = zip(payload.json)  -> 202 {jobId}
wait    : GET  {base}/async/jobs/{id}                            -> {jobStatus}
results : GET  {base}/async/jobs/{id}/results  -> presigned URL in Link header
download: GET  <presigned>             -> zip / gzip / raw JSON of the result
```

The advanced fields ride **alongside** the normal model request fields
(`geometries`, `vegetation`, `ground-materials`, weather arrays,
`time-period`, `latitude`, `longitude`). A payload with none of them is the
unchanged grid request. All advanced fields are **kebab-case** on the wire.

Next: open `01_solar_radiation_advanced.ipynb`.
"""),
        ]
    )


# ===========================================================================
# 01 - solar radiation (advanced surfaces)
# ===========================================================================


def build_01():
    return nb(
        [
            md("""
# 01 - Solar Radiation: Advanced Surface Sensors

**What it computes.** Cumulative shortwave solar irradiation (kWh/m2) over a
time window, accounting for building/terrain shadowing. The standard model
returns a 512x512 ground grid; the **advanced** surface mode instead
synthesizes a sensor grid directly on building **facades** and **roofs** -
the surfaces that actually drive PV yield, overheating and daylight.

**Advanced inputs gained**

* `analysis-surfaces`: `"facades"` | `"roofs"` | `"all"` - auto-synthesize a
  UV sensor grid on the matching triangles of every mesh in `geometries`.
* `surface-grid-size` (m, default 2.0) - cell pitch. `surface-offset` (m,
  default 0.1) - lift off the surface to avoid self-shadowing.
* `partial-cells` (default true) + `min-coverage` - clip boundary cells to
  the surface outline and prune thin slivers.
* `sensor-points` / `sensor-normals` - bring-your-own measurement locations.

**When to use.** Facade PV siting, building-envelope solar gains, roof PV
potential - anywhere you need irradiance *on the building*, not on the street.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Standard run (baseline grid)

First the ordinary 512x512 ground grid - no advanced fields. We build the
request with the SDK's own model so the weather arrays are correct, then POST
it through the direct-API helper (the advanced runs reuse the same body).
"""),
            code('''
from infrared_sdk.analyses.types import (
    SolarRadiationModelRequest, BaseAnalysisPayload, AnalysesName)

# Summer afternoon window (single day) for a fast baseline.
tp = TimePeriod(start_month=7, start_day=15, start_hour=9,
                end_month=7, end_day=15, end_hour=17)
loc = Location(latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON)
wp = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)

def sr_body():
    """Baseline solar-radiation body with correct weather arrays + geometry."""
    b = SolarRadiationModelRequest.from_weatherfile_payload(
        BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
        loc, tp, wp).to_dict()
    b["latitude"] = ia.VIENNA_LAT
    b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    return b

grid_res, info = ia.run_job("solar-radiation", sr_body(), label="grid")
grid = np.array(grid_res["output"], dtype=float)
print("grid shape:", grid.shape, "| min/max-legend:",
      grid_res.get("min-legend"), grid_res.get("max-legend"))
'''),
            code("""
fig, ax = ir.grid_heatmap(
    grid, title="Solar Radiation - ground grid (Jul 15, 9-17h)",
    cbar_label="kWh/m2", cmap="inferno", crop=True,
    note="Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Advanced run 1 - facade sensor synthesis

Add `analysis-surfaces:"facades"`. The worker finds the near-vertical
triangles of every building and lays a UV grid on them. The result is no
longer an `output` grid - it's a **`surfaces`** map (one frame per surface
region) plus per-building `aggregates`.
"""),
            code("""
body = sr_body()
body["analysis-surfaces"] = "facades"
body["surface-grid-size"] = 4.0     # 4 m cell pitch
body["surface-offset"] = 0.1
body["partial-cells"] = True        # clip boundary cells to the outline
body["min-coverage"] = 0.25         # drop cells < 25% inside the surface

fac_res, info = ia.run_job("solar-radiation", body, label="facades")
print("frames:", len(fac_res["surfaces"]),
      "| sensors:", fac_res["sensor-count"])
"""),
            md("""
### Result payload, described

The surface response has exactly these top-level keys:
`surfaces`, `aggregates`, `min-legend`, `max-legend`, `sensor-count`
(**no** `output` grid).

* **`surfaces`** - `{ "<building-uuid>/<region-idx>": frame }`. Each **frame**
  is a planar UV grid:
  * `origin`, `u-axis`, `v-axis` - the cell-(0,0) corner and the two in-plane
    unit axes.
  * `grid-size` - cell pitch (m). `nu`, `nv` - cell counts along u / v.
  * `values` - `nu*nv` row-major (`iv` outer, `iu` inner); `null` = cell
    outside the surface outline (the worker still reports the full grid shape).
  * `cell-area`, `cell-tris` - per-cell area fraction `(0,1]` and the exact
    clipped footprint (flat world-coord triangle list), both aligned 1:1 with
    `values`.
  * `area`, `mean`, `peak` - per-frame summary.
* **`aggregates.buildings.<uuid>`** - `{area, mean, peak}` area-weighted across
  that building's frames.
* **`sensor-count`** - total non-null cells (== `min-legend`/`max-legend` span
  the colorbar).

Each frame also carries two arrays **aligned 1:1 with `values`** (same length
`nu*nv`, `null` exactly where `values` is `null`):

* **`cell-area`** - the in-surface area fraction of each kept cell, in `(0, 1]`
  (`1.0` = full cell, `< 1.0` = a boundary cell clipped by `partial-cells`).
* **`cell-tris`** - the cell's exact **clipped footprint** as a flat
  `[x, y, z, ...]` triangle list in world coordinates (`len % 9 == 0`).

So you do not need any index math: render each cell straight from its
`cell-tris` polygon. `reconstruct_cells()` does exactly that, returning a
colored triangle soup `(tris, values, normals)` ready for a 3D mesh. (For a
cell missing tris it falls back to the full grid quad, treating `origin` as the
cell-(0,0) **centre** and iterating `values` in wire order `k = iv*nu + iu`.)

> `partial-cells` clipping is reflected directly on the wire now (since the
> `cell-tris` / `cell-area` serialization landed): boundary cells come back as
> real clipped polygons, not full squares, so the mesh render has smooth edges.
"""),
            code("""
import json
# Pretty-print one frame (arrays trimmed) + this building's aggregate.
fk = next(iter(fac_res["surfaces"]))
frame = fac_res["surfaces"][fk]
print("frame key:", fk)
_trim = {"values", "cell-area", "cell-tris"}
print(json.dumps({k: (v[:6] + ["...(%d total)" % len(v)] if k in _trim else v)
                  for k, v in frame.items()}, indent=2, default=float))
bid = fk.split("/")[0]
print("\\naggregates for building", bid, ":",
      json.dumps(fac_res["aggregates"]["buildings"].get(bid, {}), default=float))
"""),
            md("""
## Render - colored surface mesh on the building geometry

Render every kept cell from its exact `cell-tris` clipped footprint as a
Lambert-shaded colored triangle mesh (edges off) over a faint building context.
This is the headline view: real per-facade irradiance with smooth boundary
cells, not a scatter cloud or blocky squares.
"""),
            code("""
tris, values, normals = ia.reconstruct_cells(fac_res["surfaces"])
faces = ia.building_faces(buildings)
fig, ax = ir.surface_mesh(
    tris, values, normals=normals, context_faces=faces,
    title="Facade Solar Irradiance - colored sensor mesh",
    cbar_label="kWh/m2 (per cell)", cmap="inferno", zmax=45,
    note=f"{fac_res['sensor-count']:,} facade sensors | Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Advanced run 2 - roofs + facades together (`analysis-surfaces:"all"`)

`"all"` synthesizes on **both** facades and roof caps, so the buildings render
as closed, colored solids rather than open-topped shells.
"""),
            code("""
body = sr_body()
body["analysis-surfaces"] = "all"
body["surface-grid-size"] = 4.0
body["surface-offset"] = 0.1
body["partial-cells"] = True
body["min-coverage"] = 0.25
roof_res, info = ia.run_job("solar-radiation", body, label="all")
rt, rv, rn = ia.reconstruct_cells(roof_res["surfaces"])
fig, ax = ir.surface_mesh(
    rt, rv, normals=rn, context_faces=ia.building_faces(buildings),
    title="Facade + Roof Solar Irradiance - colored sensor mesh",
    cbar_label="kWh/m2 (per cell)", cmap="inferno", zmax=45, elev=42,
    note=f"{roof_res['sensor-count']:,} surface sensors (facades + roofs) | Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Advanced run 3 - bring-your-own sensor points

Instead of synthesizing a grid, send explicit `sensor-points` (tile-local
meters) and optional `sensor-normals`. The result is a **flat** `output` list,
one value per point, in input order, plus `sensor-count`.
"""),
            code("""
# A vertical mast of points at the AOI centre, 2 m -> 40 m.
mast = [[160.0, 230.0, z] for z in range(2, 42, 2)]
body = sr_body()
body["sensor-points"] = mast
body["sensor-normals"] = [[0.0, -1.0, 0.0]] * len(mast)   # facing south
byo_res, info = ia.run_job("solar-radiation", body, label="sensor-points")
print("keys:", sorted(byo_res), "| sensor-count:", byo_res["sensor-count"])
print("per-point kWh/m2 (z = 2..40 m):")
for (x, y, z), val in zip(mast, byo_res["output"]):
    print(f"  z={z:2d} m : {val:.3f}")
"""),
            md("""
## Summary

* **Standard**: 512x512 ground grid (`output`).
* **`analysis-surfaces`**: per-facade / per-roof colored mesh (`surfaces` +
  `aggregates`), reconstructed with the frame `origin/u/v/grid-size`.
* **`sensor-points`**: flat per-point values in input order.

Only `partial-cells`, `min-coverage`, `physics:"advanced"` and `canopy-transmissivity` are direct-API today; facade/sensor/terrain/context are typed on the SDK since 0.4.12. The
same pattern works for daylight (`02`), direct-sun-hours (`03`) and SVF (`04`).
"""),
        ]
    )


# ===========================================================================
# 02 - daylight availability
# ===========================================================================


def build_02():
    return nb(
        [
            md("""
# 02 - Daylight Availability: Advanced Surface Sensors

**What it computes.** The fraction / hours of the analysis window for which a
point receives useful daylight, given building and terrain shadowing. The
standard model returns a 512x512 ground grid; the **advanced** surface mode
puts daylight sensors on building **facades** - the input to facade daylight
factor, glare and window-placement studies.

**Advanced inputs gained** (same surface family as solar radiation):
`analysis-surfaces` (`facades` since 2026-06-13), `surface-grid-size`,
`surface-offset`, `partial-cells` / `min-coverage`, `sensor-points`,
`ground-geometry`, `context-geometry`, and multi-month windows.

**When to use.** Facade daylight access across a block, balcony / window
daylight, courtyard quality - where you need daylight *on the building*.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Standard run (baseline grid)

Daylight availability is built straight from a `time-period` + location (no
weather arrays needed). We POST the SDK-built body through the direct-API
helper so the advanced runs can reuse it.
"""),
            code("""
from infrared_sdk.analyses.types import SolarModelRequest, AnalysesName

tp = TimePeriod(start_month=7, start_day=15, start_hour=9,
                end_month=7, end_day=15, end_hour=17)

def da_body():
    b = SolarModelRequest(analysis_type=AnalysesName.daylight_availability,
                          latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON,
                          time_period=tp).to_dict()
    b["latitude"] = ia.VIENNA_LAT
    b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    return b

grid_res, info = ia.run_job("daylight-availability", da_body(), label="grid")
grid = np.array(grid_res["output"], dtype=float)
print("grid shape:", grid.shape)
"""),
            code("""
fig, ax = ir.grid_heatmap(
    grid, title="Daylight Availability - ground grid", cbar_label="daylight (hours)",
    cmap="cividis", crop=True, note="Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Advanced run - facade daylight sensors

`analysis-surfaces:"facades"` with partial-cell clipping. The result is the
same `surfaces` / `aggregates` / `sensor-count` shape described in notebook
`01` - one frame per facade region, `values` row-major over `nu*nv`.
"""),
            code("""
body = da_body()
body["analysis-surfaces"] = "facades"
body["surface-grid-size"] = 4.0
body["surface-offset"] = 0.1
body["partial-cells"] = True
body["min-coverage"] = 0.25
fac_res, info = ia.run_job("daylight-availability", body, label="facades")
print("frames:", len(fac_res["surfaces"]), "| sensors:", fac_res["sensor-count"])
"""),
            md("""
### Result payload, described

Identical structure to solar radiation (see `01`):

* `surfaces["<uuid>/<idx>"]` -> `{origin, u-axis, v-axis, grid-size, nu, nv,
  values, cell-area, cell-tris, area, mean, peak}`; `values` is `nu*nv`
  row-major, `null` outside; `cell-tris` / `cell-area` aligned 1:1 with it.
* `aggregates.buildings.<uuid>` -> `{area, mean, peak}`.
* `min-legend` / `max-legend` / `sensor-count`.

Only the units differ - here `values` are daylight hours / availability, not
kWh/m2. Reconstruct the world cells exactly the same way (`reconstruct_cells`).
"""),
            code("""
import json
fk = next(iter(fac_res["surfaces"]))
frame = fac_res["surfaces"][fk]
print("frame key:", fk)
print(json.dumps({k: (v if k != "values" else v[:8] + ["...(%d)" % len(v)])
                  for k, v in frame.items()}, indent=2, default=float))
"""),
            md("## Render - colored daylight mesh on the building geometry"),
            code("""
tris, values, normals = ia.reconstruct_cells(fac_res["surfaces"])
fig, ax = ir.surface_mesh(
    tris, values, normals=normals, context_faces=ia.building_faces(buildings),
    title="Facade Daylight Availability - colored sensor mesh",
    cbar_label="daylight (hours, per cell)", cmap="cividis", zmax=45,
    note=f"{fac_res['sensor-count']:,} facade sensors | Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Note - multi-month windows

Daylight (and solar / DSH / UTCI / TCS) accept **forward** multi-month and
annual windows on staging. Just widen the `TimePeriod`:

```python
tp = TimePeriod(start_month=6, start_day=1, start_hour=0,
                end_month=8, end_day=31, end_hour=23)   # Jun-Aug
```

Wrapping windows (e.g. Nov->Feb, `end-month < start-month`) are rejected with
400 - split into two forward requests. See `03` for a multi-month run.
"""),
        ]
    )


# ===========================================================================
# 03 - direct sun hours (with a multi-month window)
# ===========================================================================


def build_03():
    return nb(
        [
            md("""
# 03 - Direct Sun Hours: Advanced Surfaces + Multi-Month Window

**What it computes.** The number of hours a point is in **direct** (unshaded)
sunlight over the window - the metric behind right-to-light / overshadowing
checks and amenity-space sunlight rules. Standard = 512x512 ground grid;
**advanced** = direct-sun-hours on building **facades** and **roofs**.

**Advanced inputs gained.** The full surface family (`analysis-surfaces`,
`surface-grid-size`, `partial-cells`, `sensor-points`, `ground-geometry`,
`context-geometry`) **plus** forward **multi-month / annual** `time-period`
windows - aggregated as per-month representative days.

**When to use.** Facade / roof solar-access compliance, overshadowing studies,
seasonal sunlight on amenity terraces.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Multi-month window

We use a **summer half-year** window (Apr-Sep) to show the advanced
`time-period`. Direct-sun-hours aggregates this as per-month representative
days, so the result is the typical direct-sun-hours profile across the season.
"""),
            code("""
from infrared_sdk.analyses.types import SolarModelRequest, AnalysesName

# Forward multi-month window (Apr 1 -> Sep 30). Wrapping windows are rejected.
tp = TimePeriod(start_month=4, start_day=1, start_hour=4,
                end_month=9, end_day=30, end_hour=20)

def dsh_body():
    b = SolarModelRequest(analysis_type=AnalysesName.direct_sun_hours,
                          latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON,
                          time_period=tp).to_dict()
    b["latitude"] = ia.VIENNA_LAT
    b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    return b

grid_res, info = ia.run_job("direct-sun-hours", dsh_body(), label="grid-multimonth")
grid = np.array(grid_res["output"], dtype=float)
print("grid shape:", grid.shape, "| elapsed:", info["elapsed_s"], "s")
"""),
            code("""
fig, ax = ir.grid_heatmap(
    grid, title="Direct Sun Hours - ground grid (Apr-Sep representative days)",
    cbar_label="direct sun (hours)", cmap="magma", crop=True,
    note="Vienna Karlsplatz, multi-month, staging")
fig
"""),
            md("""
## Advanced run - facade direct-sun-hours

`analysis-surfaces:"facades"`. Same `surfaces` payload shape as `01`/`02`.
South / west facades pick up the most direct sun; the colored mesh makes the
orientation dependence obvious.
"""),
            code("""
body = dsh_body()
body["analysis-surfaces"] = "facades"
body["surface-grid-size"] = 4.0
body["surface-offset"] = 0.1
body["partial-cells"] = True
body["min-coverage"] = 0.25
fac_res, info = ia.run_job("direct-sun-hours", body, label="facades")
print("frames:", len(fac_res["surfaces"]), "| sensors:", fac_res["sensor-count"])
"""),
            md("""
### Result payload, described

Same surface schema as solar radiation / daylight (notebook `01`): per-frame
`{origin, u-axis, v-axis, grid-size, nu, nv, values, area, mean, peak}`,
per-building `aggregates`, and `sensor-count`. `values` here are **direct sun
hours** (representative-day average across the multi-month window).
"""),
            code("""
import json
fk = next(iter(fac_res["surfaces"]))
print("frame", fk, "->", json.dumps(
    {k: fac_res["surfaces"][fk][k] for k in
     ("grid-size", "nu", "nv", "area", "mean", "peak")}, default=float))
print("AOI-wide sensor-count:", fac_res["sensor-count"],
      "| legend:", fac_res["min-legend"], "->", fac_res["max-legend"])
"""),
            md("## Render - colored direct-sun-hours mesh"),
            code("""
tris, values, normals = ia.reconstruct_cells(fac_res["surfaces"])
fig, ax = ir.surface_mesh(
    tris, values, normals=normals, context_faces=ia.building_faces(buildings),
    title="Facade Direct Sun Hours - colored sensor mesh (Apr-Sep)",
    cbar_label="direct sun (hours, per cell)", cmap="magma", zmax=45,
    note=f"{fac_res['sensor-count']:,} facade sensors | multi-month | staging")
fig
"""),
            md("""
## Summary

* Forward multi-month / annual windows are accepted (wrapping windows -> 400).
* DSH aggregates the window as per-month representative days.
* The surface mode + payload shape is identical to solar radiation / daylight.
"""),
        ]
    )


# ===========================================================================
# 04 - sky view factors (time-independent)
# ===========================================================================


def build_04():
    return nb(
        [
            md("""
# 04 - Sky View Factors: Advanced Surface Sensors

**What it computes.** The Sky View Factor (SVF) - the share of the sky hemi-
sphere visible from a point, **reported on a 0-100 scale** (0 = fully enclosed,
100 = fully open sky). It is **time-independent** (pure geometry), so there is
no `time-period` and no weather. SVF drives longwave cooling at night and is a
core input to thermal comfort. Standard = 512x512 ground grid; **advanced** =
SVF on building **facades** / roofs.

**Advanced inputs gained.** `analysis-surfaces`, `surface-grid-size`,
`partial-cells`, `sensor-points`, `ground-geometry`, `context-geometry`. (No
time window - SVF is geometric.)

**When to use.** Facade longwave exposure, urban canyon enclosure, night-time
cooling potential per facade.
"""),
            md("## Setup"),
            code(SETUP),
            md("""
## Standard run (baseline grid)

SVF needs nothing but geometry - no weather, no time period.
"""),
            code("""
from infrared_sdk.analyses.types import SvfModelRequest, AnalysesName

def svf_body():
    b = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors).to_dict()
    b["latitude"] = ia.VIENNA_LAT
    b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    return b

grid_res, info = ia.run_job("sky-view-factors", svf_body(), label="grid")
grid = np.array(grid_res["output"], dtype=float)
print("grid shape:", grid.shape, "| SVF range:",
      round(float(np.nanmin(grid)), 1), "->", round(float(np.nanmax(grid)), 1),
      "| legend:", grid_res.get("min-legend"), "->", grid_res.get("max-legend"))
"""),
            code("""
# SVF is reported on a 0-100 scale (not 0-1). Fix vmin/vmax so the variation
# shows instead of saturating; the legend confirms 0 -> 100.
fig, ax = ir.grid_heatmap(
    grid, title="Sky View Factor - ground grid", cbar_label="SVF (%)",
    cmap="bone", crop=True, vmin=0, vmax=100, note="Vienna Karlsplatz, staging")
fig
"""),
            md("""
## Advanced run - facade SVF sensors

`analysis-surfaces:"facades"`. Facade SVF is lower in narrow canyons and
higher on tall exposed elevations - exactly what the colored mesh shows.
"""),
            code("""
body = svf_body()
body["analysis-surfaces"] = "facades"
body["surface-grid-size"] = 4.0
body["surface-offset"] = 0.1
body["partial-cells"] = True
body["min-coverage"] = 0.25
fac_res, info = ia.run_job("sky-view-factors", body, label="facades")
print("frames:", len(fac_res["surfaces"]), "| sensors:", fac_res["sensor-count"])
"""),
            md("""
### Result payload, described

Same surface schema as the solar models (notebook `01`): per-frame
`{origin, u-axis, v-axis, grid-size, nu, nv, values, cell-area, cell-tris,
area, mean, peak}` + `aggregates` + `sensor-count`. `values` are **SVF on the
0-100 scale** (legend `min-legend`/`max-legend` = `0`/`100`). Because SVF is
time-independent the *same* facade frames would come back for any season - only
the geometry matters.
"""),
            code("""
import json
fk = next(iter(fac_res["surfaces"]))
print("frame", fk, "->", json.dumps(
    {k: fac_res["surfaces"][fk][k] for k in
     ("grid-size", "nu", "nv", "mean", "peak")}, default=float))
bid = fk.split("/")[0]
print("building", bid, "aggregate:",
      json.dumps(fac_res["aggregates"]["buildings"].get(bid, {}), default=float))
"""),
            md("## Render - colored SVF mesh on the building geometry"),
            code("""
tris, values, normals = ia.reconstruct_cells(fac_res["surfaces"])
# SVF is 0-100; fix the scale so canyon vs exposed facades separate clearly.
fig, ax = ir.surface_mesh(
    tris, values, normals=normals, context_faces=ia.building_faces(buildings),
    title="Facade Sky View Factor - colored sensor mesh",
    cbar_label="SVF (%, per cell)", cmap="bone", zmax=45, vmin=0, vmax=100,
    note=f"{fac_res['sensor-count']:,} facade sensors | Vienna Karlsplatz, staging")
fig
"""),
        ]
    )


# ===========================================================================
# 05 - thermal comfort UTCI (physics v1 vs advanced + multi-month)
# ===========================================================================


def build_05():
    return nb(
        [
            md("""
# 05 - Thermal Comfort (UTCI): v1 vs `physics:"advanced"`

**What it computes.** The Universal Thermal Climate Index - the felt ("real-
feel") outdoor temperature combining air temperature, humidity, wind and mean
radiant temperature (sun, sky and surface radiation). Output is a 512x512
grid of degC. This is the headline pedestrian-comfort metric.

**Advanced inputs gained.** Thermal models do **not** take the surface-sensor
fields - they run the terrain-aware **grid** path only. What UTCI gains:

* `physics`: `"v1"` (default) | `"detail"` | `"advanced"`.
  * **v1** - absolute per-cell UTCI (Broede polynomial on a coarse-grid MRT).
  * **advanced** - hourly time-stepping, SOLWEIG-form surface-temperature
    phase lag, UTCI evaluated *every hour then averaged* (UTCI is nonlinear in
    MRT), with the **canopy ray-march on by default**.
* `canopy-transmissivity` (global psi, [0,1], default 0.40) - shortwave
  transmissivity for the advanced canopy ray-march; per-tree override via
  `transmissivity` on each `vegetation` entry.
* `ground-geometry` - terrain drape (accepted on thermal models).
* forward **multi-month / annual** `time-period`.

**When to use.** `advanced` when you care about canopy shade, surface-
temperature lag and realistic MRT (the things that move comfort by several
degrees); v1 for a fast first pass.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Build the UTCI body (full weather array set)

UTCI needs the full weather set: horizontal-infrared, DHI, DNI, GHI, dry-bulb,
relative humidity and wind speed. The SDK's `from_weatherfile_payload`
assembles them; we then add geometry, vegetation and ground materials.
"""),
            code("""
from infrared_sdk.analyses.types import UtciModelRequest, AnalysesName

# Vegetation + ground materials sharpen the advanced canopy / surface physics.
vegetation = ia.fetch_vegetation(client, ia.VIENNA_KARLSPLATZ, "karlsplatz_veg.json")
ground = ia.fetch_ground_materials(client, ia.VIENNA_KARLSPLATZ, "karlsplatz_ground.json")
print(f"vegetation features: {len(vegetation)} | ground layers: {list(ground)}")

# Hot summer afternoon - where advanced physics diverges most from v1.
tp = TimePeriod(start_month=7, start_day=15, start_hour=12,
                end_month=7, end_day=15, end_hour=16)
loc = Location(latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON)
wp = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)

def utci_body(extra=None):
    b = UtciModelRequest.from_weatherfile_payload(
        UtciModelRequest(analysis_type=AnalysesName.thermal_comfort_index,
                         latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON,
                         time_period=tp), loc, tp, wp).to_dict()
    b["latitude"] = ia.VIENNA_LAT
    b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    if vegetation:
        b["vegetation"] = vegetation
    if ground:
        b["ground-materials"] = ground
    if extra:
        b.update(extra)
    return b
"""),
            md("""
## Standard run - `physics:"v1"` (default)

No `physics` field = v1. Returns the standard thermal grid (`output`,
512x512 degC).
"""),
            code("""
v1_res, info = ia.run_job("thermal-comfort-index", utci_body(), label="v1")
v1 = np.array(v1_res["output"], dtype=float)
print("v1 grid:", v1.shape, "| mean UTCI: %.2f degC" % float(np.nanmean(v1)))
fig, ax = ir.grid_heatmap(
    v1, title="UTCI v1 - felt temperature (Jul 15, 12-16h)",
    cbar_label="UTCI (degC)", cmap="turbo", crop=True, note="Vienna, staging")
fig
"""),
            md("""
## Advanced run - `physics:"advanced"`

Add `physics:"advanced"` (and optionally `canopy-transmissivity`). Same grid
shape, but hourly-stepped with canopy ray-march and surface-temperature lag.
"""),
            code("""
adv_res, info = ia.run_job(
    "thermal-comfort-index",
    utci_body(extra={"physics": "advanced", "canopy-transmissivity": 0.40}),
    label="advanced")
adv = np.array(adv_res["output"], dtype=float)
print("advanced grid:", adv.shape, "| mean UTCI: %.2f degC" % float(np.nanmean(adv)))
fig, ax = ir.grid_heatmap(
    adv, title="UTCI advanced (physics=advanced, canopy 0.40)",
    cbar_label="UTCI (degC)", cmap="turbo", crop=True, note="Vienna, staging")
fig
"""),
            md("""
### Result payload, described

UTCI uses the **standard grid** shape (not surfaces):

```json
{ "output": [[...512...], ... 512 rows ...],   // null = no-data cell, degC
  "min-legend": <num|null>, "max-legend": <num|null> }
```

* **`output`** - 512x512 row-major grid of felt temperature in degC; `null`
  outside the data mask. Read it like any grid result (`np.array(...)`).
* **`min-legend` / `max-legend`** - suggested colorbar bounds (often `null`;
  compute your own from the finite values).

`advanced` is grid-shaped identically to v1, so the **delta** below is a clean
per-cell subtraction.
"""),
            code("""
import json
print("result keys:", sorted(adv_res))
print("legend:", adv_res.get("min-legend"), "->", adv_res.get("max-legend"))
print("sample row 256, cols 250-256:",
      json.dumps([None if not np.isfinite(x) else round(float(x), 2)
                  for x in adv[256, 250:256]]))
"""),
            md("""
## The money shot - advanced minus v1

Where does advanced physics change the felt temperature? Canopy shade and
surface-temperature lag can shift individual cells by several degrees even when
the mean barely moves.
"""),
            code("""
delta = adv - v1
d = delta[np.isfinite(delta)]
print("v1 -> advanced:  mean dUTCI = %+.2f degC | mean|d| = %.2f | max|d| = %.2f (over %d cells)"
      % (float(np.nanmean(d)), float(np.nanmean(np.abs(d))),
         float(np.nanmax(np.abs(d))), d.size))
fig, ax = ir.grid_heatmap(
    delta, title="UTCI delta: advanced - v1", cbar_label="dUTCI (degC)",
    cmap="RdBu_r", diverging=True, crop=True,
    note="blue = advanced cooler, red = warmer")
fig
"""),
            md("""
## Notes

* Thermal models reject the surface-sensor fields (`analysis-surfaces`,
  `sensor-points`, `context-geometry`) with HTTP 400 - they cover the
  grid + `ground-geometry` path only (see notebook `06` for terrain).
* Forward multi-month / annual windows work on UTCI too (advanced uses
  representative-day clustering). Widen `tp` to e.g. Jun-Aug for a seasonal
  comfort grid.
* `context-geometry` on advanced/detail UTCI just merged (PR #119) but is
  **not live** until the next staging re-deploy - until then use `physics:"v1"`
  if you need context occlusion on a thermal run (see notebook `07`).
"""),
        ]
    )


# ===========================================================================
# 06 - terrain via ground-geometry
# ===========================================================================


def build_06():
    return nb(
        [
            md("""
# 06 - Terrain: the `ground-geometry` Input

**What it adds.** `ground-geometry` is a terrain triangle mesh
(`{id: {coordinates, indices}}`, tile-local meters) that the worker uses as:

* an **occluder** on the sensor paths (facade / sensor-point runs), and
* the **drape target** on the 512x512 grid path - the flat ground plane is
  replaced by your terrain, so the grid follows the relief.

It is accepted on **all** raytraced models **and** the thermal models
(UTCI / TCS), making terrain a first-class spatial input.

**No DEM in the SDK.** The SDK does not fetch elevation, so this notebook
**synthesizes an illustrative terrain** (a gentle tilt + low-frequency bumps)
over the AOI bbox via `ir_terrain.generate_terrain`. Clearly labelled - drop
in a real re-projected DEM for a production study.

**When to use.** Sloped sites, valleys / hillsides, anywhere the ground is not
flat - terrain changes both shadowing and which cells are sunlit.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Generate an illustrative terrain mesh

A 512 m square mesh with a gentle SW->NE tilt and a couple of low-frequency
bumps - a few metres of relief across the tile. This is **synthetic** terrain
for demonstration, not a survey of Vienna.
"""),
            code("""
import ir_terrain
terrain_mesh, heights = ir_terrain.generate_terrain(
    size_m=512.0, n=44, slope=(0.035, 0.02),
    bumps=((2.5, 6.0), (1.5, 3.5)))
print("terrain triangles:", len(terrain_mesh["terrain0"]["indices"]) // 3)
print("relief: %.1f -> %.1f m" % (float(heights.min()), float(heights.max())))

fig, ax = ir.terrain_3d(
    heights, size_m=512.0, context_faces=ia.building_faces(buildings),
    title="Illustrative terrain over the AOI (with buildings)",
    note="Vienna Karlsplatz | synthetic terrain for demonstration")
fig
"""),
            md("""
## Baseline (flat) vs terrain-draped solar radiation grid

Run solar radiation twice: once flat (no `ground-geometry`), once with the
terrain as the drape target. On the grid path the result is the standard
512x512 `output`, but draped onto the relief - so sun-facing slopes gain
irradiance and shaded slopes lose it.
"""),
            code("""
from infrared_sdk.analyses.types import (
    SolarRadiationModelRequest, BaseAnalysisPayload, AnalysesName)

tp = TimePeriod(start_month=7, start_day=15, start_hour=9,
                end_month=7, end_day=15, end_hour=17)
loc = Location(latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON)
wp = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)

def sr_body():
    b = SolarRadiationModelRequest.from_weatherfile_payload(
        BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
        loc, tp, wp).to_dict()
    b["latitude"] = ia.VIENNA_LAT; b["longitude"] = ia.VIENNA_LON
    b["geometries"] = buildings
    return b

flat_res, _ = ia.run_job("solar-radiation", sr_body(), label="flat")
flat = np.array(flat_res["output"], dtype=float)

body = sr_body()
body["ground-geometry"] = terrain_mesh
terr_res, _ = ia.run_job("solar-radiation", body, label="terrain-drape")
terr = np.array(terr_res["output"], dtype=float)
print("flat mean %.1f | terrain mean %.1f kWh/m2"
      % (float(np.nanmean(flat)), float(np.nanmean(terr))))
"""),
            md("""
### Result payload, described

`ground-geometry`-only runs return the **standard grid** shape (terrain drape):

```json
{ "output": [[...512...], ...], "min-legend": <num>, "max-legend": <num> }
```

So you read it exactly like the flat grid - the difference is that each cell's
irradiance now reflects the terrain orientation under it. (On a sensor /
facade run, `ground-geometry` instead acts purely as an occluder and the
`surfaces` payload is unchanged in shape.)
"""),
            code("""
fig, ax = ir.grid_heatmap(
    flat, title="Solar Radiation - FLAT ground", cbar_label="kWh/m2",
    cmap="inferno", crop=True, note="no ground-geometry")
fig
"""),
            code("""
fig, ax = ir.grid_heatmap(
    terr, title="Solar Radiation - draped on TERRAIN", cbar_label="kWh/m2",
    cmap="inferno", crop=True, note="with ground-geometry")
fig
"""),
            md("""
## The difference - how terrain reshapes the grid

Subtract the two grids on the cells they share. Tilting the ground toward the
sun **redistributes** irradiance: south / west-facing slopes pick up more,
flatter / north-facing cells gain less. (For this gentle synthetic relief the
net effect on the shared cells is a small overall **gain** - no cell drops below
the flat baseline; with steeper terrain you would also see self-shaded slopes
fall below zero delta. Cells the terrain drape adds or removes relative to the
flat mask are simply no-data on the other grid and are left out of the
subtraction.)
"""),
            code("""
# Compare only where both grids have data; the rest is no-data on one side.
both = np.isfinite(flat) & np.isfinite(terr)
delta = np.where(both, terr - flat, np.nan)
d = delta[np.isfinite(delta)]
n_terr_only = int((np.isfinite(terr) & ~np.isfinite(flat)).sum())
n_flat_only = int((np.isfinite(flat) & ~np.isfinite(terr)).sum())
print("terrain - flat (shared cells):  mean %+.2f | max gain %+.2f | min %.2f kWh/m2 (%d cells)"
      % (float(np.nanmean(d)), float(np.nanmax(d)), float(np.nanmin(d)), d.size))
print("no-data only on flat (terrain reveals ground): %d | only on terrain: %d"
      % (n_flat_only, n_terr_only))
# Diverging scale centred at 0: red = terrain redistributes MORE sun here,
# blue would be less. For this relief the shared cells are gains (>= 0).
fig, ax = ir.grid_heatmap(
    delta, title="Solar Radiation delta: terrain - flat (shared cells)",
    cbar_label="d kWh/m2", cmap="RdBu_r", diverging=True, crop=True,
    note="red = more sun on the tilted ground; >=0 here (gentle relief, no self-shaded slopes)")
fig
"""),
            md("""
## Summary

* `ground-geometry` drapes the grid onto real relief (and occludes on sensor
  runs). It works on raytraced **and** thermal models.
* The SDK has no DEM fetch - bring your own terrain mesh (here synthesized).
  Match the tile-local meter frame of the buildings.
* Constraints: <= 500,000 triangles, >= 1 triangle (empty -> 422).
"""),
        ]
    )


# ===========================================================================
# 07 - context-geometry occluders (the money shot)
# ===========================================================================


def build_07():
    return nb(
        [
            md("""
# 07 - Context Geometry: Real Surrounding-Block Occluders

**The realistic demo.** `client.buildings.get_area(polygon)` fetches buildings
**inside** the polygon only - so a facade study on a small AOI misses the
shadows cast by the surrounding blocks. `context-geometry` fixes that: it is
geometry that **occludes** (casts shadows / blocks sky) exactly like
`geometries`, but never receives synthesized sensors and never enters the grid
mask. *"Trace everything, measure only these."*

**The recipe**

1. Fetch a **larger** polygon (a ~200 m halo around the target AOI).
2. **Split** it: buildings in the inner AOI = *target*; the rest = *context*.
3. Run facade solar radiation on the target **twice** - once without context,
   once with the surrounding blocks as `context-geometry`.
4. Look at the **before / after shadowing delta** per facade.

`context-geometry` needs a trigger (one of `analysis-surfaces`,
`sensor-points`, or `ground-geometry`) - here `analysis-surfaces` provides it.

**When to use.** Any facade / SVF / sun-hours study where the neighbours
matter (i.e. almost always in a real city).
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Fetch the larger area and split target vs context

We grow the Karlsplatz AOI by a 200 m halo, fetch all buildings in that larger
polygon (one consistent meter frame), then label each building target / context
by whether its centroid is in the inner AOI.
"""),
            code("""
import ir_context as ic

inner = ia.VIENNA_KARLSPLATZ
outer = ic.expand_polygon(inner, halo_m=200.0, ref_lat=ia.VIENNA_LAT)
big = ia.fetch_buildings(client, outer, "context_buildings.json")

rect = ic.inner_rect_local(inner, outer, ia.VIENNA_LAT)
target_ids, context_ids = ic.split_target_context(big, rect)
target = ic.subset(big, target_ids)
context = ic.subset(big, context_ids)
print(f"outer area buildings : {len(big)}")
print(f"target (inner AOI)   : {len(target)}")
print(f"context (surrounding): {len(context)}")
"""),
            md(
                "Plan view - the split. Blue = target buildings we measure; grey = context occluders."
            ),
            code("""
fig, ax = ir.footprints_2d(
    big, target_ids=target_ids,
    title="Target (blue) vs context occluders (grey)",
    note="200 m halo around Vienna Karlsplatz | context casts shadows in, gets no sensors")
fig
"""),
            md("""
## Run facade solar radiation - without vs with context

Same target buildings, same facade synthesis. The only difference is the
`context-geometry` block in the second payload.
"""),
            code("""
from infrared_sdk.analyses.types import (
    SolarRadiationModelRequest, BaseAnalysisPayload, AnalysesName)

tp = TimePeriod(start_month=7, start_day=15, start_hour=9,
                end_month=7, end_day=15, end_hour=17)
loc = Location(latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON)
wp = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)

def facade_body():
    b = SolarRadiationModelRequest.from_weatherfile_payload(
        BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
        loc, tp, wp).to_dict()
    b["latitude"] = ia.VIENNA_LAT; b["longitude"] = ia.VIENNA_LON
    b["geometries"] = target
    b["analysis-surfaces"] = "facades"
    b["surface-grid-size"] = 4.0
    b["surface-offset"] = 0.1
    return b

# WITHOUT context - target buildings shade each other, but the neighbours are invisible.
no_ctx, info_a = ia.run_job("solar-radiation", facade_body(), label="no-context")

# WITH context - the surrounding blocks now cast shadows onto the target facades.
body = facade_body()
body["context-geometry"] = context          # <-- the only change
with_ctx, info_b = ia.run_job("solar-radiation", body, label="with-context")
print("sensors (identical both runs):", no_ctx["sensor-count"], with_ctx["sensor-count"])
"""),
            md("""
### Result payload, described

Both runs return the **surface** payload of notebook `01`
(`surfaces` / `aggregates` / `sensor-count`) for the **target** buildings only
- the context never appears in the output. Because the sensor layout is
identical, we can subtract per-cell and per-building between the two runs to
isolate the **shadowing effect of the neighbours**.

`context-geometry` notes:
* it needs a trigger (here `analysis-surfaces`); on the flat grid path alone it
  is rejected with 422.
* on **advanced/detail UTCI** it just merged (PR #119) but is **not live**
  until the next staging re-deploy - use `physics:"v1"` for context on a
  thermal run until then.
"""),
            md("""
## The money shot - irradiance lost to the neighbours

Per building, how much facade irradiance did the surrounding blocks remove?
"""),
            code("""
m_no = ic.aggregate_means(no_ctx)
m_with = ic.aggregate_means(with_ctx)
common = sorted(set(m_no) & set(m_with))
deltas = np.array([m_with[b] - m_no[b] for b in common])

print("mean facade irradiance:  no-context %.3f  ->  with-context %.3f kWh/m2"
      % (float(np.mean([m_no[b] for b in common])),
         float(np.mean([m_with[b] for b in common]))))
print("context removes on average %+.3f kWh/m2 per building" % float(np.mean(deltas)))
print("most-overshadowed building loses %.3f kWh/m2" % float(np.min(deltas)))

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(9, 4))
order = np.argsort(deltas)
ax.bar(range(len(common)), deltas[order], color="#c0392b")
ax.axhline(0, color="#333", lw=0.8)
ax.set_xlabel("target building (sorted by loss)")
ax.set_ylabel("d irradiance (kWh/m2)")
ax.set_title("Facade irradiance change from surrounding-block shadows", weight="bold")
fig.tight_layout()
fig
"""),
            md("""
## Render - the same facades, with and without context

Reconstruct both as colored meshes on the **same** target geometry, on a
shared color scale, so the darkening from the neighbours is directly visible.
"""),
            code("""
t_no, v_no, n_no = ia.reconstruct_cells(no_ctx["surfaces"])
t_wi, v_wi, n_wi = ia.reconstruct_cells(with_ctx["surfaces"])
faces = ia.building_faces(target)
lo = float(np.percentile(np.concatenate([v_no, v_wi]), 2))
hi = float(np.percentile(np.concatenate([v_no, v_wi]), 98))

fig, ax = ir.surface_mesh(
    t_no, v_no, normals=n_no, context_faces=faces, vmin=lo, vmax=hi, zmax=45,
    title="Facade Solar - WITHOUT context", cbar_label="kWh/m2",
    cmap="inferno", note="target buildings only")
fig
"""),
            code("""
fig, ax = ir.surface_mesh(
    t_wi, v_wi, normals=n_wi, context_faces=faces, vmin=lo, vmax=hi, zmax=45,
    title="Facade Solar - WITH surrounding-block context", cbar_label="kWh/m2",
    cmap="inferno", note="same facades, now shaded by the neighbours")
fig
"""),
            md("""
### Per-cell difference mesh

Color each target facade cell by **how much irradiance the context removed**
(red = shaded by neighbours). This is the clearest single view of the effect.
"""),
            code("""
# Cell-triangles line up 1:1 between the two runs (identical synthesis), so
# subtract per triangle. Context can only remove irradiance, so loss >= 0.
# Plot the loss magnitude on a sequential scale: dark red = most shaded.
loss = np.clip(v_no - v_wi, 0.0, None)         # >= 0 kWh/m2 removed
fig, ax = ir.surface_mesh(
    t_wi, loss, normals=n_wi, context_faces=faces, zmax=45,
    title="Irradiance removed by surrounding-block shadows",
    cbar_label="kWh/m2 lost to context (without - with)", cmap="Reds",
    vmin=0.0, vmax=float(np.nanmax(loss)) or 1.0,
    note="dark red = facade most shaded by the neighbours")
fig
"""),
            md("""
## Summary

* `context-geometry` brings the **surrounding blocks** into the raytrace as
  occluders without adding them to the measured set - the realistic way to run
  a facade study on a small AOI.
* Fetch a larger polygon, split target vs context, and the with / without
  comparison isolates the neighbours' shadowing.
* Needs a trigger (`analysis-surfaces` here). Not yet live on advanced UTCI
  (PR #119, pending re-deploy).
"""),
        ]
    )


# ===========================================================================
# 08 - realistic combined urban scenario
# ===========================================================================


def build_08():
    return nb(
        [
            md("""
# 08 - A Realistic Urban-Design Study (Everything Combined)

This is what a real microclimate study looks like - all the advanced inputs
together on the same site:

* **target buildings** with **facade** `analysis-surfaces` synthesis
  (+ `partial-cells` clipping),
* the **surrounding blocks** as `context-geometry` occluders,
* an illustrative **terrain** via `ground-geometry`,
* a **summer multi-month** `time-period` (Jun-Aug),

run on **solar radiation** and on **UTCI** (incl. `physics:"advanced"`).

Each ingredient has its own notebook (`01`, `06`, `07`, `05`); here they are
composed into one payload, the way you would actually brief a site.
"""),
            md("## Setup"),
            code(SETUP),
            code(WEATHER),
            md("""
## Assemble the scene

Larger fetch -> target/context split (notebook `07`), plus a synthesized
terrain (notebook `06`). One consistent meter frame throughout.
"""),
            code("""
import ir_context as ic
import ir_terrain

inner = ia.VIENNA_KARLSPLATZ
outer = ic.expand_polygon(inner, halo_m=200.0, ref_lat=ia.VIENNA_LAT)
big = ia.fetch_buildings(client, outer, "context_buildings.json")
rect = ic.inner_rect_local(inner, outer, ia.VIENNA_LAT)
target_ids, context_ids = ic.split_target_context(big, rect)
target = ic.subset(big, target_ids)
context = ic.subset(big, context_ids)

terrain_mesh, heights = ir_terrain.generate_terrain(
    size_m=512.0, n=40, slope=(0.03, 0.02), bumps=((2.0, 6.0),))

vegetation = ia.fetch_vegetation(client, inner, "karlsplatz_veg.json")
ground = ia.fetch_ground_materials(client, inner, "karlsplatz_ground.json")

print(f"target buildings : {len(target)}")
print(f"context occluders: {len(context)}")
print(f"terrain tris     : {len(terrain_mesh['terrain0']['indices'])//3}")
print(f"vegetation       : {len(vegetation)} | ground layers: {list(ground)}")
"""),
            code("""
# The scene at a glance: terrain relief + the measured target buildings (solid
# blue) lifted out of the light translucent context blocks (grey occluders).
# Splitting target vs context keeps a busy urban scene readable.
fig, ax = ir.terrain_3d(
    heights, size_m=512.0,
    context_faces=ia.building_faces(context, max_buildings=600),
    target_faces=ia.building_faces(target),
    title="The study scene: terrain + target (blue) + surrounding blocks (grey)",
    note="Vienna Karlsplatz | synthetic terrain | target measured, context occludes")
fig
"""),
            md("""
## Solar radiation - the full advanced payload

Target facades + context occluders + terrain drape + multi-month window, all
in one request. This is the headline urban-design run.
"""),
            code("""
from infrared_sdk.analyses.types import (
    SolarRadiationModelRequest, BaseAnalysisPayload, AnalysesName)

# Summer multi-month window (Jun-Aug).
tp = TimePeriod(start_month=6, start_day=1, start_hour=5,
                end_month=8, end_day=31, end_hour=20)
loc = Location(latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON)
wp = client.weather.filter_weather_data(identifier=weather_id, time_period=tp)
print("weather points (multi-month):", len(wp))

sr = SolarRadiationModelRequest.from_weatherfile_payload(
    BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
    loc, tp, wp).to_dict()
sr["latitude"] = ia.VIENNA_LAT
sr["longitude"] = ia.VIENNA_LON
sr["geometries"] = target               # measure the target facades
sr["analysis-surfaces"] = "facades"
sr["surface-grid-size"] = 4.0
sr["surface-offset"] = 0.1
sr["partial-cells"] = True              # clip boundary cells
sr["min-coverage"] = 0.25
sr["context-geometry"] = context        # surrounding-block shadows
sr["ground-geometry"] = terrain_mesh    # terrain drape / occluder

sr_res, info = ia.run_job("solar-radiation", sr, label="combined", max_wait=500)
print("frames:", len(sr_res["surfaces"]), "| sensors:", sr_res["sensor-count"],
      "| elapsed:", info["elapsed_s"], "s")
"""),
            md("""
### Result payload, described

The combined run returns the standard **surface** payload (notebook `01`):
`surfaces` (per-frame `{origin, u-axis, v-axis, grid-size, nu, nv, values,
cell-area, cell-tris, area, mean, peak}`), per-building `aggregates`, and
`sensor-count` - for the **target** facades only. Context and terrain shape the
values (via shadowing / drape) but never appear in the output. Reconstruct the
world cells exactly as before (`reconstruct_cells`).
"""),
            code("""
tris, values, normals = ia.reconstruct_cells(sr_res["surfaces"])
# Show the measured target massing plus a faint hint of the surrounding context.
fig, ax = ir.surface_mesh(
    tris, values, normals=normals,
    context_faces=ia.building_faces(target) + ia.building_faces(context, max_buildings=400),
    context_alpha=0.04, zmax=45,
    title="Facade Solar (summer) - target + context + terrain",
    cbar_label="kWh/m2 (Jun-Aug, per cell)", cmap="inferno",
    note=f"{sr_res['sensor-count']:,} facade sensors | context-shaded, terrain-draped | staging")
fig
"""),
            md("""
## UTCI - advanced physics over terrain

Thermal comfort for the same site: `physics:"advanced"` (hourly stepping +
canopy ray-march) with vegetation, ground materials and the **terrain**
(`ground-geometry` is accepted on thermal models). Output is the standard
512x512 grid of felt temperature.

> `context-geometry` on advanced UTCI just merged (PR #119) but is not live
> until the next staging re-deploy, so we leave it off here and let the terrain
> + canopy do the work. For context occlusion on a thermal run today, use
> `physics:"v1"`.
"""),
            code("""
from infrared_sdk.analyses.types import UtciModelRequest

utci = UtciModelRequest.from_weatherfile_payload(
    UtciModelRequest(analysis_type=AnalysesName.thermal_comfort_index,
                     latitude=ia.VIENNA_LAT, longitude=ia.VIENNA_LON,
                     time_period=tp), loc, tp, wp).to_dict()
utci["latitude"] = ia.VIENNA_LAT
utci["longitude"] = ia.VIENNA_LON
utci["geometries"] = target
if vegetation:
    utci["vegetation"] = vegetation
if ground:
    utci["ground-materials"] = ground
utci["ground-geometry"] = terrain_mesh
utci["physics"] = "advanced"
utci["canopy-transmissivity"] = 0.40

utci_res, info = ia.run_job("thermal-comfort-index", utci, label="advanced+terrain", max_wait=500)
grid = np.array(utci_res["output"], dtype=float)
print("UTCI grid:", grid.shape, "| mean %.2f degC" % float(np.nanmean(grid)),
      "| elapsed:", info["elapsed_s"], "s")
"""),
            code("""
fig, ax = ir.grid_heatmap(
    grid, title="UTCI advanced over terrain (summer multi-month)",
    cbar_label="UTCI (degC)", cmap="turbo", crop=True,
    note="Vienna Karlsplatz | physics=advanced | terrain drape | staging")
fig
"""),
            md("""
## Summary - the advanced toolkit, combined

| Ingredient | Field | Notebook |
|---|---|---|
| facade sensors | `analysis-surfaces:"facades"` + `partial-cells` | `01` |
| surrounding shadows | `context-geometry` | `07` |
| terrain | `ground-geometry` | `06` |
| seasonal window | multi-month `time-period` | `03` |
| advanced thermal | `physics:"advanced"` + `canopy-transmissivity` | `05` |

All of it is direct-API today (the SDK's typed models don't expose these
fields yet), POSTed to the same async endpoints the SDK uses. Swap the
synthetic terrain for a real DEM and the larger fetch for your own site, and
this is a production microclimate study.
"""),
        ]
    )


# ===========================================================================
# write all notebooks
# ===========================================================================

NOTEBOOKS = {
    "00_setup.ipynb": build_00,
    "01_solar_radiation_advanced.ipynb": build_01,
    "02_daylight_availability_advanced.ipynb": build_02,
    "03_direct_sun_hours_advanced.ipynb": build_03,
    "04_sky_view_factors_advanced.ipynb": build_04,
    "05_thermal_comfort_utci_advanced.ipynb": build_05,
    "06_terrain_ground_geometry.ipynb": build_06,
    "07_context_geometry_occluders.ipynb": build_07,
    "08_realistic_urban_scenario.ipynb": build_08,
}


def main():
    for fname, builder in NOTEBOOKS.items():
        path = HERE / fname
        nbf.write(builder(), path)
        print("wrote", fname)


if __name__ == "__main__":
    main()
