# Building a Grasshopper component against the Infrared SDK

**How to build one, whichever analysis you are running.** Mode choice, the run
sequence, the whole skeleton, and every shared helper.

Then read [`grasshopper-analyses.md`](grasshopper-analyses.md) for what your
specific analysis needs, and
[`grasshopper-pitfalls.md`](grasshopper-pitfalls.md) when something looks wrong
or before you trust a number.

Every value here was measured on a real ~1,000-building Hong Kong site across
about forty failures. **The expensive ones all returned HTTP 200.**

## The sequence both blueprints follow

Do not reorder steps 1–6. Each one exists because doing it later cost
something real.

```
1  latch the run toggle on its RISING EDGE
2  resolve the coordinate frame for the site
3  read the AOI rectangle from a layer
4  select geometry whose BBOX overlaps the AOI   (cheap, per-object)
5  report what you found + the free cost preview
6  ── THE GATE ──  if not armed: return here
7  convert meshes to flat arrays                 (expensive, past the gate)
8  build the payload in ONE constructor call
9  size the job budget, dump the payload to disk
10 submit and BLOCK; record job ids before waiting
11 resolve ONE colour scale, then render
12 bake, and write the whole log to disk
```

**Why the gate matters.** Grasshopper re-solves at 10–30 Hz while anything is
dragged. Steps 7–12 above the gate means six figures of marshalled .NET calls
per drag frame. Steps 1–5 are bbox tests and are cheap enough to run always —
which is what makes the unarmed solve a useful free preview.

---

## The skeleton in full

The whole flow in one place: directives, imports, settings, the class, the
gate, and the Script-Mode entry block that makes a pasted file run at all.

**Read it for the control flow, whichever mode you chose.** If you went
SDK-Mode, take the body of `RunScript` and the helpers and ignore the entry
block, returning through `emit()` instead. If you want the single pasteable
file, this is it — but re-read the box above about what it does *not* output.

