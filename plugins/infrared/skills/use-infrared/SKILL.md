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
| GIS data → SDK (CRS, reprojection, shapefile/GPKG/GeoTIFF, QGIS, BIM anchoring) | [geospatial-crs.md](references/geospatial-crs.md) |
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
| Gradio area explorer app recipe | [recipes/gradio-area-explorer.md](references/recipes/gradio-area-explorer.md) |

## Recipes

Use the `references/recipes/` folder for UI/app implementation recipes that combine SDK usage with product-level UX guidance.

- Start with [recipes/gradio-area-explorer.md](references/recipes/gradio-area-explorer.md) to build a compact Gradio app using the Infrared SDK.
- For a richer 3D playground (Vite + React + DeckGL frontend, FastAPI backend, Zustand state, location picker that dynamically fetches buildings / vegetation / ground materials from the SDK), see [recipes/sdk-playground-fastapi.md](references/recipes/sdk-playground-fastapi.md).
- To build a **SketchUp Ruby extension** that submits simulations directly from a 3D model and renders heatmap results as coloured faces in the viewport — including a post-run KPI panel with stats and charts — see [recipes/sketchup-plugin.md](references/recipes/sketchup-plugin.md). Note: this recipe uses Ruby (not Python); the Infrared API contract (auth headers, payload shapes, async job lifecycle) is identical.
- To call the SDK from **Rhino 8 Grasshopper** Python 3 Script components, see [recipes/grasshopper.md](references/recipes/grasshopper.md) — a flat list of small patterns: SDK install via `# r:`, auto-registering outputs (`ScriptVariableParam` + `BeforeRunScript`), sticky state, off-UI-thread work with `threading` + `ExpireSolution(True)`, browser-based AOI picker, DotBim ↔ Rhino Mesh, locating the .gh file, saving PNG / GeoTIFF, heatmap mesh from a numpy grid, and visible logging.

### Hackathon track — TypeScript, Python backend, deploy

**Quick-start recipes** for hackathons, demos, internal tools, and small apps — pick the shape and harden later. They optimise for "shipped this weekend," not for production scale: no observability, lightweight auth, single-region, hand-rolled rate limits. Mix and match.

**What's what** — these are independent third-party tools. Infrared has **no affiliation** with any of them; pick what fits, swap freely.

