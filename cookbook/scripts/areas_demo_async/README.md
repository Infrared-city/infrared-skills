# Barcelona Async Demo -- Webhook-Driven Area Analysis

Async version of `demo_barcelona.py` that uses **webhooks** instead of polling.
`submit_analyses.py` fires off 4 analyses (wind, SVF, UTCI, TCS) for Barcelona
and Vienna, stores `AreaSchedule` objects in SQLite, and exits immediately.
`webhook_server.py` (Flask) receives webhook events from the Infrared API,
tracks job status, and auto-generates Plotly heatmap visualizations when all
analyses for an area complete.

```
submit_analyses.py          Infrared API          webhook_server.py
       |                         |                        |
       |--- run_area(webhook) -->|                        |
       |    (x4 per area)        |                        |
       |                         |                        |
       |  [stores schedules      |                        |
       |   in SQLite & exits]    |                        |
       |                         |-- job.running -------->|
       |                         |-- job.succeeded ------>|
       |                         |-- job.failed --------->|
       |                         |                        |
       |                         |   [all jobs terminal?] |
       |                         |                        |
       |                         |<-- merge_area_jobs ----|
       |                         |--- merged results ---->|
       |                         |                        |
       |                         |     [generate Plotly   |
       |                         |      HTML heatmap]     |
       |                         |                        |
       |                         |          outputs/*.html|
```

## Prerequisites

- **Python 3.11+**
- **Infrared API key** -- obtain from <https://app.infrared.city> or your account dashboard
- **Webhook secret** -- generated when you register a webhook endpoint via the Infrared API or dashboard
- **Public URL tunnel** (for local development) -- [ngrok](https://ngrok.com/) or a similar tunnelling tool so the Infrared API can reach your local server

## Project structure

```
demos/areas_demo_async/
  .env.example        # Template for environment variables
  .env                # Your local config (git-ignored)
  requirements.txt    # Python dependencies
  db.py               # SQLite data layer (schema, atomic persistence)
  submit_analyses.py  # Fire-and-forget analysis submitter
  visualize.py        # Plotly heatmap generator
  webhook_server.py   # Flask webhook receiver + merge orchestrator
  outputs/            # Generated HTML visualizations land here
```

## Setup

### 1. Install dependencies

From the repository root:

```bash
pip install -e .
pip install -r demos/areas_demo_async/requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in your values. The `.env` file **must** live
inside `demos/areas_demo_async/` -- both scripts load it from their own
directory:

```bash
cp demos/areas_demo_async/.env.example demos/areas_demo_async/.env
```

Edit `demos/areas_demo_async/.env` with your credentials.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `INFRARED_API_KEY` | Yes | -- | Your Infrared API key |
| `WEBHOOK_SECRET` | Yes | -- | Secret for HMAC signature verification (from your Infrared dashboard) |
| `WEBHOOK_URL` | Yes | -- | Public URL where the webhook server is reachable (e.g. `https://<id>.ngrok.io/webhook`) |
| `DB_PATH` | No | `demo.db` in this directory | Path to the SQLite database file |
| `PORT` | No | `8000` | Port for the Flask webhook server |

### 3. Expose your local server

If running locally, start a tunnel so the Infrared API can deliver webhooks to
your machine. With ngrok:

```bash
ngrok http 8000
```

Copy the generated `https://...ngrok.io` URL and set it (with `/webhook`
appended) as `WEBHOOK_URL` in your `.env`:

```
WEBHOOK_URL=https://<your-subdomain>.ngrok-free.app/webhook
```

> **Note:** Port 8000 is used by default instead of 5000 to avoid conflicts
> with macOS AirPlay Receiver, which binds to port 5000.

## Usage

You need **two terminals**. Both commands should be run from the repository root.

### Terminal 1 -- Start the webhook server

```bash
python demos/areas_demo_async/webhook_server.py
```

The server listens on `0.0.0.0:8000` (or the port set via `PORT`). It will:

1. Receive webhook events from the Infrared API
2. Verify HMAC signatures using `WEBHOOK_SECRET`
3. Update job statuses in SQLite (forward-only: pending -> running -> succeeded/failed)
4. Detect when all 4 analysis types for an area have completed
5. Spawn a background thread to merge results and generate visualizations

### Terminal 2 -- Submit analyses

```bash
python demos/areas_demo_async/submit_analyses.py
```

This script will:

1. Preview each area (tile count, estimated time)
2. Fetch buildings for the polygon
3. Fetch weather data for thermal analyses
4. Submit 4 analyses per area (wind, SVF, UTCI, TCS) with webhook callbacks
5. Persist each `AreaSchedule` to SQLite immediately after submission
6. Exit -- the webhook server handles the rest

### Expected output

Once all webhook events arrive and merges complete, you will find HTML files in
the `outputs/` directory:

```bash
ls demos/areas_demo_async/outputs/
# barcelona_outputs.html
# vienna_outputs.html
```

Each file is a self-contained Plotly page with 5 heatmap panels: building
footprints, wind speed, sky view factor, UTCI thermal index, and thermal
comfort statistics.

## Analysis types

| SDK name | Friendly name | Description |
|---|---|---|
| `wind-speed` | wind | Wind speed simulation |
| `sky-view-factors` | svf | Sky view factor calculation |
| `thermal-comfort-index` | utci | Universal Thermal Climate Index |
| `thermal-comfort-statistics` | tcs | Thermal comfort statistics |

All four must complete for an area before the merge and visualization step is
triggered.

## Cleanup

To reset and start fresh, delete the SQLite database:

```bash
rm demos/areas_demo_async/demo.db
```

To remove generated visualizations:

```bash
rm demos/areas_demo_async/outputs/*.html
```

If you registered webhook endpoints through the Infrared API and no longer need
them, delete them via the API or your Infrared dashboard to stop receiving
events.