```python
#! python 3
# r: infrared-sdk==0.5.1, orjson==3.11.5
# venv: ir-gh
"""IR Solar — solar-radiation on building facades.

Wire a Toggle to `x` (run) and a Panel with your API key to `y`.
Leave run OFF for a first solve: it reads the layers, reports what it found
and what a run would cost, and submits nothing.
"""
import os, sys, time, traceback

import Rhino
import Rhino.Geometry as rg
import System
import System.Drawing as sd
import Grasshopper
import scriptcontext as sc

# ── SETTINGS ─── values explained in grasshopper-analyses.md (A1 / B1)
SITE               = "midlevels"
DEFAULT_MONTH      = 4            # single month; multi-month fails server-side
DEFAULT_SURFACES   = "facades"    # "all" adds roofs -- see A1
DEFAULT_PRETTY     = False        # emit_cell_tris: ~90% of the response body
SURFACE_GRID       = 2.0
BUILDINGS_PER_JOB  = 100
SUBMIT_WORKERS     = 8
LEGEND_PERCENTILE  = 99.5
PALETTE            = "magma"      # "magma" | "spectral"  (see colour_of)
USE_TERRAIN        = True
FAR_HILLS          = True
BAKE_LAYER         = "IR_Solar_Result"
OUT_DIR            = os.path.join(os.path.expanduser("~"), "ir_payloads")
BASE_URL           = "https://api.infrared.city/v2"

L_AOI, L_BUILDINGS = "BoundingBox", "Buildings"
L_INFRA, L_TERRAIN = "Infrastructure", "Terrain"
L_HILLS            = "Terrain_Context"


class _IRSolver(object):
    """Plain object. NOT a GH_ScriptInstance subclass -- Rhino detects that
    base class in pasted code and drives it as a context manager, failing with
    "object has no attribute '__enter__'"."""

    def RunScript(self, api_key, run):
        comp = ghenv.Component                                   # noqa: F821
        scope = "ir_solar::%s" % comp.InstanceGuid
        lines = []

        def log(msg):
            lines.append(msg)
            Rhino.RhinoApp.WriteLine("[ir-solar] " + msg)

        def warn(msg):
            comp.AddRuntimeMessage(
                Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, msg)

        # 1 ── RISING EDGE. A Toggle is a LEVEL, not an event: read as a level,
        #      every later solve re-submits a slow, BILLED job.
        armed = rising_edge(sc.sticky, scope, run)

        facades, ground, lo, hi, cost = [], None, None, None, ""
        try:
            # 2-4 ── frame, AOI, selection. Cheap: per-object bbox only.
            aoi = aoi_bbox_from_layer(L_AOI)
            if aoi is None:
                warn("No %s layer, or it is empty." % L_AOI)
                return "\n".join(lines)
            building_objs = select_in_aoi(L_BUILDINGS, aoi)
            objs = building_objs + select_in_aoi(L_INFRA, aoi)
            origin = (aoi[0], aoi[1])            # local metres -> payload frame

            # STEP 2. Do this pre-gate: it is arithmetic, and an unset anchor
            # must fail before anything is billed, not after.
            anchor = document_anchor()
            if anchor is None:
                warn("No EarthAnchorPoint on this document. Run Rhino's "
                     "EarthAnchorPoint command, or wire lon/lat Panels.")
                return "\n".join(lines)
            frame = Frame(*anchor)
            polygon = frame.aoi_polygon(*aoi)     # also reused by build_payload
            log("AOI %.0f x %.0f m, %d object(s)"
                % (aoi[2] - aoi[0], aoi[3] - aoi[1], len(objs)))

            # 5 ── FREE preflight. preview_area bills nothing, so call it
            #      before a blocking submit and say how long the freeze will
            #      be. Note it estimates a GROUND GRID: a surface run is much
            #      slower, so treat it as a floor, not a promise.
            from infrared_sdk import InfraredClient
            _c = InfraredClient(api_key=api_key, base_url=BASE_URL)
            try:
                pv = _c.preview_area(polygon, analysis_type="solar-radiation")
                cost = ("%d tile(s), ~%.0fs, ~%.0f tokens (ground-grid "
                        "estimate)" % (pv.tile_count, pv.estimated_time_s,
                                       pv.estimated_cost_tokens))
            except Exception as exc:
                cost = "preflight failed: %s" % exc     # non-fatal
            finally:
                _c.close()
            log(cost)

            if not armed:
                log("idle -- flip run off and on to submit")
                return "\n".join(lines)

            # 6 ── THE GATE. Everything below is expensive; nothing below runs
            #      on a drag frame.
            buildings, skipped, fused = buildings_payload(
                objs, origin, mergeable=building_objs)
            log("converted %d building(s), skipped %d, fused %d stacked"
                % (len(buildings), skipped, fused))

            terrain = joined_flat(select_in_aoi(L_TERRAIN, aoi), origin) \
                if USE_TERRAIN else None
            hills = joined_flat(objects_on_layer(L_HILLS), origin) \
                if FAR_HILLS else None

            # 7-9 ── weather, payload, budget.       (build_payload, below)
            payload, polygon, lat, lon = build_payload(
                aoi, origin, terrain, hills, api_key, frame)
            budget = sensor_budget(buildings, SURFACE_GRID, BUILDINGS_PER_JOB)
            os.environ.setdefault(
                "INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES", str(1 << 20))

            # 10 ── SUBMIT AND BLOCK. Grasshopper is unresponsive here; that is
            #       deliberate. Record the job ids on the FIRST poll so a run
            #       lost to a crash is still recoverable.
            from infrared_sdk import InfraredClient
            conn = InfraredClient(api_key=api_key, base_url=BASE_URL)
            seen = {}

            def on_progress(state):
                js = getattr(state, "job_states", None) or {}
                if js and not seen:
                    seen.update(js)
                    _write(os.path.join(OUT_DIR, "last_schedule.json"),
                           repr(sorted(js)))
                    log("%d job(s) recorded" % len(js))

            try:
                result = conn.run_area_and_wait(
                    payload, polygon, buildings=buildings,
                    max_sensors_per_job=budget,
                    max_workers=SUBMIT_WORKERS,
                    on_progress=on_progress)
            finally:
                conn.close()
            log("result received")

            # 11 ── ONE colour scale, then render.
            lo, hi = 0.0, facade_percentile(result, LEGEND_PERCENTILE)
            log("colour scale %.2f .. %.2f" % (lo, hi))
            facades, problems = surface_result_to_mesh(result, origin, lo, hi)
            for bid, why, n in problems[:5]:
                log("PROBLEM %s: %s (%d)" % (bid, why, n))

            # 12 ── bake.
            log("baked %d object(s)" % bake(facades, BAKE_LAYER))

        except Exception as exc:
            # The SDK's diagnostics are PRINTS, and diag.error() goes to
            # STDERR -- so a logging handler catches nothing and a
            # stdout-only capture misses exactly the line explaining a
            # failure. The gateway also returns RFC 7807: read `detail`,
            # not `message`.
            warn("%s: %s" % (type(exc).__name__, exc))
            log("EXCEPTION " + traceback.format_exc())
        finally:
            if armed:
                _write(os.path.join(OUT_DIR, "last_log.txt"), "\n".join(lines))

        return "\n".join(lines)


def _write(path, text):
    """Encode BEFORE opening: open(...,"w") truncates immediately, so a throw
    between open and write leaves a 0-BYTE file -- destroying the log you were
    trying to keep. Never swallow the failure silently."""
    try:
        blob = text.encode("utf-8", "replace")
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "wb") as fh:
            fh.write(blob)
    except Exception as exc:
        Rhino.RhinoApp.WriteLine("[ir-solar] could not write %s: %s"
                                 % (path, exc))


# ── SCRIPT-MODE ENTRY ───────────────────────────────────────────────────────
# A pasted Python 3 component runs in SCRIPT-MODE: top-to-bottom code with the
# stock sockets x, y and output a. A class alone defines something that is
# never called -- no error, no output, nothing happens. This block runs it and
# reads whatever sockets exist.
def _in(name, default):
    v = globals().get(name)
    return default if v is None else v


_solver = _IRSolver()
a = _solver.RunScript(
    _in("api_key", _in("y", "")),
    _in("run", _in("x", False)),
)
out = a                     # named outputs fill in if the sockets exist
log = a
```

