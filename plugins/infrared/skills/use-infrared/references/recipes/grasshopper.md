# Recipe: Infrared SDK in Rhino 8 Grasshopper
Use the Python SDK (`infrared-sdk` 1.0.0) from a Grasshopper Python 3 component in Rhino 8 (Mac or Windows, CPython 3.9).

This is a toolbox. Take what you need. A small script that blocks the canvas for 5 seconds is fine. A component for 2000 buildings needs most of this file.

Companion files:

- [`grasshopper-geometry-and-drawing.md`](grasshopper-geometry-and-drawing.md): Rhino geometry in, results out, fast drawing, bake, per-building statistics.
- [`grasshopper-pitfalls.md`](grasshopper-pitfalls.md): the short list of traps.

API detail: https://infrared.city/docs/sdk/ (agents: https://infrared.city/docs/sdk/llms.txt).

## 1. Install and load the SDK in Rhino

Two facts decide everything here.

- **All Python 3 components in one Rhino session share one Python process.** The first component that imports `infrared_sdk` decides which copy every other component gets. An old SDK in one component of the file breaks all new components.
- **Rhino caches the environment of a script component.** A changed `# r:` line may not resolve again.

Rules:

- Install with **Rhino's own pip**. System Python 3.11+ gives wheels that Rhino cannot load. `uv` can pick x86_64 wheels on an ARM Mac.
- Install `pyproj` too. Without it, a projected CRS uses an approximation: no failure, only less exact. `orjson` is optional.

### Option A: the `# r:` header (one component, new file)

```python
#! python 3
# r: infrared-sdk==1.0.0
```

Pin the version. Not for many components in one file.

### Option B: one shared folder (many components)

Install once into a folder that you own. Use Rhino's pip.

```bash
# macOS path. On Windows, use the python.exe in the same py39-rh8 folder.
~/.rhinocode/py39-rh8/python3.9 -I -m pip install --upgrade \
    --target ~/infrared-sdk-libs infrared-sdk==1.0.0 pyproj orjson
```

Put this bootstrap at the top of **every** Infrared component. It puts the folder first on `sys.path` and removes an SDK that another component loaded from somewhere else.

```python
import os, sys

LIBS = os.path.expanduser("~/infrared-sdk-libs")
if LIBS in sys.path:
    sys.path.remove(LIBS)
sys.path.insert(0, LIBS)

loaded = sys.modules.get("infrared_sdk")
if loaded is not None and not (getattr(loaded, "__file__", "") or "").startswith(LIBS):
    # Another copy won the import race. Drop it so that the import below reloads.
    for name in [n for n in sys.modules if n.split(".")[0] == "infrared_sdk"]:
        del sys.modules[name]
```

To update, run the pip command again and solve the component. Restart Rhino only if a component already imported the SDK in this session.

### Check what is loaded

Use a small probe component when anything looks strange: `a = "%s from %s" % (infrared_sdk.__version__, infrared_sdk.__file__)`.

## 2. Client, payloads, weather, area run

### Client

```python
import os
from infrared_sdk import InfraredClient

def make_client(api_key=""):
    key = (api_key or os.environ.get("INFRARED_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("No API key. Wire a Panel with your key.")
    return InfraredClient(api_key=key)
```

- Use one client for each thread (safe default). Close it in `finally`, after you read the result.

### Payloads

| Analysis | Class | `analysis_type` for `preview_area` |
|---|---|---|
| Wind speed | `WindModelRequest` | `wind-speed` |
| Pedestrian wind comfort | `PwcModelRequest` | `pedestrian-wind-comfort` |
| Solar radiation | `SolarRadiationModelRequest` | `solar-radiation` |
| Sun hours, daylight availability | `SolarModelRequest` | `direct-sun-hours`, `daylight-availability` |
| Sky view factor | `SvfModelRequest` | `sky-view-factors` |
| UTCI | `UtciModelRequest` | `thermal-comfort-index` |
| Thermal comfort statistics | `TcsModelRequest` | `thermal-comfort-statistics` |
| Daylight factor (interior) | `DaylightFactorModelRequest` | single job, see below |

`AnalysesName` holds the names (`AnalysesName.solar_radiation`, and so on). Import the classes from `infrared_sdk.analyses.types`.

### Weather

Two sources: your own EPW file, or the public station catalog. Your file is read on your machine. Nothing is uploaded.

```python
from infrared_sdk import parse_epw
from infrared_sdk.analyses.types import AnalysesName, UtciModelBaseRequest, UtciModelRequest
from infrared_sdk.models import Location, TimePeriod

epw = parse_epw("site.epw")                    # a gap in the data raises: do not catch it
period = TimePeriod(start_month=6, start_day=1, start_hour=8,
                    end_month=8, end_day=31, end_hour=18)
payload = UtciModelRequest.from_weatherfile_payload(
    payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
    location=Location(latitude=lat, longitude=lon),
    time_period=period,
    weather_data=epw,
)
```