- **[Railway](https://railway.com)** — cloud platform for deploying a small backend with one command. S3-compat Buckets + Postgres built in. Docs: [docs.railway.com](https://docs.railway.com). Agent-friendly: [llms.txt](https://docs.railway.com/llms.txt) (short index) / [llms-full.txt](https://docs.railway.com/llms-full.txt) (paste the whole corpus into your AI).
- **[Render](https://render.com)** — Railway alternative with a free no-credit-card tier (services sleep after 15 min idle). Docs: [render.com/docs](https://render.com/docs).
- **[Supabase](https://supabase.com)** — Postgres + S3-compat storage + magic-link auth on one platform; free tier pauses after 1 week idle. Docs: [supabase.com/docs](https://supabase.com/docs).
- **[FastAPI](https://fastapi.tiangolo.com)** — Python web framework; where the Infrared SDK runs because the SDK is Python-only. Docs: [fastapi.tiangolo.com](https://fastapi.tiangolo.com).
- **[Lovable.dev](https://lovable.dev)** — AI app generator; describe a UI in chat, get a deployable Vite + React + Tailwind + shadcn SPA. Docs: [docs.lovable.dev](https://docs.lovable.dev). Agent-friendly: [llms.txt](https://docs.lovable.dev/llms.txt).
- **[Stripe](https://stripe.com)** — payments. [Stripe Meters](https://docs.stripe.com/billing/subscriptions/usage-based) = usage-based billing without rolling your own credit ledger.
- **[Polar.sh](https://polar.sh)** — Merchant-of-Record on top of Stripe; handles EU VAT + US sales tax globally; webhooks follow [Standard Webhooks v1](https://www.standardwebhooks.com/). Docs: [polar.sh/docs](https://polar.sh/docs).

**Pick your stack** — most hackathon builds compose 2–3 of the recipes below. Common combos:

| You want | Read |
|---|---|
| A Node / Bun / Worker route, no Python backend | [typescript-direct-api](references/recipes/typescript-direct-api.md) |
| A Python backend you can call from any frontend | [python-fastapi-railway](references/recipes/python-fastapi-railway.md) |
| AI-generated React UI on top of your FastAPI | [lovable-frontend](references/recipes/lovable-frontend.md) + [python-fastapi-railway](references/recipes/python-fastapi-railway.md) |
| Hand-built React UI on top of your FastAPI | [typescript-frontend-patterns](references/recipes/typescript-frontend-patterns.md) + [python-fastapi-railway](references/recipes/python-fastapi-railway.md) |
| Persist projects + add users + charge credits | [persistence-and-users](references/recipes/persistence-and-users.md) + [python-fastapi-railway](references/recipes/python-fastapi-railway.md) |
| Charge users + handle EU VAT for me | [persistence-and-users](references/recipes/persistence-and-users.md) **Billing shortcuts → Polar** |
| Everything on one platform (Railway) | python-fastapi-railway + persistence-and-users **Path B** |
| Everything on one platform (Supabase, with magic-link auth) | python-fastapi-railway + persistence-and-users **Path C** |
| Zero ops, just SQLite + local files | python-fastapi-railway + persistence-and-users **Path A** |

What each recipe covers:

- **TypeScript without the SDK** — raw `fetch` to `/v2/async/{type}` from Node / Bun / Workers. Polling, ZIP decode, kebab-case fields, upgrade path when `@infrared-city/infrared-sdk-ts` lands on npm. See [recipes/typescript-direct-api.md](references/recipes/typescript-direct-api.md).
- **Python FastAPI that wraps the SDK and deploys to Railway** (or Render) — project layout, `pydantic-settings`, CORS, secret management, deploy literals, picking between the two platforms. See [recipes/python-fastapi-railway.md](references/recipes/python-fastapi-railway.md).
- **Frontend display patterns (React + Zustand + MapLibre)** — simulation registry, canvas heatmap overlay, KPI cards, scenario switcher. See [recipes/typescript-frontend-patterns.md](references/recipes/typescript-frontend-patterns.md).
- **Persistence, users, billing** — two-table schema (`projects` + `artifacts`, with optional scenarios nested in project state) and pluggable DB + blob bindings. Three swap paths: SQLite + local-fs (today), Railway Postgres + Buckets, Supabase (Postgres + Storage + Auth). Adds `users` + `credit_ledger` + Stripe webhook stub. See [recipes/persistence-and-users.md](references/recipes/persistence-and-users.md).
- **Lovable.dev frontend → your FastAPI backend** — paste your `/openapi.json` URL, Lovable scaffolds a typed React + Tailwind + shadcn UI in chat. CORS, secrets, deploy via GitHub → Cloudflare Pages. See [recipes/lovable-frontend.md](references/recipes/lovable-frontend.md).

Secret handling for recipes:
- Local development: load `INFRARED_API_KEY` from `.env` (never hard-code keys in source).
- Hugging Face Spaces: store `INFRARED_API_KEY` as a Space Secret (Settings -> Secrets), then read it as an environment variable at runtime.
- Deployment docs:
  - [Hugging Face Spaces Overview](https://huggingface.co/docs/hub/spaces-overview)
  - [Managing Secrets in Spaces](https://huggingface.co/docs/hub/spaces-overview#managing-secrets)
  - [Gradio Sharing and Hosting](https://www.gradio.app/guides/sharing-your-app)

## Invariants

- Auth: `X-Api-Key` header from `INFRARED_API_KEY` env. Never `Authorization: Bearer`.
- GeoJSON coords: `[longitude, latitude]` (RFC 7946), **WGS84 / EPSG:4326** assumed (never validated — reproject before calling; see [geospatial-crs.md](references/geospatial-crs.md)).
- Imports: `from infrared_sdk import InfraredClient`; `from infrared_sdk.analyses.types import AnalysesName, ...`; `from infrared_sdk.models import TimePeriod, Location` (only for analyses that take them — wind does not).
- Enum **values** are kebab-case (`"wind-speed"`); enum **member names** are snake_case (`AnalysesName.wind_speed`, `PwcCriteria.lawson_lddc`, `TcsSubtype.heat_stress`).
- `wind_direction=270` means wind **from** the west (meteorological convention).
- For most uses: `client.run_area_and_wait(request, polygon, buildings=...)` (sync). Single-tile polygons skip tiling automatically. **Exception:** multi-tile **`wind-speed`** runs should use the two-step path with `merge_area_jobs(strategy="directional_blend", wind_direction_deg=...)` to eliminate seam artefacts — see [05-area-api.md#merging-strategies](references/05-area-api.md#merging-strategies). For async / long-running, see [async-and-jobs.md](references/async-and-jobs.md).
- Single tile is **512 m × 512 m**. Cell pitch is **1 m × 1 m**. Polygon larger than that auto-tiles. Solar/UTCI/TCS tiles carry a **128 m context margin** per side for distant-shadow buildings.
- `wind_speed` is `int` 1–100. Don't pass floats from weather data.
- Use `result.min_legend` / `result.max_legend` for plotting bounds — distributions are heavy-tailed. The API may omit them; always guard: `zmin = result.min_legend if result.min_legend is not None else float(np.nanmin(result.merged_grid))`.
- Use `result.bounds` (added 0.4.4) — not `polygon.bounds` — to place the bitmap in a map viewer. `result.bounds` reflects the real NE-padded grid extent.

## Pitfalls

- `[lat, lon]` instead of `[lon, lat]` in GeoJSON (most common bug).
- `AnalysesName.WIND_SPEED` → `AnalysesName.wind_speed` (StrEnum members are snake_case).
- Skipping vegetation/ground for thermal or solar runs — they materially affect MRT and surface heat. See [byo-inputs.md](references/byo-inputs.md).
- Verifying webhooks against re-encoded JSON instead of raw bytes (see [06-webhooks.md](references/06-webhooks.md)).

**End of task** — always read [references/reflection-and-feedback.md](references/reflection-and-feedback.md) once. Runnable recipes live at [`cookbook/`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook).
