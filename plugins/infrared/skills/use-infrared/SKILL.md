---
name: use-infrared
description: Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate simulations — wind, pedestrian wind comfort (PWC), solar radiation, daylight, sun hours, sky view factor (SVF), thermal comfort (UTCI), thermal comfort statistics (TCS) — and interpret results. Activate when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / PWC / Lawson, solar / daylight / sun hours / SVF, UTCI / thermal comfort, or asks to run an outdoor environmental simulation on a polygon.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

## Two workflows — pick the one that fits the user

**Most users bring their own data** (BIM / Rhino / IFC / GeoJSON building footprints, custom landscape designs, proposed-scenario ground materials). That's the primary workflow. **Always check first whether the user already has buildings/trees/ground data** before falling back to the SDK's fetch-from-API path. The fetch path is convenient for prototyping over an unknown city block, but real architectural and planning work usually starts from data the user already has.

→ **For BYO (default for most users):** [byo-inputs.md](references/byo-inputs.md) — DotBim building format, tree GeoJSON Features, ground-material layers, mix-and-match patterns.

→ **For prototyping with fetched data:** the example below.

## Quick start (wind speed, fetched data — prototyping only)

```python
import os
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName, WindModelRequest

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[16.371, 48.207], [16.376, 48.207],
                     [16.376, 48.210], [16.371, 48.210], [16.371, 48.207]]],
}

client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])
area = client.buildings.get_area(POLYGON)        # fetch — replace with BYO when available
result = client.run_area_and_wait(
    WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=15,           # int 1..100, m/s
        wind_direction=270,      # int 0..360, meteorological (270 = from west)
    ),
    POLYGON,
    buildings=area.buildings,    # for BYO: pass dict[str, DotBimMesh] you already have
)
print(result.grid_shape, result.min_legend, result.max_legend)
```

For thermal/solar analyses (UTCI, TCS, solar-radiation), use the `*ModelRequest.from_weatherfile_payload(...)` classmethods — they need hourly weather. See per-analysis section in the [SDK README](https://pypi.org/project/infrared-sdk/) until per-analysis references are written here.

## Invariants

- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env. Never `Authorization: Bearer`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946).
- Imports: `from infrared_sdk import InfraredClient`; `from infrared_sdk.analyses.types import AnalysesName, WindModelRequest, ...`; `from infrared_sdk.models import TimePeriod, Location` (only for analyses that take them — wind does not).
- Enum **values** are kebab-case (`"wind-speed"`); enum **member names** are snake_case (`AnalysesName.wind_speed`, `PwcCriteria.lawson_lddc`, `TcsSubtype.heat_stress`).
- `wind_direction=270` means wind **from** the west.
- Always use `client.run_area_and_wait(request, polygon, buildings=...)` — single-tile polygons skip tiling automatically.
- Single tile is **512 m × 512 m**. Cell pitch is **1 m × 1 m**. Polygon larger than that auto-tiles.
- `wind_speed` is `int` 1–100. Don't pass floats from weather data.
- Use `result.min_legend` / `result.max_legend` for plotting bounds — distributions are heavy-tailed.

## Choosing an analysis

| User wants to know… | Analysis name (kebab-case) | Reference |
|---|---|---|
| Is it windy at street level? | `wind-speed` | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Is wind comfortable for pedestrians? | `pedestrian-wind-comfort` | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Solar energy on a surface? | `solar-radiation` | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Enough daylight at street level? | `daylight-availability` | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Sun-hour exposure? | `direct-sun-hours` | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| How open is the sky? | `sky-view-factors` | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Outdoor thermal comfort? | `thermal-comfort-index` (UTCI) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |
| % of time uncomfortable per year? | `thermal-comfort-statistics` (TCS) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |
| **User has own BIM / Rhino / GeoJSON data** (default for most users) | (any analysis) | [byo-inputs.md](references/byo-inputs.md) |

## Pitfalls

- Hardcoded API keys → use `os.environ["INFRARED_API_KEY"]`.
- `[lat, lon]` instead of `[lon, lat]` in GeoJSON.
- `AnalysesName.WIND_SPEED` → `AnalysesName.wind_speed` (StrEnum members are snake_case).
- Calling `WindModelRequest(location=..., time_period=...)` — wind takes `wind_speed` and `wind_direction`, no location/time_period.
- Averaging PWC class grids — they're categorical class indices, use mode or area-share.
- TCS subtype is per-call — to get `thermal-comfort` + `heat-stress` + `cold-stress`, run three jobs.
- Skipping vegetation/ground for thermal or solar runs — they materially affect MRT and surface heat. Fetch via `client.vegetation.get_area(polygon)` and `client.ground_materials.get_area(polygon)`, or supply your own. See [byo-inputs.md](references/byo-inputs.md).
- Comparing UTCI runs with different weather files (keep the EPW constant).

## Runnable examples

For end-to-end recipes the user can clone and run, point them at the cookbook:
<https://github.com/Infrared-city/infrared-skills/tree/main/cookbook>

Eight scenarios covering wind, UTCI in Munich, all-8-analyses on a single polygon, fetch-once-reuse for layers, area tiling, layer fetching only, advanced lower-level primitives, and async webhook workflows.
