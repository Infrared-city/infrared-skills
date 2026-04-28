---
name: use-infrared
description: Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate simulations — wind, pedestrian wind comfort (PWC), solar radiation, daylight, sun hours, sky view factor (SVF), thermal comfort (UTCI), thermal comfort statistics (TCS) — and interpret results. Activate when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / PWC / Lawson, solar / daylight / sun hours / SVF, UTCI / thermal comfort, or asks to run an outdoor environmental simulation on a polygon.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

## Default workflow

**Most users bring their own data** (BIM / Rhino / IFC / GeoJSON building footprints, custom landscape designs, proposed-scenario ground materials). Always check first whether the user already has buildings/trees/ground data before falling back to the SDK's fetch-from-API path. Real architectural and planning work usually starts from data the user already has.

→ **For BYO (default for most users):** [byo-inputs.md](references/byo-inputs.md)
→ **For prototyping with fetched data:** [01-quickstart.md](references/01-quickstart.md)

## Setup and basics

| Topic | Reference |
|---|---|
| Install + auth | [00-setup.md](references/00-setup.md) |
| End-to-end quickstart | [01-quickstart.md](references/01-quickstart.md) |
| Polygon / GeoJSON / coords | [02-geometry.md](references/02-geometry.md) |
| Time period / weather window | [03-time-period.md](references/03-time-period.md) |
| Weather data / EPW | [04-weather-data.md](references/04-weather-data.md) |
| Bring your own buildings / trees / ground | [byo-inputs.md](references/byo-inputs.md) |

## Choosing an analysis

| User wants to know… | Analysis | Payload + response | Result interpretation |
|---|---|---|---|
| Is it windy at street level? | `wind-speed` | [analyses/01-wind-speed.md](references/analyses/01-wind-speed.md) | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Is wind comfortable for pedestrians? | `pedestrian-wind-comfort` | [analyses/02-pedestrian-wind-comfort.md](references/analyses/02-pedestrian-wind-comfort.md) | [interpretation/wind-results.md](references/interpretation/wind-results.md) |
| Enough daylight at street level? | `daylight-availability` | [analyses/03-daylight-availability.md](references/analyses/03-daylight-availability.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Sun-hour exposure? | `direct-sun-hours` | [analyses/04-direct-sun-hours.md](references/analyses/04-direct-sun-hours.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| How open is the sky? | `sky-view-factors` | [analyses/05-sky-view-factors.md](references/analyses/05-sky-view-factors.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Solar energy on a surface? | `solar-radiation` | [analyses/06-solar-radiation.md](references/analyses/06-solar-radiation.md) | [interpretation/solar-results.md](references/interpretation/solar-results.md) |
| Outdoor thermal comfort? | `thermal-comfort-index` (UTCI) | [analyses/07-thermal-comfort-utci.md](references/analyses/07-thermal-comfort-utci.md) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |
| % of time uncomfortable per year? | `thermal-comfort-statistics` (TCS) | [analyses/08-thermal-comfort-statistics.md](references/analyses/08-thermal-comfort-statistics.md) | [interpretation/thermal-results.md](references/interpretation/thermal-results.md) |

## Cross-cutting topics

| Topic | Reference |
|---|---|
| Area API / tiling / AreaResult / cost preview | [05-area-api.md](references/05-area-api.md) |
| Webhooks / signature verification / events | [06-webhooks.md](references/06-webhooks.md) |
| Image generation (PNG output) | [07-images.md](references/07-images.md) |
| Errors / exception hierarchy | [08-error-handling.md](references/08-error-handling.md) |

## Invariants

- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env. Never `Authorization: Bearer`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946).
- Imports: `from infrared_sdk import InfraredClient`; `from infrared_sdk.analyses.types import AnalysesName, ...`; `from infrared_sdk.models import TimePeriod, Location` (only for analyses that take them — wind does not).
- Enum **values** are kebab-case (`"wind-speed"`); enum **member names** are snake_case (`AnalysesName.wind_speed`, `PwcCriteria.lawson_lddc`, `TcsSubtype.heat_stress`).
- `wind_direction=270` means wind **from** the west (meteorological convention).
- Always use `client.run_area_and_wait(request, polygon, buildings=...)` — single-tile polygons skip tiling automatically.
- Single tile is **512 m × 512 m**. Cell pitch is **1 m × 1 m**. Polygon larger than that auto-tiles.
- `wind_speed` is `int` 1–100. Don't pass floats from weather data.
- Use `result.min_legend` / `result.max_legend` for plotting bounds — distributions are heavy-tailed.

## Pitfalls

- Hardcoded API keys → use `os.environ["INFRARED_API_KEY"]`.
- `[lat, lon]` instead of `[lon, lat]` in GeoJSON.
- `AnalysesName.WIND_SPEED` → `AnalysesName.wind_speed` (StrEnum members are snake_case).
- Calling `WindModelRequest(location=..., time_period=...)` — wind takes `wind_speed` and `wind_direction`, no location/time_period.
- Averaging PWC class grids — they're categorical class indices, use mode or area-share.
- TCS subtype is per-call — to get `thermal-comfort` + `heat-stress` + `cold-stress`, run three jobs.
- Skipping vegetation/ground for thermal or solar runs — they materially affect MRT and surface heat. See [byo-inputs.md](references/byo-inputs.md).
- Comparing UTCI runs with different weather files (keep the EPW constant).

## Runnable examples

For end-to-end recipes the user can clone and run, point them at the cookbook:
<https://github.com/Infrared-city/infrared-skills/tree/main/cookbook>

Eight scenarios covering wind, UTCI in Munich, all-8-analyses on a single polygon, fetch-once-reuse for layers, area tiling, layer fetching only, advanced lower-level primitives, and async webhook workflows.
