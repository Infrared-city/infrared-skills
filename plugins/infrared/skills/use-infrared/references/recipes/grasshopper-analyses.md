# Facade, terrain and interior analyses in Grasshopper

**What each analysis needs**, on top of the shared component shape. Read
[`grasshopper-component-shape.md`](grasshopper-component-shape.md) first — the
mode decision, the 12-step sequence and every helper called here live there.

| | A — facade | B — terrain | C — interior |
|---|---|---|---|
| analysis | `solar-radiation` + `analysis_surfaces` | `thermal-comfort-index` | `daylight-factor` |
| result | one mesh per building | one ground mesh, draped | coloured sensors per floor |
| you send | buildings, terrain, far hills | + trees, ground materials | floors, walls, windows you **synthesise** |
| the hard part | sensor caps and batching | vegetation/materials reaching the payload | the request shape — every mistake is billed |
| typical run | 12 jobs, 13 s server | 4 jobs, ~40 s | 3–4 jobs, minutes |

---

# Blueprint A — facade (`solar-radiation` on surfaces)

## A1. What each setting means

**The values live in the skeleton's `SETTINGS` block in
[`grasshopper-component-shape.md`](grasshopper-component-shape.md) — one
place, once.**
This section explains them; it deliberately does not re-declare them. Two
copies of a constant is how `DEFAULT_PRETTY` ended up `True` here and "start
with it OFF" three sections later.

Settings, not sockets: a socket is a support question, a constant is a
documented decision.

| constant | value | why that value |
|---|---|---|
| `SITE` | `"midlevels"` | only a label if you read the anchor from the document |
| `DEFAULT_MONTH` | `4` | **single month.** A multi-month window passes validation and then fails server-side — the sun-vector generator does not honour it |
| `DEFAULT_SURFACES` | `"facades"` | walls only. `"all"` adds roofs, which is what makes a render look like a building study — but roofs sit **~6.6× higher**, so including them forces the facade-population legend (A7) or every wall renders one shade. `""` gives the flat ground grid instead |
| `DEFAULT_PRETTY` | `False` | `emit_cell_tris`. Exact clipped per-cell geometry: crisper footprint edges and **~90% of the response body**. Values are identical either way, so iterate with it off and turn it on for the final image |
| `SURFACE_GRID` | `2.0` | facade sensor pitch, metres. Sensors scale with the **square** of this |
| `BUILDINGS_PER_JOB` | `100` | **a correctness knob, not a performance one** — see below |
| `SUBMIT_WORKERS` | `8` | each payload is tens of MB; 20 in flight can saturate an uplink |
| `USE_TERRAIN` | `True` | sends the `Terrain` layer as `ground_geometry` |
| `FAR_HILLS` | `True` | sends `Terrain_Context` as `context_geometry`. Worth it for facades (+7.8° of eastern horizon at height), near-irrelevant at street level |
| `LEGEND_PERCENTILE` | `99.5` | of **facade** values only (A7) |
| `PALETTE` | `"magma"` | perceptually uniform. `"spectral"` for the familiar blue→red look, knowing it is not (component-shape) |

**Why `BUILDINGS_PER_JOB` is a correctness knob.** The server caps a job at
262,144 synthesized sensors and 422s **above** it — after the job has run and
been billed, which then fails the merge of every sibling job. And the SDK's
estimator **under-counts by ~2×** (measured 1.88–2.09× against three real
jobs), so its own default budget of 235,930 *estimated* is ~470,000 *actual*.
The default path cannot submit a dense facade job. Size it yourself; `A6`'s
`sensor_budget` (component-shape) applies the correction.

## A3. Read geometry (steps 3–5)

```python
aoi = aoi_bbox_from_layer("BoundingBox")        # (x0, y0, x1, y1) local metres
building_objs = select_in_aoi("Buildings", aoi)
objs = building_objs + select_in_aoi("Infrastructure", aoi)
```