A winter window (1 Dec to 28 Feb) is one `TimePeriod`.
Catalog weather, when you have no file:

```python
stations = client.weather.get_weather_file_from_location(lat=lat, lon=lon, radius=50)
rows = client.weather.filter_weather_data(identifier=stations[0]["uuid"], time_period=period)
# Pass `rows` as weather_data=. Read the weather once and reuse it for all variants.
```

Solar radiation uses the same call. Start from a plain base payload, then add the facade and roof fields:

```python
from typing import Literal
from infrared_sdk.analyses.types import BaseAnalysisPayload, SolarRadiationModelRequest

base = BaseAnalysisPayload[Literal[AnalysesName.solar_radiation]](
    analysis_type=AnalysesName.solar_radiation)
payload = SolarRadiationModelRequest.from_weatherfile_payload(
    payload=base, location=Location(latitude=lat, longitude=lon),
    time_period=period, weather_data=epw)
payload = payload.model_copy(update={
    "analysis_surfaces": "all",     # "facades" | "roofs" | "all"
    "surface_grid_size": 2.0,       # metres; 1.0 gives 4x the cells
})
```

Sky view factor needs no weather. `SvfModelRequest(analysis_type="sky-view-factors", analysis_surfaces="facades", surface_grid_size=3.0)` is a complete facade payload.

### Preview, then run

`preview_area` is free and local. Call it before every paid run. Pass `analysis_type` and `payload` as keywords.

```python
preview = client.preview_area(polygon, analysis_type="thermal-comfort-index",
                              payload=payload, buildings=buildings)
print(preview.tile_count, preview.would_bill_jobs, preview.sensor_count,
      preview.estimated_cost_tokens)

result = client.run_area_and_wait(
    payload, polygon,                     # polygon: GeoJSON, WGS84 [lon, lat]
    buildings=buildings,                  # see grasshopper-geometry-and-drawing.md
    on_progress=lambda st: stage("server %d/%d" % (st.succeeded, st.total)),
    on_accepted=lambda job_id, *_: save_job_id(job_id),   # log what the server took
    max_workers=8,                        # submit pool; split it between parallel variants
    retries=1,                            # failed tiles run once more
)
```

- `payload` can be a **list**. Analyses on the same site share one geometry upload.
- A failed tile raises `AreaRunError`. There is no partial map.
- Write the job IDs to a file in `on_accepted`. After a Rhino crash you still know what the server took.
- Ground analyses give an `AreaResult`. Facade analyses give a `SurfaceAnalysisResult`.
- Wind and PWC: when the buildings sit on terrain, set `terrain_alignment="to-ground"`. They refuse `ground_geometry`.
- Comfort materials (UTCI and TCS only): `wall_albedo`, `wall_absorptivity`, `canopy_transmissivity`, `ground_albedo`, `ground_dt_max`.

### Daylight factor: one job

Interior daylight factor is one job for one building, not a map. Send the walls, slabs and windows as closed meshes in metres. `interior_entities` wraps them with a category.

```python
from infrared_sdk import PartsRunError, interior_entities
from infrared_sdk.analyses.types import DaylightFactorModelRequest

# Each argument is {id: {"coordinates": [...], "indices": [...]}} from your Rhino objects.
barriers = {**interior_entities(walls, category="wall"),
            **interior_entities(slabs, category="floor")}
payload = DaylightFactorModelRequest(
    analysis_type=AnalysesName.daylight_factor,
    barriers=barriers,
    openings=interior_entities(windows, category="window"),   # glazing in the plane of the wall
    floors=list(range(n_floors)),
    grid_size=0.5,                    # sensor spacing in metres
    analysis_height=0.8,              # check this against your sill height
    context_geometry=interior_entities(neighbours),           # shade only
)
try:
    result = client.analyses.run_and_wait(
        payload, timeout=600,
        on_progress=lambda s: stage("server %d/%d" % (s.succeeded, s.total)))
except PartsRunError as exc:          # a large building runs in parts: send only the failed ones
    result = client.analyses.run_and_wait(payload, retry_from=exc.schedule)
```

Keep the wall solid and put the window in its plane. Sensor surfaces must be horizontal. Add `context_geometry`, or the rooms read too bright.

## 3. The non-blocking component

### Why

A component that calls `run_area_and_wait` on the UI thread freezes Grasshopper for the whole run. A background thread fixes this. A naive one fails in these ways:

- A saved file with the `run` toggle ON starts a **paid** run when somebody opens the file.
- Two components that draw at the same time can crash Rhino on macOS.
- A worker thread that touches the Rhino document or the canvas crashes Rhino at random.

### Rules

- **Run on the rising edge only.** Start when `run` goes from OFF to ON. Never on the level.
- **Split the work by thread.**
  - UI thread (the solve): read the Rhino document, convert geometry, draw, bake.
  - Worker thread: network only (weather, upload, wait, download). Pure numpy work is safe there too.
- **Never block the UI thread.** No `join()`. No lock with a timeout. Use `lock.acquire(False)` and try later.
- **Wake the component from the UI thread**, with `ScheduleSolution`. Never call `ExpireSolution` from the worker.
- **Keep state in `scriptcontext.sticky`**, keyed by the component `InstanceGuid` and a **version** string. Change the version when the stored shapes change.
- **Put `infrared_sdk.__version__` into the input fingerprint.** A result from another SDK version has other classes.
- **One heavy draw at a time** across all Infrared components. Use one shared lock in `sticky`.
- **Progress must not re-solve.** A `ScheduleSolution` for each progress tick re-runs every downstream component. Update only `comp.Message` and repaint. Solve once when the job is done.
- **Keep paid results.** A finished result stays in `sticky` until the inputs change. A failed draw does not lose it.
- **Make errors sticky.** Store the error with the input fingerprint. Show it on every solve until the inputs change.
- **Log elapsed seconds** (`[ 12.3s] stage`) and write the log to a file.

### Recipe: the state machine

`prepare()`, `run_analysis()` and `finish()` are yours.

```python
import threading, time, traceback
import Grasshopper, Rhino, System
import scriptcontext as sc

DRAW_LOCK = sc.sticky.setdefault("ir::draw_lock", threading.Lock())   # shared by ALL components
VERSION = "v1"                                                        # bump when sticky shapes change


def on_ui(fn):
    """Run fn on the Rhino UI thread. Safe to call from a worker."""
    Rhino.RhinoApp.InvokeOnUiThread(System.Action(fn))


def resolve_later(comp, delay=10):
    """Ask for ONE new solve. Never blocks the caller."""
    def expire(doc):
        if doc.FindObject(comp.InstanceGuid, True) is not None:   # the component may be deleted
            comp.ExpireSolution(False)

    def schedule():
        doc = comp.OnPingDocument()
        if doc is not None:
            doc.ScheduleSolution(delay, Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(expire))

    on_ui(schedule)


def repaint(comp, text):
    """Update the label only. No solve, so downstream components stay quiet."""
    def paint():
        comp.Message = text
        comp.OnDisplayExpired(True)
    on_ui(paint)


def solve(comp, inputs):
    scope = "ir_x::%s::%s" % (VERSION, comp.InstanceGuid)
    job_key, last_key, edge_key = scope + "::job", scope + "::last", scope + "::run_prev"

    # 1. Rising edge. The first solve after open sees prev == run, so a saved ON toggle never runs.
    prev = sc.sticky.get(edge_key, bool(inputs["run"]))
    sc.sticky[edge_key] = bool(inputs["run"])
    armed = bool(inputs["run"]) and not prev

    last = dict(sc.sticky.get(last_key) or {})
    job = sc.sticky.get(job_key)

    # 2. Finished job: draw on the UI thread, one component at a time.
    if job is not None and job["state"] == "done":
        if not DRAW_LOCK.acquire(False):
            comp.Message = "waiting for another Infrared component"
            resolve_later(comp, 500)
            return last
        try:
            sc.sticky.pop(job_key, None)
            out = finish(comp, job, inputs)              # yours: show or bake
            sc.sticky[last_key] = out
            return out
        finally:
            DRAW_LOCK.release()

    # 3. Running job: show the last result. The worker repaints the label.
    if job is not None:
        return last

    # 4. Idle, or start a new run.
    if not armed:
        comp.Message = "ready"
        return last
    ctx = prepare(comp, inputs)                           # yours: UI thread, reads the document
    start(comp, job_key, ctx)
    comp.Message = "running"
    return last


def start(comp, job_key, ctx):
    job = {"state": "running", "stage": "starting", "t0": time.perf_counter(), "lines": []}

    def stage(name):
        job["stage"] = name
        repaint(comp, "%.0fs  %s" % (time.perf_counter() - job["t0"], name))

    def work():
        try:
            job["result"] = run_analysis(ctx, stage)     # yours: network only, no document access
        except Exception as exc:
            job["exc"] = exc
            job["lines"].append(traceback.format_exc())
        finally:
            job["state"] = "done"
            resolve_later(comp)                          # the one solve at the end

    sc.sticky[job_key] = job
    threading.Thread(target=work, name="ir-run", daemon=True).start()
```