Every helper the skeleton calls is defined below: `rising_edge`, `colour_of`,
`drape_onto`, `bake`, `merge_stacked` in A6 · `objects_on_layer`,
`select_in_aoi`, `aoi_bbox_from_layer`, `mesh_to_flat`, `joined_flat`,
`buildings_payload` in A6 · `Frame`, `build_payload`, `sensor_budget` in A6 ·
`facade_percentile` and `surface_result_to_mesh` live in
[`grasshopper-analyses.md`](grasshopper-analyses.md) A7, because they are
facade-specific.

One note on `on_progress`: `state.job_states` is read through `getattr` because
that is the shape observed in live runs (it logs `N job(s) recorded`), not
because the attribute is uncertain. Keep the guard — a rename would otherwise
silently disable crash recovery, which is the one thing that makes a lost run
recoverable rather than paid-for-and-gone.

---

## A2. Sockets and outputs

**Pick ONE mode. They are not compatible and mixing them is the single most
expensive mistake available here.**

| | Script-Mode (this skeleton) | SDK-Mode |
|---|---|---|
| what it is | top-to-bottom code in a pasted component | a `GH_ScriptInstance` subclass |
| how you get it | drop a Python 3 component and paste | *Convert To GH_ScriptInstance* in the menu |
| sockets | stock `x`, `y`, output `a`; more added by ZUI | declared by `RunScript`'s signature |
| output registration | **none** — assign a name at the end and it fills a socket of that name | `ScriptVariableParam` from `BeforeRunScript` |
| pasteable in one go | **yes** | no — a pasted class is never called |

### Which one you want — and it is probably not the flat file

**Building ONE component and want real named outputs? Use SDK-Mode.** Create
the component, *Convert To GH_ScriptInstance*, register typed outputs in
`BeforeRunScript`, and put the 12-step body in `RunScript` returning values
**by name** (next section). This is what the reference implementation does and
it is what gets coloured meshes onto a socket.

**Use Script-Mode only when the deliverable is a single pasteable file** — one
person handing another a component with no repo, no imports, no conversion
step. Right for distribution, wrong for authoring.

**"The skeleton in full" below is Script-Mode, and it is a BUILD ARTIFACT.**
The reference implementation is a modular SDK-Mode component plus shared
library modules; a build step flattens them into one namespace, strips the
`GH_ScriptInstance` base and appends the entry block. Read the skeleton to see
the whole flow in one place — but know what it costs:

> **Script-Mode has no output registration.** `facades`, `ground`, `aoi`,
> `legend_min`, `legend_max`, `broken` and `cost` from A2's table are **not**
> outputs in that form. The entry block assigns names at the bottom, which fill
> sockets *only if the user already added them by hand via ZUI*. On a freshly
> pasted component you get `a` — one string. **If the task is "return coloured
> meshes", the flat form does not do that by itself.**

A pasted `GH_ScriptInstance` subclass, meanwhile, defines something Rhino never
invokes: no error, no output, nothing happens — and Rhino hijacks that base
class if it sees it, failing with `object has no attribute '__enter__'`. That
is why the flat form's helper is a plain `object`: a consequence of flattening,
not a design preference.

### Returning outputs BY NAME (SDK-Mode)

The mechanism that makes A2's socket table real. Both halves exist because of
a shipped bug.