**Merge stacked massing before anything else.** Dense-Asian city models
routinely model a podium and its tower as separate solids — measured 1,011 of
1,877 objects (54%) sitting on another object, many at 100% footprint overlap.
`auto-align` re-bases every solid onto the terrain beneath it, so a tower
based at +188 m on a podium topping at +190 m is dragged to grade. Measured
displacements: **−43 m to +45 m.**

```python
# Only BUILDINGS may fuse. An elevated road's bbox spans hundreds of
# buildings and, being above grade, satisfies the stacking test against every
# one — union-find then chains whole districts into a single "building"
# (measured groups of 420 and 179 before this filter).
buildings, skipped, fused = buildings_payload(
    objs, origin, mergeable=building_objs)
```

## A4. Payload (steps 8–9)

Two traps in one call:

```python
# 1. `from_weatherfile_payload` has NO passthrough for analysis_surfaces /
#    surface_grid_size / ground_geometry / terrain_alignment. Extract the
#    weather fields yourself and construct directly.
#    SolarRadiationModelRequest is FROZEN, so you cannot set them afterwards
#    even if you wanted to. (Verified by execution: Utci/Tcs requests are
#    NOT frozen — a weather mixin sets frozen=False and wins the base merge.
#    Construct in one call anyway -- B6 publishes UTCI's seven weather field
#    names so that is actually possible for it too, not just advice.)
# 2. terrain_alignment MUST be "auto-align". "assume-aligned" moves nothing
#    but 422s the WHOLE job for any base outside ±1 m of terrain. On
#    separately-sourced buildings + DTM only ~18% of objects qualify, and
#    ~22% AFTER the stack merge in A3 -- so even having fixed the stacking,
#    this mode is still not usable. The residual is DTM sampling: a footprint
#    spanning a slope cannot have every base vertex within 1 m of a 5 m DTM.
# The full constructor, including the weather fetch it depends on, is
# build_payload() in grasshopper-component-shape.md. Written once
# there; do not re-derive it.
```

`ground_geometry` and `context_geometry` are `{id: flat_mesh}` maps and the ids
are **yours** — `"terrain"` and `"far"` below are arbitrary labels, not a
schema. They come back in the result keys, so name them something you would
want to read.

**Does this replace the SDK's own splitting, or stack with it?** It
*parameterises* it. `run_area_and_wait` tiles the polygon and then splits each
facade tile into sub-jobs itself; `max_sensors_per_job` is the budget it uses
to decide where to split. You are not batching separately and you are not
disabling anything — you are correcting a budget whose default is unusable.
Keep using `run_area_and_wait`. `SUBMIT_WORKERS` is passed as its
`max_workers`, which is how many tile submissions go out concurrently.

Then size the budget from the buildings, and force the S3 upload route:

```python
budget = sensor_budget(buildings, SURFACE_GRID, BUILDINGS_PER_JOB)   # A6

# A zip landing JUST UNDER 5 MiB is POSTed inline and refused with
# 413 {"message": "Request Too Long"} — non-retryable, so the SDK gives up on
# attempt 1/3 and the surface merge aborts with siblings already billed.
# Smaller zips post fine; BIGGER ones route to S3 and succeed. Only the band
# below the threshold fails. Force everything onto S3.
#
# NOTE which call this governs. Analysis-job submission routes through
# post_zip_with_big_payload, which tests the ZIPPED size — that is the one
# above. The buildings / vegetation / ground_materials / layers services use
# post_with_big_payload, which tests RAW pre-zip JSON. Same env var, different
# quantity: if you port this workaround to one of those uploads you are tuning
# against a different measurement.
os.environ.setdefault("INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES", str(1 << 20))
```

## A5. Render — one scale, and pick the right population

A facade result is **two populations, not one distribution.** Measured over
1.47M cells: facades median 8.2, roofs median 53.9 — **6.6× apart.** A shared
`0..global_max` ramp is set by the 13% of cells that are roofs, and 93% of
facade cells land in its bottom quarter: every wall renders one shade.