### Recipe: sticky error bubble
```python
def flag(key, fp, level, text):
    sc.sticky[key] = {"fp": fp, "level": level, "text": text}

def show_flag(comp, key, fp):
    prob = sc.sticky.get(key)
    if prob and prob["fp"] != fp:          # the inputs changed: forget the old problem
        sc.sticky.pop(key, None)
    elif prob:
        comp.AddRuntimeMessage(prob["level"], prob["text"])
```

`fp` is a `repr()` of everything that changes the result: key, time period, surfaces, legend pins, object IDs, grid size and `infrared_sdk.__version__`. `level` is a `Grasshopper.Kernel.GH_RuntimeMessageLevel` value.

### Recipe: reuse paid results for each variant
```python
kept = sc.sticky.get(raw_key)                        # (fingerprint, {variant: result})
raws = dict(kept[1]) if kept and kept[0] == ctx["fp"] else {}
todo = [n for n in names if n not in raws]           # only new or failed variants run again
```

**Debounce.** If a slider drives a costly step, store `(fingerprint, first time seen)`. Start the step when the fingerprint did not change for 0.5 s.

### Traps

- `Rhino.RhinoDoc.ActiveDoc` is `None` for a new, unsaved file on macOS. Use `Rhino.RhinoDoc.OpenDocuments()[0]`.
- `Layers.Modify` in a loop can crash the Layers panel on Rhino Mac. Do not change layers in code. Tell the user instead.
- Never patch SDK functions inside the shared Rhino process. It breaks every other component.

## 4. Settings panels instead of many sliders

For a component with many options, use one **text input** in list access. A Panel on the canvas holds one key on each line:

```
analysis: utci          # solar | sun-hours | daylight | svf | utci | tcs | wind | pwc
months: jun-aug         # 6 | 6-8 | Jun | Dec-Feb
hours: 9 - 17
legend: 26..46          # auto | low..high
```

Make the parser forgiving (any case, `:` or `=`, `#` comments, month names, `6-8` or `6..8`). An unknown key gives a warning with "did you mean". A bad value gives an error bubble that names the key. Several panels merge in order: a preset panel first, then a small override panel. Keep one table with a row for each analysis (name, unit, default legend, facade support).

## 5. Migrating a 0.5.1 script

The full upgrade steps are in `UPGRADING.md` in the installed package (`infrared_sdk-1.0.0.dist-info/UPGRADING.md`). The docs home is https://infrared.city/docs/sdk/ (there is no separate upgrade page). Do these steps in order.

1. **Load path.** Use section 1. Make sure no 0.5.1 component stays in the same file.
2. **Imports.** The modules `infrared_sdk.tiling.merger`, `merger_smart` and `terrain_envelope` are gone. So are the old `transforms` and `terrain_slice` helpers. Use `run_area_and_wait`, or `client.merge_area_jobs(schedule)`.
3. **Grids.** Never read `result.merged_grid` for numbers. Use `result.physical_grid(np.float32)`. The grid is read-only.
4. **Facades.** Replace loops over `result.surfaces` with `result.columns` and `columns.render_buffers()`.
5. **Payload arguments.** UTCI and TCS requests now refuse unknown keywords. Fix the typos that this shows.
6. **Buildings.** Each entry needs `coordinates` and `indices`. A bad entry now raises before submit.
7. **Ground materials.** Keys are `asphalt`, `concrete`, `soil`, `vegetation`, `water`. An unknown key raises `ValueError`.
8. **Weather.** A private weather identifier does not work. Use `parse_epw("file.epw")`.
9. **Workers.** The default `max_workers` is 8 (was 20).
10. **Saved state.** Schedules, `config_hash` values and layouts from 0.5.x do not load. Run again. Version your sticky keys.
11. **Compare.** Do not compare facade values with 0.5.1 sensor by sensor. Wall orientation, grid alignment and mesh cleaning changed.

| 0.5.1 | 1.0 |
|---|---|
| `np.nanmin(result.merged_grid)`, `grid += x` | `g = result.physical_grid(np.float32)` |
| `merge_area_jobs(schedule, dtype=...)` | no `dtype=`; use `physical_grid(dtype)` |
| `result.surfaces[...]` loops | `result.columns`, `columns.render_buffers()` |
| `np.isnan(columns.values[i])` | `columns.has_value(i)` |
| `client.api_key` as text | `client.api_key.get_secret_value()` |
| daylight factor gives a dict | gives `DaylightFactorResult` (`.to_json()` for a dict) |
| `retry_from=` an old schedule | refused: start a new run |
| `WeatherDataPoint.znithLuminance` | `.zenithLuminance` |
| `buildings.get_area(polygon)` | reads public data on your machine; needs `infrared-sdk[geodata]` |
