# Barcelona Async Demo -- Webhook-Driven Area Analysis

Async version of `demo_barcelona.py` that uses **webhooks** instead of polling.
`submit_analyses.py` fires off 2 analyses (wind, UTCI) per configured area,
stores `AreaSchedule` objects in SQLite, and exits immediately.
`webhook_server.py` (Flask) receives webhook events from the Infrared API and
tracks job status. A separate `generate_visualizations.py` script merges tile
results, fetches ground materials + vegetation, and writes a Plotly HTML file
per area.

```
submit_analyses.py          Infrared API          webhook_server.py
       |                         |                        |
       |--- run_area(webhook) -->|                        |
       |    (wind + UTCI)        |                        |
       |                         |                        |
       |  [stores schedules      |                        |
       |   in SQLite & exits]    |                        |
       |                         |-- job.running -------->|
       |                         |-- job.succeeded ------>|
       |                         |-- job.failed --------->|
       |                         |                        |
       |                         |          (jobs tracked |
       |                         |           in SQLite)   |
       |                         |                        |
                                        generate_visualizations.py
                                        - merge tile results
                                        - fetch ground materials
                                        - fetch vegetation
                                        - outputs/*.html
```

## Prerequisites

- **Python 3.11+**
- **Infrared API key** -- obtain from <https://app.infrared.city> or your account dashboard
- **Webhook secret** -- generated when you register a webhook endpoint via the Infrared API or dashboard
- **Public URL tunnel** (for local development) -- [ngrok](https://ngrok.com/) or a similar tunnelling tool so the Infrared API can reach your local server

## Project structure

```
cookbook/08-async-webhooks/
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

From this recipe directory:

```bash
pip install infrared-sdk
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in your values. The `.env` file **must** live
inside `cookbook/08-async-webhooks/` -- both scripts load it from their own
directory:

```bash
cp .env.example .env
```

Edit `.env` with your credentials.

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

You need **two terminals**. Both commands should be run from `cookbook/08-async-webhooks/`.

### Terminal 1 -- Start the webhook server

```bash
python webhook_server.py
```

The server listens on `0.0.0.0:8000` (or the port set via `PORT`). It will:

1. Receive webhook events from the Infrared API
2. Verify HMAC signatures using `WEBHOOK_SECRET`
3. Update job statuses in SQLite (forward-only: pending -> running -> succeeded/failed)

Once jobs have completed, run `generate_visualizations.py` (see below) to merge
tile results and write Plotly HTML files.

### Terminal 2 -- Submit analyses

```bash
python submit_analyses.py
```

This script will:

1. Preview each area (tile count, estimated time)
2. Fetch buildings for the polygon
3. Fetch weather data for UTCI
4. Submit the wind and UTCI analyses per area with webhook callbacks
5. Persist each `AreaSchedule` to SQLite immediately after submission
6. Exit -- the webhook server handles the rest

### Terminal 3 -- Generate visualizations

Once jobs have reached a terminal status, merge tile results and write HTML:

```bash
python generate_visualizations.py
# or target one area:
python generate_visualizations.py --area barcelona_gracia
```

### Expected output

You will find HTML files in the `outputs/` directory:

```bash
ls outputs/
# barcelona_gracia_outputs.html
```

Each file is a self-contained Plotly page with 4 panels:

1. **Building footprints** — binary mask derived from a merged analysis grid.
2. **Ground materials + trees** — GeoJSON polygons for vegetation/water/
   asphalt/concrete/soil/building layers, overlaid with dark-green triangle
   markers for individual trees.
3. **Wind speed** — merged `wind-speed` heatmap (m/s).
4. **UTCI** — merged `thermal-comfort-index` heatmap (°C).

## Analysis types

| SDK name | Friendly name | Description |
|---|---|---|
| `wind-speed` | wind | Wind speed simulation |
| `thermal-comfort-index` | utci | Universal Thermal Climate Index |

## Cleanup

To reset and start fresh, delete the SQLite database:

```bash
rm demo.db
```

To remove generated visualizations:

```bash
rm outputs/*.html
```

If you registered webhook endpoints through the Infrared API and no longer need
them, delete them via the API or your Infrared dashboard to stop receiving
events.