```python
OUTPUTS = [
    ("facades", "Facades", "Coloured facade meshes", "list", None),
    ("ground",  "Ground",  "Ground grid mesh",       "item", None),
    ("aoi",     "AOI",     "Analysed extent",        "item", None),
    ("legend_min", "Min",  "Lower legend bound",     "item", float),
    ("legend_max", "Max",  "Upper legend bound",     "item", float),
    ("broken",  "Broken",  "Worst-affected sources", "list", None),
    ("cost",    "Cost",    "Free preflight",         "item", str),
    ("log",     "Log",     "Step log",               "item", str),
]


def register_outputs(comp, outputs):
    # Call ONLY from BeforeRunScript. Inputs auto-derive from RunScript's
    # signature; outputs do not. They must be RhinoCodePluginGH
    # ScriptVariableParam instances -- the script runner casts every output to
    # that class and throws "Unable to cast" on a stdlib Param_Mesh. And
    # topology changes are forbidden mid-solve, which is why this cannot live
    # in RunScript.
    import clr
    clr.AddReference("RhinoCodePluginGH")
    from RhinoCodePluginGH.Parameters import ScriptVariableParam
    import Grasshopper.Kernel as ghk

    params = comp.Params
    if [q.Name for q in params.Output] == [o[0] for o in outputs]:
        return                                   # already correct; no-op

    # Build EVERY replacement FIRST. Unregistering before building means a
    # throw in between leaves the component with fewer outputs -- and
    # Grasshopper deletes the wires attached to params that disappear.
    fresh = []
    for name, nick, desc, access, hint in outputs:
        q = ScriptVariableParam(name)
        q.NickName, q.Description = nick, desc
        q.Access = (ghk.GH_ParamAccess.list if access == "list"
                    else ghk.GH_ParamAccess.item)
        if hint is not None:
            try:
                q.TypeHints.Select(clr.GetClrType(hint))
            except Exception:
                pass
        q.CreateAttributes()
        fresh.append(q)

    while params.Output.Count > 0:
        params.UnregisterOutputParameter(params.Output[0], True)
    for q in fresh:
        params.RegisterOutputParam(q)
    comp.VariableParameterMaintenance()
    params.OnParametersChanged()
    comp.Attributes.ExpireLayout()


def emit(comp, outputs, values, lines):
    # Return outputs BY NAME; order comes from `outputs`.
    #
    # A positional return means every exit path -- including each early return
    # -- restates every value in the same order, by hand. Drift there is
    # silent: a value lands on the wrong socket and the canvas shows plausible
    # wrong data. This SHIPPED. A later edit's final return omitted the
    # `broken` key that both early returns included, so after a real BILLED run
    # the one diagnostic output the docstring points at came back None.
    names = [o[0] for o in outputs]
    unknown = [k for k in values if k not in names]
    if unknown:
        raise KeyError("emit() got unknown outputs: %s (declared: %s)"
                       % (sorted(unknown), names))
    out = ["\n".join(lines) if n == "log" else values.get(n) for n in names]

    # Grasshopper caches the expected output COUNT before BeforeRunScript runs,
    # so the first solve after registration can expect a different number than
    # you produce. Pad or truncate; it self-heals on the second solve.
    count = comp.Params.Output.Count
    if count < len(out):
        out = out[:count]
    elif count > len(out):
        out = out + [None] * (count - len(out))
    return tuple(out)


class MyComponent(Grasshopper.Kernel.GH_ScriptInstance):
    def BeforeRunScript(self, comp):
        register_outputs(comp, OUTPUTS)          # never from RunScript

    def RunScript(self, api_key: str, run: bool):
        ...                                      # the 12 steps
        return emit(ghenv.Component, OUTPUTS, {
            "facades": facades, "ground": ground, "aoi": aoi_rect,
            "legend_min": lo, "legend_max": hi,
            "broken": broken, "cost": cost,
        }, lines)
```

**Build the dict in ONE place.** `emit` catches an unknown key but cannot catch
a *missing* one — that is precisely how the `broken` output went silently
`None`.

```
INPUTS
  x / run       Toggle or Button    submits, and BLOCKS until results land
  y / api_key   Panel               your Infrared key

OUTPUTS
  facades       list   one coloured mesh per building
  ground        item   the ground grid mesh, draped (when surfaces == "")
  aoi           item   the analysed extent, as a rectangle
  legend_min    item   float, the scale actually used
  legend_max    item   float
  broken        list   source meshes of the worst-affected buildings
  cost          item   str, the free preflight
  log           item   str, the step log
```

Everything else takes its constant. Optional named sockets can be added via
ZUI later; each must fall back to its constant when absent, and `None` must be
distinguishable from a deliberate `0` — `x or default` silently rewrites a
deliberate zero.

## A6. The helpers the steps above assume

Nothing here is SDK-specific — it is the Rhino side, and it is where the time
goes. Read layers first.

