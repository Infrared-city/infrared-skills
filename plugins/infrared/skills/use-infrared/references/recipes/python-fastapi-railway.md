# Recipe: FastAPI that Wraps the Infrared SDK (Railway / Render)

> **No affiliation.** Railway and Render are independent third-party platforms — pick either, or swap for Fly.io / Koyeb / your own VPS. The recipe pattern stays the same.
> **Official docs:** Railway — [docs.railway.com](https://docs.railway.com) (agent-friendly: [llms.txt](https://docs.railway.com/llms.txt), [llms-full.txt](https://docs.railway.com/llms-full.txt)). Render — [render.com/docs](https://render.com/docs). FastAPI — [fastapi.tiangolo.com](https://fastapi.tiangolo.com).

A small FastAPI service that holds your `INFRARED_API_KEY`, wraps the Python SDK, and exposes typed endpoints your frontend (browser, mobile, Lovable, Worker, whatever) can call. Deploys to Railway in three commands; the same code runs on Render with a GitHub connect.

This is the **default backend** for any TypeScript / browser app that needs Infrared results — see also [`typescript-direct-api.md`](typescript-direct-api.md) (Node-only direct calls) and [`lovable-frontend.md`](lovable-frontend.md) (consume from a Lovable UI).

## When to use this

- You need a public HTTPS URL for a frontend to call.
- You want the Infrared SDK's tiling / polygon / merge logic (TypeScript direct calls only cover single-tile primitives).
- You want one place to add user auth, rate-limits, billing later (see [`persistence-and-users.md`](persistence-and-users.md)).

## Target Stack

- Python 3.11+.
- `fastapi` + `uvicorn[standard]`.
- `infrared-sdk` — the official Python client.
- `pydantic-settings` for typed env config.
- `python-dotenv` for local `.env` loading (uvicorn dev only).
- One platform: **Railway** (primary) or **Render** (alt). Both auto-detect Python from `pyproject.toml` / `requirements.txt` — no Dockerfile needed for the default path.

## Project layout

```
my-infrared-api/
├── pyproject.toml
├── .env                    # local dev only — gitignored
├── .gitignore
├── README.md
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI app + CORS + router mounting
    ├── settings.py         # pydantic Settings — env vars in one place
    ├── deps.py             # FastAPI dependencies (e.g., get_settings, get_client)
    ├── schemas.py          # pydantic request/response models
    ├── services/
    │   └── infrared.py     # SDK wrapper — the only place that imports infrared_sdk
    └── routers/
        ├── sims.py         # POST /sims/sun-hours, /sims/pwc, ...
        └── health.py       # GET /health
```

Why this shape: one router per resource family, one service per external system, settings centralised. Easy to grow (add `routers/users.py`, `services/storage.py`) without rewiring. The frontend never imports anything from `services/` — it only sees `schemas` over HTTP.

## pyproject.toml

```toml
[project]
name = "my-infrared-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "infrared-sdk>=0.4.8",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "python-dotenv>=1.0",
]
```

## app/settings.py

One typed surface for every env var. Fails fast on boot if a required value is missing.

```python
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    infrared_api_key: str = Field(..., description="X-Api-Key for api.infrared.city")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    environment: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Pydantic-settings reads env vars case-insensitively. `INFRARED_API_KEY` → `infrared_api_key`. `CORS_ORIGINS='["https://my-app.pages.dev","https://my-app.lovable.app"]'` → parsed JSON list.

## app/services/infrared.py

The SDK wrapper. Only file that imports `infrared_sdk`. Keeps the rest of the codebase decoupled.

```python
from functools import lru_cache
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName, SolarModelRequest
from infrared_sdk.models import TimePeriod

from app.settings import get_settings


@lru_cache
def get_client() -> InfraredClient:
    settings = get_settings()
    return InfraredClient(api_key=settings.infrared_api_key)


def _square_polygon(lat: float, lon: float, half_deg: float = 0.0025) -> dict:
    """A small ~500 m square polygon centred on (lat, lon). GeoJSON [lon, lat]."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half_deg, lat - half_deg],
            [lon + half_deg, lat - half_deg],
            [lon + half_deg, lat + half_deg],
            [lon - half_deg, lat + half_deg],
            [lon - half_deg, lat - half_deg],
        ]],
    }


def run_sun_hours(lat: float, lon: float, month: int) -> dict:
    """Run direct-sun-hours for a single month over a small square around (lat, lon)."""
    client = get_client()
    request = SolarModelRequest(
        analysis_type=AnalysesName.direct_sun_hours,
        latitude=lat,
        longitude=lon,
        time_period=TimePeriod(
            start_month=month, start_day=1, start_hour=8,
            end_month=month, end_day=28, end_hour=18,
        ),
    )
    polygon = _square_polygon(lat, lon)
    result = client.run_area_and_wait(request, polygon)
    return {
        "grid": result.merged_grid.tolist(),
        "bounds": list(result.bounds),
        "min_legend": result.min_legend,
        "max_legend": result.max_legend,
    }
```

Real production code would type the return value and reuse a single request builder per analysis — keep it flat for the recipe.

## app/schemas.py

Note: `direct-sun-hours` requires a single-month window — multi-month requests return HTTP 400.

```python
from pydantic import BaseModel, Field


class SunHoursRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    month: int = Field(7, ge=1, le=12)  # single month only — multi-month returns 400


class SunHoursResponse(BaseModel):
    grid: list[list[float]]
    bounds: list[float]          # [west, south, east, north]
    min_legend: float | None
    max_legend: float | None
```

## app/routers/sims.py

```python
import logging
from fastapi import APIRouter, HTTPException
from app.schemas import SunHoursRequest, SunHoursResponse
from app.services.infrared import run_sun_hours

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sims", tags=["sims"])


@router.post("/sun-hours", response_model=SunHoursResponse)
def sun_hours(req: SunHoursRequest) -> SunHoursResponse:
    try:
        data = run_sun_hours(req.lat, req.lon, req.month)
    except Exception:  # narrow when you know which SDK errors you care about
        # Log the real traceback server-side; do NOT leak SDK error text
        # (may contain internal URLs / auth diagnostics) over the public boundary.
        log.exception("sun_hours failed")
        raise HTTPException(status_code=502, detail="Upstream simulation failed")
    return SunHoursResponse(**data)
```

## app/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.settings import get_settings
from app.routers import sims, health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Infrared API wrapper", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(sims.router)
    return app


app = create_app()
```

`/openapi.json` is exposed automatically — Lovable consumes it (see [`lovable-frontend.md`](lovable-frontend.md)).

## Local dev

```bash
echo "INFRARED_API_KEY=sk_live_..." > .env       # NEVER commit
uv pip install -e .                              # or pip install -e .
uv run uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/sims/sun-hours \
  -H 'Content-Type: application/json' \
  -d '{"lat":48.21,"lon":16.36,"month":7}'
```

## Deploy: Railway (primary)

```bash
npm i -g @railway/cli
railway login
railway init        # creates project, links cwd
railway up          # uploads, builds with Railpack, deploys
railway domain      # request a *.up.railway.app URL
```

Set the API key:

```bash
railway variable set INFRARED_API_KEY=sk_live_...
railway variable set CORS_ORIGINS='["https://my-app.lovable.app","https://my-app.pages.dev"]'
```

Or via Railway dashboard → your service → **Variables** tab. For secrets shared by multiple services (DB URL, key), use **Project Settings → Shared Variables** and reference with `${{shared.NAME}}`. Mark a variable as **Sealed** to hide its value in the UI after first save — useful for `INFRARED_API_KEY`.

Variables are scoped per environment (production, staging, PR previews) — each environment gets its own value.

Start command — Railway autodetects FastAPI and runs `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. To override, set **Service → Settings → Custom Start Command**.

## Deploy: Render (alternative — free, no credit card)

1. Push code to GitHub.
2. render.com → **New +** → **Web Service** → pick repo.
3. Runtime: Python 3. Build command: `pip install -e .` (or `pip install -r requirements.txt` if you prefer). Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. Free instance type: 512 MB / 0.1 vCPU, sleeps after **15 min idle**, cold start 30–60 s for numpy/scipy on first wake. Paid tier: always-on.
5. **Env vars** → add `INFRARED_API_KEY` and `CORS_ORIGINS`. For multi-service projects, create an **Env Group** under Settings → Env Groups and link it to each service — single source of truth.

Cold-start mitigation for demos: hit `/health` 30 s before going on stage, or upgrade to Starter for the duration of the event.

## Picking Railway vs Render

| | Railway | Render |
|---|---|---|
| Free without card | trial credit only | Yes |
| Always-on free | No | No (sleeps 15 min) |
| FastAPI cold start | None | 30–60 s on wake |
| Native DB | Postgres service | Postgres (free 30 days, then paid) |
| Native object storage | **Railway Buckets** (S3-compat) | None (use B2 / R2) |
| CLI deploy | `railway up` | Push to GitHub |

Default pick for hackathons with a credit card: **Railway** — no cold start kills your demo. Default for "no card at all": **Render** with the `/health` warm-up trick.

## When this recipe isn't enough

- **GPU work** — Infrared SDK calls are network-bound, so a tiny FastAPI on Railway is fine. If you're also running your *own* GPU job (training, inference) in the same service, neither Railway nor Render is the right home. Move that part to **Modal** with `@modal.asgi_app()` (free credits per account on signup).
- **Cron / background jobs** — Render has native **Background Workers** and **Cron Jobs**. Railway uses a separate service per cron. For "poll an async Infrared job every minute and post to Slack," either works.
- **Large simulation polygons** — let the SDK do the tiling; expose a job-submission endpoint that returns immediately, then poll from the frontend (or use webhooks — see [`../06-webhooks.md`](../06-webhooks.md)).

## Pitfalls

- **`.env` committed by accident** — add `.env` to `.gitignore` first thing. Railway and Render both ignore `.env` files; env vars come from the platform UI.
- **CORS allow-all in production** — `cors_origins=["*"]` works in local dev but breaks if you ever ship browser auth (cookies + `*` is forbidden by spec). List your real frontends.
- **Holding `InfraredClient` per-request** — re-instantiating the SDK on every call adds latency. The `@lru_cache` in `services/infrared.py` keeps one client for the process lifetime.
- **Pickling errors with `numpy.ndarray` in responses** — convert to lists via `result.merged_grid.tolist()` (see `services/infrared.py`).
- **Trial credit isn't recurring** — once it's spent, the service goes down unless you upgrade. Set a calendar reminder for ~day 7.

## See also

- TypeScript without this backend: [`typescript-direct-api.md`](typescript-direct-api.md)
- Add a DB, blob storage, users, billing: [`persistence-and-users.md`](persistence-and-users.md)
- Plug a Lovable.dev UI into this server: [`lovable-frontend.md`](lovable-frontend.md)
- Auth invariants and SDK install: [`../00-setup.md`](../00-setup.md)
