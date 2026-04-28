# Infrared Cookbook

Runnable Python recipes for the [Infrared SDK](https://pypi.org/project/infrared-sdk/). Clone, set `INFRARED_API_KEY`, and run.

> **Note (2026-04-28):** the SDK has a workshop Jupyter notebook + 6 numbered example files coming on `feat/quickstart-v2`, plus a major README rewrite (PR #80 `chores/jobs-and-area-docs`) that introduces the canonical `client.analyses.execute()` / `client.jobs.*` / `AreaSchedule` async pattern. Once those land, several recipes here will be superseded — treat the current set as best-effort against current `staging`, and expect the cookbook to re-shuffle on the next sync.

| # | Recipe | What it shows |
|---|---|---|
| 01 | [`01-wind/`](./01-wind/) | Wind-speed analysis over a polygon, plotted |
| 02 | [`02-utci-munich/`](./02-utci-munich/) | End-to-end UTCI thermal-comfort analysis (Munich) |
| 03 | [`03-multi-analysis-vienna/`](./03-multi-analysis-vienna/) | All 8 analyses in one run, multi-panel plot |
| 04 | [`04-vegetation-ground/`](./04-vegetation-ground/) | Fetch-once-reuse pattern for layers across runs |
| 05 | [`05-area-tiling/`](./05-area-tiling/) | Multi-tile polygon walkthrough with tile boundaries overlaid |
| 06 | [`06-fetch-layers/`](./06-fetch-layers/) | Fetch buildings/vegetation/ground without running an analysis |
| 07 | [`07-advanced/`](./07-advanced/) | Lower-level primitives (manual submit/poll/merge, BYO weather, schedules) |
| 08 | [`08-async-webhooks/`](./08-async-webhooks/) | Webhook-driven async workflow with SQLite scheduling |

## Setup

```bash
pip install infrared-sdk plotly python-dotenv numpy
echo 'INFRARED_API_KEY=your-api-key-here' > .env
```

Get an API key at <https://infrared.city>.

## Run a recipe

```bash
cd 01-wind
python wind_analysis.py
```

Each recipe's `README.md` lists its specific options and dependencies.