```python
import Rhino, Rhino.Geometry as rg

def objects_on_layer(path):
    """Objects on a layer given its FULL PATH ('Parent::Child')."""
    d = Rhino.RhinoDoc.ActiveDoc
    index = d.Layers.FindByFullPath(path, -1)
    if index < 0:
        return []
    # `FindByLayer(str)` matches the layer's NAME, not its path. For
    # "GroundMaterials::Ground_asphalt" the name is only "Ground_asphalt", so
    # passing the path returns NOTHING -- while FindByFullPath above SUCCEEDS,
    # so a guard on it passes and the caller gets [] with no error. Pass the
    # LAYER OBJECT. This is Rhino behaviour, not analysis-specific: it applies
    # to every nested layer you read, in every component.
    return list(d.Objects.FindByLayer(d.Layers[index]) or [])

def select_in_aoi(path, aoi):
    """Objects whose BBOX overlaps the AOI. Per-object only -- no per-triangle
    work, which is what keeps dragging the AOI box interactive."""
    hits = []
    for o in objects_on_layer(path):
        bb = o.Geometry.GetBoundingBox(True)
        if bb.IsValid and not (bb.Max.X < aoi[0] or bb.Min.X > aoi[2] or
                               bb.Max.Y < aoi[1] or bb.Min.Y > aoi[3]):
            hits.append(o)
    return hits

def aoi_bbox_from_layer(path="BoundingBox"):
    """(x0, y0, x1, y1) of everything on the AOI layer, in local metres."""
    boxes = [o.Geometry.GetBoundingBox(True) for o in objects_on_layer(path)]
    boxes = [b for b in boxes if b.IsValid]
    if not boxes:
        return None                       # warn; do NOT analyse the whole city
    return (min(b.Min.X for b in boxes), min(b.Min.Y for b in boxes),
            max(b.Max.X for b in boxes), max(b.Max.Y for b in boxes))

def mesh_to_flat(mesh, dx, dy):
    """Rhino Mesh -> {"coordinates": [...], "indices": [...]}.

    BULK overloads, not per-item loops: every RhinoCommon call crosses
    CPython<->.NET, and a 100k-vertex mesh is 10^5 crossings the slow way.
    Round to millimetres -- 24% smaller payload, measured, and finer than any
    sensor grid.
    """
    xf = mesh.Vertices.ToFloatArray()               # flat [x,y,z, x,y,z, ...]
    coords = [0.0] * len(xf)
    for i in range(0, len(xf), 3):
        coords[i]     = round(xf[i] + dx, 3)
        coords[i + 1] = round(xf[i + 1] + dy, 3)
        coords[i + 2] = round(xf[i + 2], 3)
    return {"coordinates": coords,
            "indices": list(mesh.Faces.ToIntArray(True))}   # True = triangulate
```

### Toggle latching, colour, draping and baking

```python
def rising_edge(sticky, scope, run):
    """True only on the solve where `run` goes False -> True."""
    key = scope + "::prev"
    prev, now = bool(sticky.get(key, False)), bool(run)
    sticky[key] = now
    return now and not prev


# 256-entry LUT built once. Color.FromArgb is a marshalled static call and a
# 512x512 grid needs one per vertex -- 262,144 crossings just to colour it.
_LUT = None
# magma: perceptually uniform, monotonic lightness, and what the Infrared
# platform renders -- so the component and the web app agree.
_MAGMA = ((0.0, (0, 0, 4)), (0.25, (79, 18, 123)), (0.5, (181, 54, 122)),
          (0.75, (251, 135, 97)), (1.0, (252, 253, 191)))
# spectral: the familiar blue->yellow->red reading, muted. NOT uniform -- it is
# diverging, so it is lightest in the middle and measures MORE lightness
# reversals than jet (182 vs 174). A deliberate aesthetic choice, not a
# neutral one.
_SPECTRAL = ((0.0, (94, 79, 162)), (0.25, (102, 176, 190)),
             (0.5, (230, 245, 152)), (0.75, (253, 174, 97)),
             (1.0, (213, 62, 79)))
_RAMPS = {"magma": _MAGMA, "spectral": _SPECTRAL}


def _ramp(t, stops):
    if t <= 0: return stops[0][1]
    if t >= 1: return stops[-1][1]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(round(a + (b - a) * f)) for a, b in zip(c0, c1))
    return stops[-1][1]


def colour_of(v, lo, hi):
    """Perceptually-uniform ramp. Do NOT hand-roll blue-cyan-yellow-red: its
    lightness reverses 174 times over 512 samples (magma: 0), and every
    reversal renders two different values at the same lightness -- a smooth
    gradient grows a visible band that is not in the data."""
    global _LUT
    if _LUT is None:
        stops = _RAMPS.get(PALETTE, _MAGMA)
        _LUT = [sd.Color.FromArgb(255, *_ramp(i / 255.0, stops))
                for i in range(256)]
    if hi <= lo:
        return _LUT[128]
    t = (v - lo) / (hi - lo)
    return _LUT[max(0, min(255, int(t * 255)))]


def drape_onto(mesh, terrain):
    """Move each vertex down onto the terrain. A result grid carries VALUES,
    not heights -- render it as-is and it floats as a flat sheet."""
    if terrain is None:
        return mesh
    for i in range(mesh.Vertices.Count):
        p = mesh.Vertices[i]
        for d in (rg.Vector3d(0, 0, -1), rg.Vector3d(0, 0, 1)):
            t = rg.Intersect.Intersection.MeshRay(
                terrain, rg.Ray3d(rg.Point3d(p.X, p.Y, p.Z), d))
            if t >= 0:
                hit = rg.Point3d(p.X, p.Y, p.Z) + d * t
                mesh.Vertices.SetVertex(i, hit.X, hit.Y, hit.Z + 0.15)
                break
    return mesh


def bake(meshes, layer_name, colour=(120, 160, 255)):
    """-> count baked. Replaces whatever was on the layer."""
    doc = Rhino.RhinoDoc.ActiveDoc
    idx = doc.Layers.FindByFullPath(layer_name, -1)
    if idx < 0:
        lay = Rhino.DocObjects.Layer()
        lay.Name = layer_name
        lay.Color = sd.Color.FromArgb(255, *colour)
        idx = doc.Layers.Add(lay)
    else:
        for o in (doc.Objects.FindByLayer(layer_name) or []):
            doc.Objects.Delete(o, True)
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = idx
    # Meshes carry per-vertex colours; tell Rhino to display them.
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    n = 0
    for m in meshes:
        if m is None:
            continue
        # AddMesh signals failure by returning Guid.Empty, with NO exception.
        # Without this check the only symptom of an invalid mesh is
        # "baked 0 object(s)" after a successful, paid-for analysis.
        if doc.Objects.AddMesh(m, attrs) != System.Guid.Empty:
            n += 1
        else:
            ok, why = m.IsValidWithLog()
            Rhino.RhinoApp.WriteLine("[bake] refused: %s" % (why or "?"))
    doc.Views.Redraw()
    return n
```