```python
lo, hi = 0.0, facade_percentile(result, LEGEND_PERCENTILE)      # A7
# Facade test is the z of (u_axis × v_axis). There is NO `normal` field, and
# defaulting a missing one to [0,0,1] classifies everything as roof.
```

Then **one `lo/hi` for every building**, so a colour means the same number
everywhere. Judge the scale by the fraction of **objects** affected, not cells:
4.4% of cells clipping put red on 77% of buildings.

Mesh rules that are not optional:

- **one mesh per building**, not per surface — a job returns ~19k surfaces
- **skip degenerate faces at build time**; one zero-area face invalidates the
  whole mesh and `AddMesh` then returns `Guid.Empty` silently
- **never `Compact()`** an index-built mesh — it re-indexes and desyncs colours
- build planar quads **by hand**; `MeshingParameters.Default` measured **97
  triangles on a flat 4.6 × 1.3 m rectangle**

---

## A7. The deliverable: result → one coloured mesh per building

### First, the colour scale

```python
def facade_percentile(result, pct):
    """Top of the ramp, from FACADE values only.

    Facades and roofs are two populations ~6.6x apart (medians 8.2 vs 53.9),
    so a scale taken over everything is set by the ~13% of cells that are
    roofs and renders every wall one shade.

    There is NO `normal` field on a surface. The facade test is the z
    component of u_axis x v_axis, and |z| <= 0.5 is the SDK's own threshold --
    defaulting a missing normal to [0,0,1] classifies everything as roof,
    which silently gives you the scale you were trying to avoid.
    """
    import math
    vals = []
    for surf in result.surfaces.values():
        u, v = surf.u_axis, surf.v_axis
        nz = u[0] * v[1] - u[1] * v[0]
        if abs(nz) > 0.5:
            continue                                  # roof or soffit
        for x in (surf.values or []):
            if x is not None and math.isfinite(x):
                vals.append(x)
    if not vals:
        return None                        # fall back to a fixed domain
    vals.sort()
    return vals[min(len(vals) - 1, int(pct / 100.0 * len(vals)))]
```

### Then the meshes

`result.surfaces` is a **dict** of `{"<building-id>/<surface-index>": grid}`,
and each grid carries a **UV frame** — `origin`, `u_axis`, `v_axis`,
`grid_size`, `nu`, `nv` — not coordinates and indices.

```python
def surface_result_to_mesh(result, origin_xy, lo, hi):
    """-> (meshes, problems). ONE mesh per BUILDING, not per surface."""
    ox, oy = origin_xy
    groups = {}
    # A real run returns ~19,000 surfaces. Baking that many objects is slow to
    # write, slow to draw and impossible to select -- so group by the building
    # id, which is the unit a user thinks in anyway.
    for key, surf in result.surfaces.items():
        bid = str(key).split("/")[0]
        verts, cols, faces = groups.setdefault(bid, ([], [], []))
        o, u, v = surf.origin, surf.u_axis, surf.v_axis
        step, nu, nv = surf.grid_size, int(surf.nu), int(surf.nv)
        vals = surf.grid()                       # (nv, nu), NaN where masked
        h = step / 2.0
        for j in range(nv):
            for i in range(nu):
                val = vals[j][i]
                if val is None or val != val:    # NaN: no sensor here
                    continue
                # `origin` is cell (0,0)'s CENTRE, not a corner. One quad per
                # cell, corners at +/- half a step along u and v.
                base = len(verts)
                for du, dv in ((-h, -h), (h, -h), (h, h), (-h, h)):
                    du_ = (i * step) + du
                    dv_ = (j * step) + dv
                    verts.append((o[0] + u[0]*du_ + v[0]*dv_ + ox,
                                  o[1] + u[1]*du_ + v[1]*dv_ + oy,
                                  o[2] + u[2]*du_ + v[2]*dv_))
                    cols.append(colour_of(val, lo, hi))
                faces.append((base, base + 1, base + 2, base + 3))
    meshes, problems = [], []
    for bid in sorted(groups):
        verts, cols, faces = groups[bid]
        m = rg.Mesh()
        # Bulk adds, then VERIFY the count -- a partial bulk add misaligns
        # every later face index and renders as spikes.
        added = m.Vertices.AddVertices([rg.Point3f(*p) for p in verts])
        for a, b, cc, d in faces:
            m.Faces.AddFace(a, b, cc, d)
        m.VertexColors.SetColors([sd.Color.FromArgb(255, *c) for c in cols])
        m.Normals.ComputeNormals()
        # NEVER Compact(): it drops unused vertices and RE-INDEXES the rest,
        # which the parallel colour list does not follow. Because masked cells
        # above are skipped, unreferenced vertices exist -- this is exactly the
        # case where Compact() silently shuffles the colours.
        if m.Faces.Count:
            meshes.append(m)
        else:
            problems.append((bid, "no drawable cells", 0))
    return meshes, problems
```

