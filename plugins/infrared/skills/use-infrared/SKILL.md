---
name: use-infrared
description: Use the Infrared SDK (`pip install infrared-sdk`) to run urban microclimate simulations — wind, pedestrian wind comfort (PWC), solar radiation, daylight, sun hours, sky view factor (SVF), thermal comfort (UTCI), thermal comfort statistics (TCS) — and interpret results. Activate when the user mentions Infrared, infrared.city, infrared-sdk, urban microclimate, wind / PWC / Lawson, solar / daylight / sun hours / SVF, UTCI / thermal comfort, or asks to run an outdoor environmental simulation on a polygon.
allowed-tools: Bash(pip:*), Bash(uv:*), Bash(python:*), Bash(python3:*), Bash(curl:*)
license: Apache-2.0
---

# Use Infrared

## Default workflow

Most users bring their own data (BIM/Rhino/IFC/GeoJSON footprints, custom landscapes, proposed-scenario ground). Ask before falling back to the SDK fetch path.
→ **BYO (default):** [byo-inputs.md](references/byo-inputs.md) — **Prototype with fetched data:** [01-quickstart.md](references/01-quickstart.md)

## Setup and basics

| Topic | Reference |
|---|---|
| Install + auth | [00-setup.md](references/00-setup.md) |
| End-to-end quickstart | [01-quickstart.md](references/01-quickstart.md) |
| Polygon / GeoJSON / coords | [02-geometry.md](references/02-geometry.md) |
| Time period / weather window | [03-time-period.md](references/03-time-period.md) |
| Weather data / EPW | [04-weather-data.md](references/04-weather-data.md) |
| Bring your own buildings / trees / ground | [byo-inputs.md](references/byo-inputs.md) |

## Execution styles

Pick the entry point first — it shapes blocking, webhooks, and persistence. Full rule: [async-and-jobs.md](references/async-and-jobs.md).

| When | Entry point |
|---|---|
| Sync, blocks until result | `client.run_area_and_wait()` → `AreaResult` |
| Async, returns `AreaSchedule` (use webhook or `check_area_state`); land via `client.merge_area_jobs(schedule)` once terminal | `client.run_area()` → `AreaSchedule` |
| Single tile, custom polling | `client.analyses.execute()` + `client.jobs.*` → `Job` |

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
| Async runs / `AreaSchedule` / single-tile primitives | [async-and-jobs.md](references/async-and-jobs.md) |
| Webhooks / Standard Webhooks v1 / verification | [06-webhooks.md](references/06-webhooks.md) |
| Image generation (PNG output) | [07-images.md](references/07-images.md) |
| Errors / exception hierarchy | [08-error-handling.md](references/08-error-handling.md) |
| Plotting / compare scenarios (baseline vs proposed) / GeoTIFF export | [interpretation/grid-conventions.md](references/interpretation/grid-conventions.md) |

## Invariants

- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env. Never `Authorization: Bearer`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946).
- Imports: `from infrared_sdk import InfraredClient`; `from infrared_sdk.analyses.types import AnalysesName, ...`; `from infrared_sdk.models import TimePeriod, Location` (only for analyses that take them — wind does not).
- Enum **values** are kebab-case (`"wind-speed"`); enum **member names** are snake_case (`AnalysesName.wind_speed`, `PwcCriteria.lawson_lddc`, `TcsSubtype.heat_stress`).
- `wind_direction=270` means wind **from** the west (meteorological convention).
- For most uses: `client.run_area_and_wait(request, polygon, buildings=...)` (sync). Single-tile polygons skip tiling automatically. For async / long-running, see [async-and-jobs.md](references/async-and-jobs.md).
- Single tile is **512 m × 512 m**. Cell pitch is **1 m × 1 m**. Polygon larger than that auto-tiles.
- `wind_speed` is `int` 1–100. Don't pass floats from weather data.
- Use `result.min_legend` / `result.max_legend` for plotting bounds — distributions are heavy-tailed. The API currently returns `None` for these; always guard: `zmin = result.min_legend if result.min_legend is not None else float(np.nanmin(result.merged_grid))`.

## Pitfalls

- `[lat, lon]` instead of `[lon, lat]` in GeoJSON (most common bug).
- `AnalysesName.WIND_SPEED` → `AnalysesName.wind_speed` (StrEnum members are snake_case).
- Skipping vegetation/ground for thermal or solar runs — they materially affect MRT and surface heat. See [byo-inputs.md](references/byo-inputs.md).
- Verifying webhooks against re-encoded JSON instead of raw bytes (see [06-webhooks.md](references/06-webhooks.md)).

**End of task** — always read [references/reflection-and-feedback.md](references/reflection-and-feedback.md) once. Runnable recipes live at [`cookbook/`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook).