### Fusing stacked massing

```python
STACK_OVERLAP, STACK_GAP_M = 0.5, 3.0


def merge_stacked(objs, mergeable=None):
    """Group podium+tower solids into one building. -> [[obj, ...], ...]

    Union-find over footprint overlap AND vertical contiguity. Both are
    required: overlap alone fuses neighbours that merely touch; contiguity
    alone fuses unrelated solids at similar heights.
    """
    allow = None if mergeable is None else set(id(o) for o in mergeable)
    boxes = [o.Geometry.GetBoundingBox(True) for o in objs]
    parent = list(range(len(objs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell, buck = 60.0, {}
    for i, b in enumerate(boxes):
        if not b.IsValid or (allow is not None and id(objs[i]) not in allow):
            continue                        # cannot merge -> do not index it
        for gx in range(int(b.Min.X // cell), int(b.Max.X // cell) + 1):
            for gy in range(int(b.Min.Y // cell), int(b.Max.Y // cell) + 1):
                buck.setdefault((gx, gy), []).append(i)

    for i, a in enumerate(boxes):
        if not a.IsValid or (allow is not None and id(objs[i]) not in allow):
            continue
        near = set()
        for gx in range(int(a.Min.X // cell), int(a.Max.X // cell) + 1):
            for gy in range(int(a.Min.Y // cell), int(a.Max.Y // cell) + 1):
                near.update(buck.get((gx, gy), ()))
        for j in near:
            if j <= i:
                continue
            b = boxes[j]
            w = min(a.Max.X, b.Max.X) - max(a.Min.X, b.Min.X)
            h = min(a.Max.Y, b.Max.Y) - max(a.Min.Y, b.Min.Y)
            if w <= 0 or h <= 0:
                continue
            up, lo_ = (a, b) if a.Min.Z >= b.Min.Z else (b, a)
            area_up = max(1e-9, (up.Max.X - up.Min.X) * (up.Max.Y - up.Min.Y))
            if (w * h) / area_up < STACK_OVERLAP:
                continue
            # ONE-SIDED on purpose: a tower routinely starts INSIDE its podium
            # (base 207.8 m on a podium topping at 213.1 m), so requiring the
            # base to meet the top within a tolerance rejects most real stacks.
            if up.Min.Z < lo_.Min.Z + STACK_GAP_M:
                continue                    # not meaningfully above it
            if up.Min.Z > lo_.Max.Z + STACK_GAP_M:
                continue                    # floats clear of it
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

    groups = {}
    for i in range(len(objs)):
        groups.setdefault(find(i), []).append(objs[i])
    return list(groups.values())
```

`buildings_payload` then flattens each GROUP into one mesh, keyed by the
**lowest** object's name — that object carries the base at grade, which is what
terrain alignment seats the whole stack by.

### Step 2 — the coordinate frame

**This is the step most likely to be invented badly, and nothing else works
without it.** A Rhino model is in local metres with an arbitrary origin; the
API wants WGS84 lon/lat. You need both directions: forward to build the AOI
polygon and the weather lookup, inverse to place the returned grid back in the
document.

