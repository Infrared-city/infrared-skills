# Interior analysis — daylight factor

`daylight-factor` measures daylight at each point *inside* a room, as a percentage of unobstructed
outdoor illuminance. The CIE overcast sky is time-independent, so it takes no time period and no
weather.

## Not an area model

No polygon, no tiling, no merge — you supply the geometry. Submit via `client.analyses.execute()`;
`run_area()` rejects it.

```python
from infrared_sdk import (
    AnalysesName,
    DaylightFactorModelRequest,
    InfraredClient,
    to_interior_entity,
)

job = client.analyses.execute(payload=DaylightFactorModelRequest(
    analysis_type=AnalysesName.daylight_factor,
    barriers=room_barriers,      # dict of entities, NOT a list
    openings=windows,
    sensor_points=points,
))
client.jobs.wait_for_completion(job.job_id)
```

## 1. The entity shape

Interior entities are **nested** — unlike the six outdoor grid models, which take flat meshes:

```jsonc
{"geometry": {"payload": {"coordinates": [...], "indices": [...]}}}   // interior
{"coordinates": [...], "indices": [...]}                              // outdoor
```

**The flat shape is not rejected server-side.** The entity is read as having no geometry, skipped,
and the analysis runs against an empty occluder — a near-uniform, meaningless field returned with
HTTP 200. The signature is a perfectly uniform field — since the 2026-08 server change (lambda-models#234/#239) at ~0 % rather than the old 2 % floor. `to_interior_entity()` converts, and the
SDK rejects the flat form for you.

**Two fields are the exception and take the FLAT shape:** `ground_geometry` and `vegetation`. One
payload carries both conventions.

| field | shape |
|---|---|
| `barriers`, `openings`, `context_geometry`, `sensor_surfaces`, `buildings[*]` | nested |
| `ground_geometry`, `vegetation` | flat |

## 2. Geometry recipe

Every mesh is a triangle soup: flat `coordinates` (x,y,z triples) plus `indices` in threes.

```python
from infrared_sdk import to_interior_entity

def quad(p0, p1, p2, p3):
    return {"coordinates": [c for p in (p0, p1, p2, p3) for c in p],
            "indices": [0, 1, 2, 0, 2, 3]}

W, D, H = 6.0, 6.0, 3.0                  # metres — no unit conversion happens anywhere

barriers = {
    "floor":      to_interior_entity(quad((0,0,0), (W,0,0), (W,D,0), (0,D,0))),
    "ceiling":    to_interior_entity(quad((0,0,H), (W,0,H), (W,D,H), (0,D,H))),
    "wall-south": to_interior_entity(quad((0,0,0), (W,0,0), (W,0,H), (0,0,H))),
    "wall-north": to_interior_entity(quad((0,D,0), (W,D,0), (W,D,H), (0,D,H))),
    "wall-west":  to_interior_entity(quad((0,0,0), (0,D,0), (0,D,H), (0,0,H))),
    "wall-east":  to_interior_entity(quad((W,0,0), (W,D,0), (W,D,H), (W,0,H))),
}

# Windows are `openings`, not holes. Keep the wall; place the aperture in its
# plane, nudged a hair inside so it clearly belongs to that surface.
openings = {"window-south": to_interior_entity(
    quad((2, 0.01, 0.9), (4, 0.01, 0.9), (4, 0.01, 2.9), (2, 0.01, 2.9)),
    opening_factor=0.7)}

# Sensors: [x, y, z] at the working plane (0.8 m), on cell centres.
PITCH = 0.5
sensors = [[x*PITCH + PITCH/2, y*PITCH + PITCH/2, 0.8]
           for x in range(int(W/PITCH)) for y in range(int(D/PITCH))]
```

**Enclose the room.** A missing wall is a hole the sky pours through — the run succeeds and the
number is simply too high.

**Cover the whole floor at a uniform pitch, and keep every point inside the room.** On the
`sensor_points` tier the analysed floor area is inferred from the sensor cloud — never from the
barrier mesh — so the grid changes the daylight factor itself, not just its resolution. Points are
*not* checked against the room envelope: a handful of stray points outside the walls shifts the
inferred pitch and biases **every** sensor, including the legitimate interior ones. Measured: six
stray points moved the mean of 144 valid sensors by +17%.

### From meshes you already have

Rhino/Grasshopper, IFC, dotbim and `client.buildings.get_area()` all produce the **flat** shape:

```python
from infrared_sdk import interior_entities, to_interior_entity

wall    = to_interior_entity(existing_mesh)                        # one mesh
context = interior_entities(client.buildings.get_area(polygon))    # a whole map
```

`to_interior_entity()` accepts flat dicts, `DotBimMesh`, or already-nested entities, and preserves
what is already on them — safe to call on a partly-prepared scene.

Check imported geometry: metres · finite coordinates (a stray `NaN` is an opaque 500) · indices
within the coordinate array (out of range is a *billed* error) · triangulated · **one frame for
everything**. `get_area()` returns polygon-bbox-SW metres while your room is in whatever frame you
authored it in; mixing them misplaces the neighbours with no error.

## 3. Per-window glazing — the main lever

`openingFactor` is visible-light transmittance, set **per opening**:

```python
openings = {
    "window-south": to_interior_entity(south, opening_factor=0.9),   # clear
    "window-north": to_interior_entity(north, opening_factor=0.1),   # tinted
}
```

Glazing is read **only from `openings`** — an aperture filed under `barriers` or `context_geometry`
is fully opaque, and the result is a flat field rather than an error.

Measured once (pre-2026-08 server) on a single test room, identical windows on opposite walls at
0.9 / 0.1: half-field means of 8.20 and 3.51. Treat the ratio as indicative, not the absolute
values — both included the since-removed 2 % floor, so absolute numbers read lower today and the
glazing ratio reads truer (the floor compressed it). The wire key is exactly `openingFactor` — any other spelling is ignored and the window
silently becomes a **clear pane (1.0)**. Valid range `[0, 1]`; there is no server-side clamp, so an
out-of-range value yields a daylight factor above 100 % or below zero.

**Two different scopes — do not flatten them:** `openingFactor` is per *opening*, while
`room_reflectances` / `window_area` / `exterior_ground_reflectance` are per *request*. Note
`exterior_ground_reflectance` is accepted but currently has NO effect (since lambda-models#239; a
work-plane sensor cannot see the ground directly — reactivation tracked in lambda-models#241), so
sweeping it produces distinct billed runs with identical results. **Set
`window_area` to your real glazing area** — it feeds the internally-reflected term and is not
derived from your `openings`; omitting it silently uses a hardcoded 2.0 m². Reflectance keys are exactly `floor` / `walls` / `ceiling` — a
misspelled key silently uses the default (0.2 / 0.5 / 0.7).

**`window_area` does not control how much light enters, and on a big room it barely moves the
number.** Light in comes from the `openings` geometry and its `openingFactor`, which is what
the raytracer sees. `window_area` feeds one term — the split-flux internally reflected
component, a single scalar added uniformly to every sensor:

```
DF = (SC + ERC + IRC) / 10,000 lux x 100
IRC = mean(SC) x window_area x rho_avg / (floor_area x (1 - rho_avg))
```

Since 2026-08 (lambda-models#239), ERC is *traced*: buildings seen through your `openings`
re-emit 10 % of the sky they hide. It is 0 for a sealed room, 0 without `openings`, and it no
longer adds a flat `exterior_ground_reflectance x 10` floor to every sensor.

Its effect therefore scales with `window_area / floor_area`. Measured on staging, taking
`window_area` from 2 to 16 m² (8x) with everything else fixed: an 8 x 8 m room moved
**5.65% -> 6.33%** (+0.68), a 16 x 16 m room **2.97% -> 3.01%** (+0.05). Both match the
formula to four decimals — the flat response on a deep plan is arithmetic, not a defect. To
model more glazing, change the `openings` mesh or `openingFactor`; set `window_area` so the
reflected term is right. `room_reflectances` scales the same term and dilutes the same way.

## 4. Surrounding buildings

`context_geometry` is how neighbours shade the room. Omitting it does not error — the room just
reads brighter than it is. The effect is entirely scene-dependent: three close 20 m blocks cut mean
DF **29 %**, while 1570 real Vienna buildings around the same room cut it only **3 %**. Never quote
a fixed figure.

## 5. Measurement tiers

| tier | result shape |
|---|---|
| `sensor_points` | `{"output": [{x,y,z,df}], "min-legend", "max-legend"}` |
| `sensor_surfaces` | `{"surfaces": {sid: …}}` |
| `floors` | `{"floors": {"0": …}}` |
| `buildings` | `{"buildings": {bid: {"floors": {…}}}}` |

Dispatch is `sensor_points` → `sensor_surfaces` → `buildings` → `floors`; the **first key present
wins** and the rest are ignored. Supplying two selectors therefore analyses something other than
what you asked for — the SDK rejects that rather than letting it run.

The `floors` and `buildings` tiers additionally require barriers carrying `category="floor"` **with
`position`/`rotation`**, also checked before submitting.

Note `buildings` is *not* a competing selector when sensors are present — it supplies the occluder.
But a non-empty `buildings` **does** take over the occluder on every tier, so top-level `barriers`
alongside it are silently dropped server-side.

**Caps.** The SDK is the source of truth — read them from it rather than trusting a number
written here, which goes stale the moment the limits move:

```python
from infrared_sdk.analyses.types import (
    MAX_FLOORS_PER_REQUEST,     # floors summed across ALL buildings
    MAX_SENSORS_PER_FLOOR,
    MAX_OCCLUDER_TRIANGLES,     # across barriers + openings + context + ground + vegetation
)
```

At the time of writing those are 15 / 100,000 / 2,000,000. The sensor-surface count is capped
by `MAX_FLOORS_PER_REQUEST` too, so it moves with it.

The SDK checks all of them before submitting, because the cap is enforced *after* the job is
charged: an over-cap request is accepted, billed, and only then refused with a 422. Checking
locally is free; finding out from the API is not.

## 6. Reading the result

Results are a ZIP:

```python
from infrared_sdk.analyses.jobs import JobsServiceClient

result = JobsServiceClient.decompress(client.jobs.download_results(job.job_id).content)
values = [p["df"] for p in result["output"]]
assert len(set(values)) > 1, "uniform field — the occluder was empty"
```

**Always check for a uniform field in a room that HAS `openings`** — it is the one failure that
looks like a success (a deliberately sealed or opening-less room correctly returns uniform 0.0;
that is the answer, not a failure). Reading bands since the 2026-08 server change (the old 2 %
floor is gone, so deep sensors read lower): under ~1 % is dim, ~1.5–4 % normal for a daylit room,
> 4–5 % generously glazed — and values should fall off sharply away from the aperture. A flat
nonzero field, or an implausibly dark field with an intact gradient (a misaligned neighbour
pressed against the window), means something never reached the model correctly.

Compute is fast (~0.1 s); the wait is queue time (~20 s). Payload size is not the driver, so there
is nothing to gain from splitting a request that already fits.
