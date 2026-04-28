---
name: use-infrared
description: >
  Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate
  simulations and interpret results — wind speed, pedestrian wind comfort
  (PWC), solar radiation, daylight availability, direct sun hours, sky view
  factor (SVF), thermal comfort (UTCI), and thermal comfort statistics (TCS).
  Use this skill whenever the user mentions Infrared, infrared.city, the
  infrared-sdk Python package, urban microclimate analysis, wind simulation,
  PWC / Lawson criteria, solar / daylight / sun-hours analysis, sky view
  factor, UTCI, thermal comfort, urban heat island analysis, or asks to run
  an outdoor environmental simulation on a polygon or building footprint —
  even if they don't say "Infrared" explicitly.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

This skill lets you call the Infrared SDK to run urban microclimate simulations and interpret the numbers it returns.

## When to load what

This file is the router. **Pick the reference(s) that match the user's intent and load them.** Do not load all references at once — they are designed for on-demand reading.

### Setup and basics

| If the user is… | Read |
|---|---|
| Installing the SDK or setting up auth | `references/00-install-and-auth.md` |
| Running their very first simulation | `references/01-quickstart.md` |
| Defining geometry (polygon, lon/lat order) or a time window | `references/02-geometry-and-time.md` |
| Bringing their own buildings (GeoJSON / Rhino / IFC) | `references/03-buildings-byo.md` |
| Adding vegetation or ground materials | `references/04-vegetation-and-ground.md` |

### Choosing an analysis

Decision tree — what does the user actually want to know?

- **"Is it windy at street level?"** → wind speed → `references/analyses/01-wind-speed.md`
- **"Is the wind comfortable for pedestrians / according to Lawson?"** → PWC → `references/analyses/02-pedestrian-wind-comfort.md`
- **"How much sun energy hits this surface?"** → solar radiation → `references/analyses/03-solar-radiation.md`
- **"Is there enough daylight at street level?"** → daylight availability → `references/analyses/04-daylight-availability.md`
- **"How many sun-hours does this spot get?"** → direct sun hours → `references/analyses/05-direct-sun-hours.md`
- **"How much sky is visible from here?"** → sky view factor → `references/analyses/06-sky-view-factor.md`
- **"Is it thermally comfortable outdoors?"** → UTCI → `references/analyses/07-thermal-comfort-utci.md`
- **"How often is it uncomfortably hot/cold per year?"** → TCS → `references/analyses/08-thermal-comfort-stats.md`

Each of those analysis references contains:
- The exact `*ModelRequest` class to use (with import path)
- A working payload example (Python)
- The response shape
- Realistic value ranges
- Common interpretation traps

### Workflows

| If the user is… | Read |
|---|---|
| Running on a multi-tile polygon (anything bigger than ~250m × 250m) | `references/workflows/area-api-and-tiling.md` |
| Using webhooks instead of polling | `references/workflows/webhooks-and-async.md` |
| Reading the parquet / GeoJSON files the SDK downloads | `references/workflows/result-files.md` |

### Interpretation (what do the numbers mean?)

| Topic | Read |
|---|---|
| Wind speed and PWC results — Lawson, Beaufort, "good vs bad" | `references/interpretation/wind-results.md` |
| Solar / daylight / sun-hours / SVF results | `references/interpretation/solar-results.md` |
| UTCI thermal-stress categories and TCS percentiles | `references/interpretation/thermal-results.md` |
| All comfort/value scales consolidated for cross-reference | `references/interpretation/value-scales.md` |

### Pitfalls

| Topic | Read |
|---|---|
| `ValidationError` / serialisation rules / enum values | `references/pitfalls/validation-errors.md` |
| Common mistakes (lon/lat order, height conventions, time window) | `references/pitfalls/common-mistakes.md` |

## Invariants — never break these

1. **Auth header is `X-Api-Key`**, value comes from `INFRARED_API_KEY` env var. Never hardcode keys, never use `Authorization: Bearer ...`.
2. **GeoJSON coordinate order is `[longitude, latitude]`** (RFC 7946). Lat-first is the most common bug.
3. **Imports come from the public package only**: `from infrared_sdk import InfraredClient`, `from infrared_sdk.analyses.types import ...`, `from infrared_sdk.models import TimePeriod, Location`. Never invent module paths.
4. **Enum values are kebab-case** (`"wind-speed"`, `"pedestrian-wind-comfort"`, `"thermal-comfort-utci"`) — the SDK serialises them; never invent unlisted values.
5. **Use factory methods** when present (`TimePeriod.from_iso(...)`, `Location.from_lat_lon(...)`) instead of bare constructors when both exist.
6. **Don't fabricate fields**. If a user asks for something that isn't in the request type, say so — don't silently add an undocumented kwarg.

## Quick start (paste this if the user just wants to see one working call)

```python
import os
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import WindModelRequest, AnalysesName
from infrared_sdk.models import TimePeriod, Location

client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])

request = WindModelRequest(
    analysis_type=AnalysesName.WIND_SPEED,
    location=Location(latitude=48.2082, longitude=16.3738),  # Vienna
    time_period=TimePeriod.from_iso("2024-07-15T14:00:00", "2024-07-15T15:00:00"),
)
result = client.run_and_wait(request)
print(result.summary())
```

For anything beyond a single tile, **load `references/workflows/area-api-and-tiling.md` first** — single-call runs cap at ~250m × 250m.

## When you're unsure

Load the most specific reference for the user's question, and if it covers multiple analyses (e.g. "compare wind and UTCI on the same site"), load both analysis references plus `workflows/area-api-and-tiling.md`.