```python
import math

# Rhino's "unset double" -- EarthAnchorPoint reads back as this when nobody
# has set it, which is most documents.
_UNSET = 1.0e100


def document_anchor():
    """(lon, lat) from the document's EarthAnchorPoint, or None if unset.

    This is Rhino's NATIVE georeference, so honouring it means the component
    works on any model rather than only one whose origin you hardcoded. Set it
    in Rhino with the EarthAnchorPoint command.
    """
    d = Rhino.RhinoDoc.ActiveDoc
    try:
        eap = d.EarthAnchorPoint
        lat = float(eap.EarthBasepointLatitude)
        lon = float(eap.EarthBasepointLongitude)
    except Exception:
        return None
    if abs(lat) > 90.0 or abs(lon) > 180.0:      # sentinel or garbage
        return None
    return lon, lat


class Frame(object):
    """local metres <-> WGS84, anchored at (lon0, lat0).

    Tangent-plane projection with latitude-correct scale factors. Sub-metre
    over a few km, which is finer than any sensor grid -- but it ignores grid
    convergence, so error grows with distance from the anchor (order 0.16 m/km
    at HK latitudes).

    PRODUCTION: prefer the city's projected CRS via `pyproj` and fall back to
    this. Two rules if you do:
      - build BOTH transformers and require BOTH to succeed. One exact
        direction plus one approximate stops the round-trip being a no-op while
        still LOOKING exact, and the caller has no other signal.
      - expose WHICH you got (an `exact` flag and a `warnings` list) and log
        it. A frame that silently degraded is a whole class of quiet error.

    Also CACHE the frame: constructing pyproj transformers costs milliseconds,
    and an uncached frame pays that on every drag-frame re-solve.
    """

    def __init__(self, lon0, lat0):
        self.lon0, self.lat0 = float(lon0), float(lat0)
        phi = math.radians(self.lat0)
        # metres per degree, from the standard series
        self._m_lat = (111132.92 - 559.82 * math.cos(2 * phi)
                       + 1.175 * math.cos(4 * phi))
        self._m_lon = (111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi))

    def to_wgs84(self, x, y):
        """local metres -> (lon, lat). GeoJSON order, per RFC 7946."""
        return (self.lon0 + x / self._m_lon, self.lat0 + y / self._m_lat)

    def to_local(self, lon, lat):
        """(lon, lat) -> local metres. Needed to place the result grid, which
        comes back in lon/lat, into the document's frame."""
        return ((lon - self.lon0) * self._m_lon,
                (lat - self.lat0) * self._m_lat)

    def aoi_polygon(self, x0, y0, x1, y1):
        """AOI rectangle -> GeoJSON Polygon.

        COUNTER-CLOCKWISE and explicitly CLOSED (first point repeated). Note
        the coordinate order is [lon, lat] -- putting lat first is the single
        most common bug against this API and it fails as a wrong LOCATION, not
        as an error.
        """
        ring = [self.to_wgs84(x0, y0), self.to_wgs84(x1, y0),
                self.to_wgs84(x1, y1), self.to_wgs84(x0, y1)]
        ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}
```

Wire it from the anchor, and fail loudly rather than guessing:

```python
anchor = document_anchor()
if anchor is None:
    raise RuntimeError(
        "No EarthAnchorPoint on this document. Run Rhino's EarthAnchorPoint "
        "command, or wire lon/lat Panels -- do NOT guess an origin.")
frame = Frame(*anchor)
```

### `build_payload` — the one canonical version

The skeleton calls this; it is the only place weather and payload are
constructed. Two details that are easy to get wrong:

```python
def build_payload(aoi, origin, terrain, hills, api_key, frame):
    """-> (payload, polygon, lat, lon)"""
    from infrared_sdk import InfraredClient
    from infrared_sdk.models import TimePeriod, extract_weather_fields
    from infrared_sdk.analyses.types import (
        AnalysesName, SolarRadiationModelRequest)

    polygon = frame.aoi_polygon(*aoi)
    ring = polygon["coordinates"][0]
    lon = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
    lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)

    # SINGLE MONTH. A multi-month window passes validation and then fails
    # server-side: the sun-vector generator does not honour it.
    tp = TimePeriod(start_month=DEFAULT_MONTH, start_day=1, start_hour=8,
                    end_month=DEFAULT_MONTH, end_day=28, end_hour=18)

    conn = InfraredClient(api_key=api_key, base_url=BASE_URL)
    try:
        stations = conn.weather.get_weather_file_from_location(
            lat=lat, lon=lon, radius=50)
        if not stations:
            raise RuntimeError("no EPW station within 50 km")
        # The SAME TimePeriod must go to the filter AND the payload.
        weather = conn.weather.filter_weather_data(
            identifier=stations[0]["uuid"], time_period=tp)
    finally:
        conn.close()

    # extract_weather_fields lives in infrared_sdk.models, and it takes the
    # FIELD LIST as its second argument -- solar-radiation needs exactly these
    # two. Omitting the list does not give you "all of them".
    accum = extract_weather_fields(
        weather, ["diffuseHorizontalRadiation", "directNormalRadiation"])

    payload = SolarRadiationModelRequest(
        analysis_type=AnalysesName.solar_radiation,
        latitude=lat, longitude=lon, time_period=tp,
        analysis_surfaces="all",
        surface_grid_size=SURFACE_GRID,
        emit_cell_tris=DEFAULT_PRETTY,
        ground_geometry={"terrain": terrain} if terrain else None,
        context_geometry={"far": hills} if hills else None,
        terrain_alignment="auto-align",
        **accum,
    )
    return payload, polygon, lat, lon
```