**`emit_cell_tris` is a real cost.** With it on, each surface also carries
exact clipped per-cell triangles — crisper footprint edges and roughly **90% of
the response body**. The UV rebuild above is geometrically identical to within
0.0 m; only the clip at surface boundaries differs. Start with it OFF while you
are still checking the setup.

# Blueprint B — terrain-level (UTCI on a ground grid)

Same skeleton. Five differences, all of which cost something.

## B1. Settings that differ

Start from A1's block and change only these. Everything else carries over.

| constant | facade (A) | terrain (B) | why it changes |
|---|---|---|---|
| `DEFAULT_SURFACES` | `"facades"` | **remove it** | UTCI rejects `analysis_surfaces` and `surface_grid_size` outright (B2) |
| `SURFACE_GRID` | `2.0` | **remove it** | same |
| `BUILDINGS_PER_JOB` | `100` | **remove it** | no surface sensors means nothing to batch |
| `LEGEND_PERCENTILE` | `99.5` of facades | `98.0` **of the data** | there is no facade population here, and the fixed domain is unusable (B4) |
| `TREES` | — | `True` | `Vegetation` **points**, never the crowns — crowns are display proxies and sending both double-counts |
| `MATERIALS` | — | `True` | the `GroundMaterials::*` sublayers (B3) |
| `TERRAIN_MARGIN_M` | — | `3000.0` | widens the terrain slice; **only** has an effect with `USE_TERRAIN` on |
| `FAR_HILLS` | `True` → `context_geometry` | `True` → **`terrain_context_margin_m`** | **the flag survives, the mechanism does not.** See below |

`PALETTE` stays `"magma"` — it is what the Infrared platform renders, so the
component and the web app show the same picture for the same quantity.

> **`UtciModelRequest` HAS NO `context_geometry` FIELD.** Verified by
> inspecting the model: solar has `ground_geometry`, `context_geometry` and
> `terrain_alignment`; UTCI has `ground_geometry` and `terrain_alignment` only.
> Copying Blueprint A's `context_geometry={"far": hills}` into a UTCI payload is
> a construction-time error, not a silent one — but you will only find it after
> writing the whole component.
>
> So there is **no separate occluder channel for UTCI.** The only lever is
> `terrain_context_margin_m`, which widens how far `ground_geometry` is sliced
> — meaning distant hills shade the site *only if they are part of the
> `Terrain` mesh you upload*. If your far terrain is a separate layer, it does
> nothing here.

## B2. No `analysis_surfaces` — and no batching

`thermal-comfort-index` **rejects** `analysis_surfaces` and
`surface_grid_size`. It produces one ground grid, so none of Blueprint A's
sensor-cap or batching machinery applies. Do not port it across; there is
nothing to batch.

## B3. Vegetation and materials — the silent one

They travel as **separate kwargs**, not payload fields:

