---
name: use-infrared
description: Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate simulations — wind, pedestrian wind comfort (PWC), solar radiation, daylight, sun hours, sky view factor (SVF), thermal comfort (UTCI), thermal comfort statistics (TCS) — and interpret the results. Activate when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / PWC / Lawson, solar / daylight / sun hours / SVF, UTCI / thermal comfort, or asks to run an outdoor environmental simulation on a polygon.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

Run urban microclimate simulations and interpret outputs from the Infrared SDK.

## Quick start

```python
import os
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName
from infrared_sdk.models import TimePeriod, Location

client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])
request = WindModelRequest(
    analysis_type=AnalysesName.WIND_SPEED,
    location=Location(latitude=48.2082, longitude=16.3738),
    time_period=TimePeriod.from_iso("2024-07-15T14:00:00", "2024-07-15T15:00:00"),
)
result = client.run_and_wait(request)
```

For polygons larger than ~250m × 250m, call `client.run_area_and_wait(...)` instead — the SDK auto-tiles.

## Invariants

- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env var. Never `Authorization: Bearer …`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946).
- Imports: `from infrared_sdk import InfraredClient` / `from infrared_sdk.analyses.types import ...` / `from infrared_sdk.models import TimePeriod, Location`.
- Enum values are kebab-case (`"wind-speed"`, `"thermal-comfort-utci"`).
- `wind_direction` is meteorological — `270` = wind **from** the west.

## Choosing an analysis

| User wants to know… | Analysis | Reference |
|---|---|---|
| Is it windy at street level? | wind-speed | `references/interpretation/wind-results.md` |
| Is the wind comfortable for pedestrians? | pedestrian-wind-comfort | `references/interpretation/wind-results.md` |
| Solar energy on a surface? | solar-radiation | `references/interpretation/solar-results.md` |
| Enough daylight at street level? | daylight-availability | `references/interpretation/solar-results.md` |
| Sun-hour exposure? | direct-sun-hours | `references/interpretation/solar-results.md` |
| How open is the sky? | sky-view-factor | `references/interpretation/solar-results.md` |
| Outdoor thermal comfort? | thermal-comfort-utci | `references/interpretation/thermal-results.md` |
| % of time uncomfortable per year? | thermal-comfort-stats | `references/interpretation/thermal-results.md` |

Load the matching reference for value ranges, units, and pitfalls. For everything else (auth, geometry, time, area API, webhooks, examples) consult the SDK README at <https://pypi.org/project/infrared-sdk/>.

## Common pitfalls

- Hardcoded API keys → use `os.environ["INFRARED_API_KEY"]`.
- `[lat, lon]` instead of `[lon, lat]`.
- `run_and_wait` on a multi-tile polygon → use `run_area_and_wait`.
- Averaging PWC class grids → they're categorical, use mode or area-share.
- Comparing UTCI runs with different weather files.
