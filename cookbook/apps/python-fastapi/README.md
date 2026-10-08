# Infrared area API (FastAPI)

A small HTTP API on the Infrared SDK 1.0. Send a site polygon and your own
buildings. Get a price, start a run, then read the map as JSON or PNG.
The guide for this app is the
[python-fastapi-app recipe](../../../plugins/infrared/skills/use-infrared/references/recipes/python-fastapi-app.md).

| File | What it does |
|---|---|
| `main.py` | Endpoints, one shared client, background runs, result cache |
| `analyses.py` | Analysis name -> SDK request. Add analyses here. |
| `geometry.py` | Your GeoJSON footprints -> closed building meshes in metres |
| `sample-site.json` | A 200 m site with three buildings, to test with |

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export INFRARED_API_KEY=...        # from https://infrared.city; keep it on the server
uvicorn main:app --port 8000
```

Then, in a second shell:

```bash
# 1. Price it. This sends no job and costs nothing.
curl -s -X POST localhost:8000/preview -H 'content-type: application/json' -d @sample-site.json
# {"tiles":1,"jobs":1,"estimated_cost_tokens":10,...}

# 2. Start the run. You get the run id at once.
curl -s -X POST localhost:8000/runs -H 'content-type: application/json' -d @sample-site.json
# {"run_id":"9c83e327fd37","status":"running","cached":false}

# 3. Ask for the status until it is "done".
curl -s localhost:8000/runs/9c83e327fd37

# 4. Get the map.
curl -s localhost:8000/runs/9c83e327fd37/result.png -o svf.png
curl -s localhost:8000/runs/9c83e327fd37/result.json -o svf.json
```

The same inputs again return the same run (`"cached": true`). It is not billed again.

## Request body

```json
{
  "polygon": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]},
  "analysis": "sky-view-factors",
  "params": {},
  "buildings": {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": "a", "properties": {"height": 18},
     "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}}
  ]},
  "public_buildings": false
}
```

- `analysis`: `sky-view-factors`, `wind-speed` (`params`: `wind_speed`,
  `wind_direction`) or `direct-sun-hours` (`params`: `month`).
- `buildings`: your footprints in lon/lat, with `height` in metres.
- `public_buildings`: set it to `true` only when you have no model. Install
  `infrared-sdk[geodata]==1.0.0` for it.

## Deploy

Any container host works (Railway, Render, Fly.io, Cloud Run, your own VM).

1. Set `INFRARED_API_KEY` as a secret on the host. Never put it in the image or
   in the frontend.
2. Build from the `Dockerfile`. The host sets `PORT`.
3. Use one instance with one worker. Runs and the result cache are in memory.
   For more instances, keep runs and results in a database and object storage.

Railway (it finds the `Dockerfile` itself):

```bash
railway init
railway variable set INFRARED_API_KEY --stdin   # paste the key; it stays out of the shell history
railway up
railway domain
```

Before a public launch, add your own user check and a run limit per user in
front of `POST /runs`, and allow only your frontend origin (CORS).