```python
result = client.run_area_and_wait(
    payload, polygon,
    buildings=buildings,
    vegetation=trees,             # {} silently means "no trees"
    ground_materials=materials,   # {} silently means emissivity 0.97
)
```

**The trap that cost a whole run:** nested layers.
`Objects.FindByLayer(str)` matches the layer's **NAME, not its full path.**
For `GroundMaterials::Ground_asphalt` the name is only `Ground_asphalt`, so
passing the path returns nothing — while `FindByFullPath` *succeeds*, so the
guard passes and the caller sees an empty list with **no error.** Observed:
`ground materials: none` on a file holding 865 valid closed polylines, and
UTCI ran with no surface-energy inputs at all.

```python
index = doc.Layers.FindByFullPath("GroundMaterials::Ground_asphalt", -1)
objs = doc.Objects.FindByLayer(doc.Layers[index])     # the LAYER, not the path
```

Top-level layers (`Buildings`, `Terrain`, `Vegetation`) are unaffected because
name == path — which is exactly why this hides.

Ground materials go as `{material: GeoJSON FeatureCollection}` in lon/lat, and
the layers must be **mutually exclusive** — clip them so each point belongs to
one material.

## B4. The legend runs the other way

Blueprint A's ramp *saturates*; this one *flattens.* UTCI's fixed domain is
the stress-category scale, **−40…46 °C = 86 °C wide.** Measured over 683,500
cells of a July run, the real data spans **20.7–27.3 °C — 6.6 °C, or 8% of the
ramp.** The whole city renders one flat orange, which reads as "the model did
nothing."

Percentile-clip the actual values (~16× the contrast) and **say in the log
that it is auto-scaled**, because two such runs are not comparable. Expose a
pin for the case where they must be.

## B5. Drape the result

The grid carries **values, not heights** — render it flat and it floats. Drape
each vertex onto the terrain mesh with a ray. And a 512 m tile is ~78% NaN
outside the AOI, so **drop faces touching masked cells** or most of the
surface renders grey.

---

## B6. The UTCI payload — and why it is built differently

**`07-thermal-comfort-utci.md` says to use `from_weatherfile_payload` and
"don't pass them manually unless you know the schema" — and it is right, for a
plain UTCI run.** The classmethod pulls all seven weather fields for you and
you should use it.

The exception is precisely this blueprint's case: **the classmethod has no
passthrough for `ground_geometry` or `terrain_alignment`.** So for UTCI *on
terrain* you need one of two things — and since the page's caveat is "unless you
know the schema", here is the schema.

Route 1, direct construction. Preferred: one call, nothing to re-validate.

Route 2, the classmethod then merge the terrain fields in — which works only
because `UtciModelRequest` is unfrozen (verified by execution; solar's is
frozen). The reference implementation does this, and it is more fragile: it
depends on `model_dump(exclude_none=True)` round-tripping cleanly. Use it if
one code path must serve several analyses.

```python
# UTCI needs SEVEN weather fields, not solar's two.
UTCI_WEATHER = ("horizontal_infrared_radiation_intensity",
                "diffuse_horizontal_radiation",
                "direct_normal_radiation",
                "global_horizontal_radiation",
                "dry_bulb_temperature",
                "wind_speed",
                "relative_humidity")


def utci_payload(polygon, tp, weather, terrain, lat, lon, margin_m=3000.0):
    from infrared_sdk.models import extract_weather_fields
    from infrared_sdk.analyses.types import AnalysesName, UtciModelRequest

    accum = extract_weather_fields(weather, [
        "horizontalInfraredRadiationIntensity", "diffuseHorizontalRadiation",
        "directNormalRadiation", "globalHorizontalRadiation",
        "dryBulbTemperature", "windSpeed", "relativeHumidity"])

    return UtciModelRequest(
        analysis_type=AnalysesName.thermal_comfort_index,
        latitude=lat, longitude=lon, time_period=tp,
        ground_geometry={"terrain": terrain} if terrain else None,
        # auto-align, ALWAYS. "assume-aligned" moves nothing but 422s the whole
        # job for any base outside +-1 m of terrain, and separately-sourced
        # buildings and DTM never satisfy that.
        terrain_alignment="auto-align",
        # NOTE: no context_geometry. It does not exist on this model.
        **accum,
    )
```

