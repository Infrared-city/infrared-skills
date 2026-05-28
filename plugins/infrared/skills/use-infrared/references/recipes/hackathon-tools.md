# Hackathon & Demo Stack Recipes

Quick-start recipes for hackathons, demos, internal tools, and small apps — optimised for "shipped this weekend," not production scale: no observability, lightweight auth, single-region, hand-rolled rate limits. Mix and match.

**These are independent third-party tools.** Infrared has no affiliation with any of them; pick what fits, swap freely.

## Tools

- **[Railway](https://railway.com)** — cloud platform for deploying a small backend with one command. S3-compat Buckets + Postgres built in. Agent-friendly: [llms.txt](https://docs.railway.com/llms.txt) / [llms-full.txt](https://docs.railway.com/llms-full.txt).
- **[Render](https://render.com)** — Railway alternative with a free no-credit-card tier (services sleep after 15 min idle).
- **[Supabase](https://supabase.com)** — Postgres + S3-compat storage + magic-link auth on one platform; free tier pauses after 1 week idle.
- **[FastAPI](https://fastapi.tiangolo.com)** — Python web framework; where the Infrared SDK runs because the SDK is Python-only.
- **[Lovable.dev](https://lovable.dev)** — AI app generator; describe a UI in chat, get a deployable Vite + React + Tailwind + shadcn SPA. Agent-friendly: [llms.txt](https://docs.lovable.dev/llms.txt).
- **[Stripe](https://stripe.com)** — payments. [Stripe Meters](https://docs.stripe.com/billing/subscriptions/usage-based) = usage-based billing without rolling your own credit ledger.
- **[Polar.sh](https://polar.sh)** — Merchant-of-Record on top of Stripe; handles EU VAT + US sales tax globally; webhooks follow [Standard Webhooks v1](https://www.standardwebhooks.com/).

## Pick your stack

| You want | Read |
|---|---|
| A Node / Bun / Worker route, no Python backend | [typescript-direct-api.md](typescript-direct-api.md) |
| A Python backend you can call from any frontend | [python-fastapi-railway.md](python-fastapi-railway.md) |
| AI-generated React UI on top of your FastAPI | [lovable-frontend.md](lovable-frontend.md) + [python-fastapi-railway.md](python-fastapi-railway.md) |
| Hand-built React UI on top of your FastAPI | [typescript-frontend-patterns.md](typescript-frontend-patterns.md) + [python-fastapi-railway.md](python-fastapi-railway.md) |
| Persist projects + add users + charge credits | [persistence-and-users.md](persistence-and-users.md) + [python-fastapi-railway.md](python-fastapi-railway.md) |
| Charge users + handle EU VAT for me | [persistence-and-users.md](persistence-and-users.md) **Billing shortcuts → Polar** |
| Everything on one platform (Railway) | python-fastapi-railway + persistence-and-users **Path B** |
| Everything on one platform (Supabase, magic-link auth) | python-fastapi-railway + persistence-and-users **Path C** |
| Zero ops, just SQLite + local files | python-fastapi-railway + persistence-and-users **Path A** |

## What each recipe covers

- **[typescript-direct-api.md](typescript-direct-api.md)** — raw `fetch` to `/v2/async/{type}` from Node / Bun / Workers. Polling, ZIP decode, kebab-case fields, upgrade path when `@infrared-city/infrared-sdk-ts` lands on npm.
- **[python-fastapi-railway.md](python-fastapi-railway.md)** — Python FastAPI that wraps the SDK and deploys to Railway (or Render). Project layout, `pydantic-settings`, CORS, secret management, deploy literals.
- **[typescript-frontend-patterns.md](typescript-frontend-patterns.md)** — React + Zustand + MapLibre. Simulation registry, canvas heatmap overlay, KPI cards, scenario switcher.
- **[persistence-and-users.md](persistence-and-users.md)** — two-table schema (`projects` + `artifacts`). Three swap paths: SQLite + local-fs, Railway Postgres + Buckets, Supabase. Adds `users` + `credit_ledger` + Stripe webhook stub.
- **[lovable-frontend.md](lovable-frontend.md)** — paste your `/openapi.json` URL, Lovable scaffolds a typed React + Tailwind + shadcn UI. CORS, secrets, deploy via GitHub → Cloudflare Pages.

## Secret handling

- Local development: load `INFRARED_API_KEY` from `.env` (never hard-code keys in source).
- Hugging Face Spaces: store as a Space Secret (Settings → Secrets), read as env var at runtime. See [Spaces overview](https://huggingface.co/docs/hub/spaces-overview) and [managing secrets](https://huggingface.co/docs/hub/spaces-overview#managing-secrets).
- Railway / Render / Supabase: set as environment variables in the platform dashboard.
