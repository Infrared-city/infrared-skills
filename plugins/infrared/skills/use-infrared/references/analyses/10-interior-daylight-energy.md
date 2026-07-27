# Interior analysis — daylight factor & energy balance

| Analysis | Answers | Weather? | Time period? |
|---|---|---|---|
| `daylight-factor` | daylight at each point in a room, as % of unobstructed outdoor illuminance | no | **no** — the CIE overcast sky is time-independent |
| `energy-balance` | annual heating/cooling demand per zone | no weather *file* | **no** — the climate series *is* the time input |

> 🛑 **`energy-balance` output is not currently reliable — do not use it for decisions.** Both
> `EUI_heat` and `EUI_cool` can return `0.0` for entirely ordinary buildings. Cooling is only
> computed when the monthly *mean* outdoor temperature exceeds 26 °C, so it is zero year-round in
> most European climates; the heating error peaks for well-insulated, highly glazed zones. `0.0` is
> not an error — it reads as "no demand", exactly the kind of plausible answer nobody questions, and
> the job is still billed. A model fix is in progress. **`daylight-factor` is unaffected** and
> everything below applies to it fully.

## Not area models

No polygon, no tiling, no merge — you supply the geometry. Submit via `client.analyses.execute()`;
`run_area()` rejects them.

```python
from infrared_sdk import InfraredClient, to_interior_entity
from infrared_sdk.analyses.types import AnalysesName, DaylightFactorModelRequest

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
HTTP 200. The signature is every sensor reading ≈ 107 %. `to_interior_entity()` converts, and the
SDK rejects the flat form for you.

**Two fields are the exception and take the FLAT shape:** `ground_geometry` and `vegetation`. One
payload carries both conventions.

| field | shape |
|---|---|
| `barriers`, `openings`, `spatial_volumes`, `context_geometry`, `buildings[*]` | nested |
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

**Cover the whole floor at a uniform pitch.** On the `sensor_points` tier the analysed floor area is
inferred from the sensor cloud, so a sparse or partial grid changes the daylight factor itself, not
just its resolution.

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

Measured: identical windows on opposite walls at 0.9 / 0.1 gave half-field means of **8.20** and
**3.51**. The wire key is exactly `openingFactor` — any other spelling is ignored and the window
silently becomes a **clear pane (1.0)**. Valid range `[0, 1]`; there is no server-side clamp, so an
out-of-range value yields a daylight factor above 100 % or below zero.

**Three different scopes — do not flatten them:** `openingFactor` is per *opening*;
`room_reflectances` / `window_area` / `exterior_ground_reflectance` are per *request*;
`energy-settings` is per *building*. Reflectance keys are exactly `floor` / `walls` / `ceiling` — a
misspelled key silently uses the default (0.2 / 0.5 / 0.7).

## 4. Surrounding buildings

`context_geometry` is how neighbours shade the room. Omitting it does not error — the room just
reads brighter than it is. The effect is entirely scene-dependent: three close 20 m blocks cut mean
DF **29 %**, while 1570 real Vienna buildings around the same room cut it only **3 %**. Never quote
a fixed figure.

## 5. energy-balance specifics

Every entity needs a **`category`** — `"space"` for `spatial_volumes`, `"wall"`/`"floor"` for
barriers, `"window"` for openings. A missing or mistyped category is silently skipped, so a room
with mistyped walls reports no exterior wall loss at all. `spatial_volumes` also need `position`
**and** `rotation`; openings need `rotation` — absence is a 500, not a validation error.
`to_interior_entity(mesh, category="space")` supplies identity transforms.

Climate: `dry_bulb_temperature` (°C) and `global_horizontal_radiation` must be equal length, ≥ 12
samples, spanning a full year — 12, 52, 365 and 8760 all work. Radiation is **Wh/m² per sample**,
not mean W/m²; the natural reading makes solar gains ~1000× too small and still returns 200.

## 6. daylight-factor tiers

| tier | result shape |
|---|---|
| `sensor_points` | `{"output": [{x,y,z,df}], "min-legend", "max-legend"}` |
| `sensor_surfaces` | `{"surfaces": {sid: …}}` |
| `floors` | `{"floors": {"0": …}}` |
| `buildings` | `{"buildings": {bid: {"floors": {…}}}}` |

The `floors` and `buildings` tiers additionally require barriers carrying `category="floor"` **with
`position`/`rotation`** — plain barriers give a *billed* rejection. Supplying two sensor tiers at
once is not an error either: points win and the surfaces are silently ignored.

**Caps (daylight-factor only):** 15 floors per request summed across *all* buildings · 100,000
sensors per floor · 2,000,000 occluder triangles. `energy-balance` has no caps. The SDK checks these
before submitting, because an over-cap request is billed and *then* refused.

## 7. Reading the result

Results are a ZIP:

```python
from infrared_sdk.analyses.jobs import JobsServiceClient

result = JobsServiceClient.decompress(client.jobs.download_results(job.job_id).content)
values = [p["df"] for p in result["output"]]
assert len(set(values)) > 1, "uniform field — the occluder was empty"
```

**Always check for a uniform field** — it is the one failure that looks like a success. For a daylit
room, 1–2 % is dim, 2–5 % normal, > 5 % generously glazed, and values should fall off sharply away
from the aperture. A flat field means something never reached the model.

Compute is fast (~0.1 s); the wait is queue time (~20 s). Payload size is not the driver, so there
is nothing to gain from splitting a request that already fits.