Route 2, for completeness:

```python
base = UtciModelRequest.from_weatherfile_payload(
    payload=UtciModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_index),
    location=Location(latitude=lat, longitude=lon),
    time_period=tp, weather_data=weather)
# Unfrozen, so this round-trip is legal here and NOT on the solar model.
merged = base.model_dump(exclude_none=True)
merged.update(ground_geometry={"terrain": terrain},
              terrain_alignment="auto-align")
payload = UtciModelRequest.model_validate(merged)
```

## B7. Vegetation and ground materials — the exact contracts

Both are **separate kwargs** to `run_area_and_wait`, not payload fields, and
both fail silently: `{}` means "no trees" and "emissivity 0.97 everywhere"
rather than an error.

```python
# Attributes live in Rhino USER TEXT on each point, read with GetUserString.
# Nothing in the docs states that mechanism, and a wrong key name yields an
# empty properties dict -- trees submit, HTTP 200, and MRT is quietly wrong.
VEG_KEYS = ("height_m", "crown_m", "crown_area_m2",
            "archetype", "leaf_cycle", "lon", "lat")


def vegetation_payload(objs, frame):
    """Vegetation POINTS -> the SDK's tree list.

    Read the `Vegetation` layer, NEVER `Vegetation_Crowns` -- that is a real,
    separate layer holding ellipsoid DISPLAY proxies. The point plus its user
    text is the authoritative tree; sending crowns as well double-counts.

    `crown_m` is a DIAMETER, not a radius. Halving it by mistake shrinks every
    tree's shading by 4x in area and nothing complains.
    """
    out = []
    for o in objs:
        pt = o.Geometry.Location if hasattr(o.Geometry, "Location") else None
        if pt is None:
            continue
        props = {}
        for k in VEG_KEYS:
            v = o.Attributes.GetUserString(k)
            if v:
                props[k] = v
        # An explicit lon/lat in user text WINS over the reprojected point --
        # the source data knows better than our tangent-plane approximation.
        lon = float(props.pop("lon", 0) or 0) or None
        lat = float(props.pop("lat", 0) or 0) or None
        if lon is None or lat is None:
            lon, lat = frame.to_wgs84(pt.X, pt.Y)
        out.append({"type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": props})
    return {"type": "FeatureCollection", "features": out}


# The FIVE recognised materials, and the layer convention is
# "GroundMaterials::Ground_<material>" for every one of them -- not just the
# asphalt example the pitfalls page uses to demonstrate the FindByLayer trap.
GROUND_LAYERS = {
    "asphalt":    "GroundMaterials::Ground_asphalt",
    "concrete":   "GroundMaterials::Ground_concrete",
    "vegetation": "GroundMaterials::Ground_vegetation",
    "soil":       "GroundMaterials::Ground_soil",
    "water":      "GroundMaterials::Ground_water",
}


def ground_materials_payload(aoi, frame):
    """-> {material: GeoJSON FeatureCollection}, in lon/lat.

    Layers must be MUTUALLY EXCLUSIVE -- clip them so each point belongs to
    exactly one material, or the server stacks them in dict order.
    """
    out = {}
    for material, layer in GROUND_LAYERS.items():
        feats = []
        for obj in select_in_aoi(layer, aoi):          # the Layer-object fix
            crv = getattr(obj.Geometry, "Value", obj.Geometry)
            if crv is None or not crv.IsClosed:
                continue                               # open ring: unusable
            ok, pl = crv.TryGetPolyline()
            if not ok or pl is None or len(pl) < 4:
                continue
            ring = [list(frame.to_wgs84(p.X, p.Y)) for p in pl]
            if ring[0] != ring[-1]:
                ring.append(ring[0])                   # GeoJSON must close
            feats.append({"type": "Feature",
                          "geometry": {"type": "Polygon",
                                       "coordinates": [ring]},
                          "properties": {"material": material}})
        if feats:
            out[material] = {"type": "FeatureCollection", "features": feats}
    return out
```