### Joining and keying geometry

```python
def joined_flat(objs, origin):
    """Several Rhino meshes -> ONE flat mesh dict, or None."""
    out = rg.Mesh()
    for o in objs:
        m = o.Geometry if isinstance(o.Geometry, rg.Mesh) else None
        if m is not None:
            out.Append(m)
    return mesh_to_flat(out, -origin[0], -origin[1]) if out.Faces.Count else None


def buildings_payload(objs, origin, mergeable=None):
    """-> ({name: flat mesh}, skipped, fused).

    Fuses each stacked group into ONE building keyed by the LOWEST object's
    name -- that object carries the base at grade, which is what terrain
    alignment seats the whole stack by.
    """
    out, skipped, fused = {}, 0, 0
    for i, group in enumerate(merge_stacked(list(objs), mergeable)):
        ranked = sorted(
            group, key=lambda o: o.Geometry.GetBoundingBox(True).Min.Z)
        coords, indices = [], []
        for o in ranked:
            m = o.Geometry if isinstance(o.Geometry, rg.Mesh) else None
            if m is None or m.Faces.Count == 0:
                skipped += 1
                continue
            part = mesh_to_flat(m, -origin[0], -origin[1])
            base = len(coords) // 3
            coords.extend(part["coordinates"])
            indices.extend(v + base for v in part["indices"])
        if not indices:
            continue
        fused += len(ranked) - 1
        # Loop until unique. A single "%s_%d" fallback still collides, and the
        # second entry SILENTLY overwrites the first -- one building vanishes
        # from a billed payload with no error and no bump to `skipped`.
        name = ranked[0].Attributes.Name or "obj_%d" % i
        key, n = name, 0
        while key in out:
            n += 1
            key = "%s__%d" % (name, n)
        out[key] = {"coordinates": coords, "indices": indices}
    return out, skipped, fused
```

### The budget helper

Written against public API only — the constants below mirror documented server
limits rather than importing private SDK internals, which would break on any
refactor.

```python
# The server refuses a job that would synthesize more than this many sensors.
MAX_SYNTH_SENSORS = 262_144
# The SDK's own batch budget is this cap less a 10% safety margin.
DEFAULT_SENSOR_BUDGET = MAX_SYNTH_SENSORS * 0.9          # 235,930

# How badly a surface-area estimate UNDER-counts what the server actually
# synthesizes. Measured 1.88 / 1.97 / 2.09 against three real jobs -- the
# server grids each surface separately and rounds up, so every small facet
# costs at least one whole cell. Round UP.
ESTIMATOR_UNDERCOUNT = 2.1
ESTIMATOR_CEILING = MAX_SYNTH_SENSORS / ESTIMATOR_UNDERCOUNT * 0.85   # ~106,000


def estimate_sensors(mesh, grid):
    """Surface area / grid^2 -- the same shape the SDK's own estimator uses.

    Deliberately inlined rather than imported: it is four lines, and it makes
    visible WHY it under-counts (it assumes perfect packing, the server does
    not).
    """
    co, ix = mesh.get("coordinates") or [], mesh.get("indices") or []
    if not co or not ix:
        return 0.0
    pts = [(co[i], co[i + 1], co[i + 2]) for i in range(0, len(co), 3)]
    area = 0.0
    for i in range(0, len(ix), 3):
        try:
            a, b, c = pts[ix[i]], pts[ix[i + 1]], pts[ix[i + 2]]
        except IndexError:
            return 0.0
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        area += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return area / (grid * grid)

def sensor_budget(buildings, grid, per_job):
    """Budget that puts about `per_job` buildings in one job."""
    ests = [estimate_sensors(m, grid) for m in buildings.values()]
    if not ests or sum(ests) <= 0:
        return None                                  # leave the SDK's default
    mean = sum(ests) / len(ests)
    # DEFAULT_SENSOR_BUDGET is a hard ceiling: resolve_sensor_batch_cap
    # REJECTS anything above it, so clamp rather than raise.
    return min(mean * per_job, DEFAULT_SENSOR_BUDGET, ESTIMATOR_CEILING)
```