Pass them through, and **log the counts** — a `0` here is the most common
silent failure in this component:

```python
result = conn.run_area_and_wait(
    payload, polygon, buildings=buildings,
    vegetation=trees or None, ground_materials=materials or None,
    terrain_context_margin_m=TERRAIN_MARGIN_M)
```

---

# Blueprint C — interior daylight (`daylight-factor`, floors tier)

The hardest of the three, and the one where every mistake is **billed**. Read
C1 before writing anything: four of the five failures below are in the request
shape, and all four submit successfully first.

## C1. The request shape — where the money goes

**Tier dispatch is by key PRESENCE, first match wins, and the rest are silently
ignored:** `sensor-points` → `sensor-surfaces` → `buildings` → `floors`. Send
`sensor_points` "just for testing" alongside `floors` and your floors are
discarded without comment.

| rule | if you get it wrong |
|---|---|
| `floors` is a list of **integer indices** (0-based, positional after the server clusters your slabs by elevation) — or floor-UUID strings. **Not** your barrier dict keys | keys like `"floor_000"` pass the SDK's own validator (indistinguishable from a UUID) and then match nothing server-side. **Billed, returns nothing** |
| floor slabs **must** carry `category="floor"` | no clustering happens; billed rejection |
| a floor barrier's `position` **and** `rotation` must be real objects | absent or `null` → **HTTP 500**, not a 422. A serializer that keeps `None` fields trips this |
| every other barrier needs **no** category | it occludes regardless — the shell goes in uncategorised |
| `barriers` / `openings` / `context_geometry` are **nested**: `{"category":…, "geometry": {"payload": {...}, "position": {...}, "rotation": {...}}}`. `ground_geometry` / `vegetation` are **flat** | a flat mesh in a nested slot is silently skipped — near-uniform field, HTTP 200 |

**The server drops small storeys, then rejects your indices.** It clusters your
`category="floor"` barriers by elevation and **discards any cluster under 20% of
the largest floor's area in that request** — a plant room, a penthouse, a small
setback. Then a `floors` list asking for an index it no longer has fails:

```
422 floor 9: floor index 9 out of range: building has 9 storey(s) (0..8)
```

The whole batch dies, billed. **Apply the same 20% rule client-side before
sending** so your indices and the server's stay in step, and log what you
dropped. A sent-vs-returned check afterwards cannot save you — nothing is
returned.

Caps, all checked before charging: **15** floors per request, **100,000**
sensors per floor, **2,000,000** occluder triangles.

## C2. You synthesise the room. There is no slicing tier

The server only *clusters* slabs you hand it. On a city model with no floors and
no windows, the client builds all of it:

```
floor slabs   -> barriers, category="floor", explicit position + rotation
walls         -> barriers, uncategorised, sealed FLOOR TO SLAB (see C3)
windows       -> openings, with openingFactor = VLT
neighbours    -> context_geometry, by RADIUS (100 m), never the whole AOI
```

**Do not send `buildings=` alongside `barriers`** — that selects a different
tier.

## C3. The two arithmetic traps that make numbers wrong, not absent

Both are silent, both are in the geometry you generate, and both were shipped.

**Seal the wall to the SLAB, not the ceiling plane.** With `storey_height 3.2`
and a ceiling at `h − 0.4 = 2.8`, tiling the wall to 2.8 leaves a **0.400 m
fully open ribbon** to the next slab: unglazed sky into the room, and not
counted in `window_area` either, so the internally reflected term is also wrong.
Measured consequence — median DF **29.7%** where 1–5% is typical. The plenum is
not a light path. Only the *window* stays inside the ceiling plane.

**Check the sensor plane against your sill.** `analysis_height` defaults to
**0.8 m**. A window band at `wwr 0.4` on a 2.8 m ceiling computes a sill of
**0.924 m** — so on the defaults every sensor sits *below* the glazing with an
opaque slab overhead, and sky access collapses to a near-horizon wedge. Pass
`analysis_height` explicitly (1.1 m clears that sill) and log both numbers.

**Windows do not need a hole in the wall.** A coincident aperture in an
unbroken wall transmits — the server's tolerance is 0.5 m and it is unit-tested.
Punch openings for realism and for variation along the wall, not to admit light.

## C4. The response, and its fixed legend

```python
{"floors": {"<index>": {"output": [{"x":…, "y":…, "z":…, "df":…}, …],
                        "min-legend": 0, "max-legend": 100}}}
```

`min-legend` / `max-legend` are **fixed constants, never data-driven.** A client
that trusts them renders a typical sub-10% field as flat. Use a 0–10% domain, or
percentile-clip — **over the ENCLOSED floors only.** One roof terrace returned a
median of 242% against a building typical of 29.7%, and letting it set the ramp
crushed thirteen real floors into one colour. Exclude floors whose median
exceeds ~3× the median of medians; they still render, clipped.

Also drop the **topmost** level: nothing encloses it from above, so it is a roof
slab looking at the sky, not a room. It returned DF > 100% — more light indoors
than outdoors.

## C5. Submitting

`JOB_TIMEOUT_S = 1200`. The SDK default of **300 s** is not enough for 15 floors
at a 0.5 m grid, and **timing out client-side neither stops nor refunds the
job** — it only discards a result you paid for.

Submit every batch before waiting on any (queue time overlaps), and gather with
`submit` + `as_completed`, **not `pool.map`** — `map` re-raises on consumption,
so one slow batch discards every batch that already landed and was billed.
Treat a failure as `None`, render what returned, and say how many are missing.

---

# Far terrain via `context_geometry` — SOLAR ONLY

**This section applies to Blueprint A.** UTCI has no `context_geometry` field
(B1), so none of it transfers — do not read the horizon gains below as
something `terrain_context_margin_m` will buy you.

Worth stating because the instinct is to send everything.

| | horizon at pedestrian level | at 60 m facade height |
|---|---|---|
| near `Terrain` only | 31.5° S | 27.3° S |
| + far hills | 31.6° S | 27.9° S |

**The Peak is already in the near terrain** — south agrees within 0.6°. Far
hills add mostly low-angle east/west: **+7.8° of eastern horizon at facade
height**, which is the morning-sun sector. Worth sending for a facade study,
nearly irrelevant at street level.

Cost: 20 m pitch is right — at 1.5 km it subtends ≈0.76°, already about the
angular width of the sun disc, so a finer pitch cannot change a shading
result. **5.1 MB** of compact JSON per batch (87,576 verts / 173,728 tris,
re-measured; earlier notes said 5.9 and 7 MB — those were a non-compact
serialisation and an estimate). `context_geometry` is **never culled** —
it is copied verbatim into every tile and every batch, so its cost is
`size × tiles × batches`. 62% of it sits below the horizon and can never shade
the AOI; a horizon cull is the obvious optimisation and is not built.

---

# Before you flip `run`

The unarmed solve exists to be looked at. Check, in this order:

1. **counts** — buildings found, stacked objects fused, trees, materials
   (a `0` or `none` here is the single most common silent failure)
2. **the projected sub-job count** — each is billed separately
3. **triangle counts** — the number that reveals a mesher quietly
   subdividing something planar; nothing else does
4. **the geometry itself, in the viewport** — bake the preview and look

Then submit, and treat the first result as a hypothesis until you have looked
at the picture. A correct simulation with a wrong colour scale is
indistinguishable from a broken one, and both of this project's most expensive
bugs returned HTTP 200.
