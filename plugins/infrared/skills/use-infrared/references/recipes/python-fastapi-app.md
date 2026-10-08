# Recipe: a fast Python API app on the Infrared SDK

Build a small HTTP API that holds the API key, takes the user's site and
buildings, prices a run, runs it in the background and serves the map.
Any frontend can call it: a web map, a mobile app, a notebook or a CAD plugin.

Runnable code: [`cookbook/apps/python-fastapi/`](../../../../../../cookbook/apps/python-fastapi/)
(`main.py` is about 200 lines). Copy it, then change it. This recipe tells you
why the code has its shape, so that you keep it fast when you grow it.

SDK guide (one Markdown file, good for agents): https://infrared.city/docs/sdk/1.0/sdk.md.
Python reference: https://infrared.city/docs/sdk/1.0/python/sdk/index.md.

## When to use this

- A browser or mobile app needs Infrared results, and the key must stay secret.
- You want results stored and shared between users (one run, many viewers).
- You run batch jobs on a server.

For an interactive map where each user's device does the work, the
TypeScript SDK in a Web Worker is also an option. Read "Serve many users" in
the SDK guide. The server way below is the simpler start.

## What you build

```
frontend ──POST /preview──▶ API ── preview_area()  (local, free)
         ──POST /runs─────▶ API ── thread: run_area_and_wait() ──▶ Infrared cloud
         ◀─ run_id (at once)          tiles, upload, submit, poll, merge
                                      (wind: run_area + directional blend merge)
         ──GET /runs/{id}──▶ status + jobs_done / jobs_total
         ──GET /runs/{id}/result.png | result.json
```

| Endpoint | Does | Cost |
|---|---|---|
| `POST /preview` | Tiles, jobs, tokens | Free, sends no job |
| `POST /runs` | Starts the run in a worker thread, returns `run_id` at once | Billed per job |
| `GET /runs/{id}` | `queued`, `running`, `done` or `failed`, plus job progress | Free |
| `GET /runs/{id}/result.json?step=1` | Physical values (`null` = no value), grid bounds, legend | Free |
| `GET /runs/{id}/result.png` | Official colours, north up, no-data transparent | Free |

Request body: `polygon` (GeoJSON, `[lon, lat]`), `analysis`, `params`,
`buildings` (GeoJSON footprints with `height`), `public_buildings` (fallback),
`allow_large` (more than 100 tiles). The app README has the full body and curl calls.

Bad input gets HTTP 422 with a clear message, before anything is billed:

- `SiteRequest` checks the polygon: type `Polygon`, one closed ring of 4 or
  more `[lon, lat]` points in range.
- The SDK refuses more than 100 tiles. The app catches this in the preview
  and says so. With `allow_large: true` it passes `max_tiles_override` (the
  app has its own upper limit, 400 tiles).
- `public_buildings` without the `geodata` extra: the message gives the
  install line.

## Speed rules (the code follows each one)

1. **One client per process.** Make `InfraredClient()` once at startup
   (FastAPI `lifespan`) and close it at shutdown. The client keeps the
   upload of each tile geometry in memory for about 24 hours. A second
   analysis on the same site then skips the upload. A client per request
   uploads everything again. The Python SDK has no disk store for these
   uploads; keep the process alive.
2. **Preview first.** `client.preview_area(polygon, payload=request)` is local
   and free. Show `would_bill_jobs` and `estimated_cost_tokens` to the user
   before they press Run. Always give the analysis (`payload=` or
   `analysis_type=`): without it the count uses the wind grid and is wrong.
3. **Let the SDK poll.** `run_area_and_wait` tiles, uploads, submits, polls
   and merges. It asks for up to 50 jobs per status request with a set pace.
   Your own poll loop only adds requests. Use `on_progress` to update the
   status that your frontend reads. Wind speed is the one exception (rule 8).
4. **Return at once, run in the background.** A run takes seconds to minutes.
   Start it in a small thread pool and return the `run_id`. The frontend asks
   `GET /runs/{id}` every 1 to 2 s. Two runs at a time per process is
   enough: the merge of a large site needs much memory for a short time.
5. **Cache results by input hash.** The API has no result cache: the same
   run again is billed again. Hash every input (polygon, analysis, params,
   buildings) and return the old run for the same hash. Do the check and the
   insert under one lock (`store.py`): FastAPI runs sync endpoints in a thread
   pool, so two equal requests can arrive at the same moment. Remove the hash
   when a run fails, so that the user can try again. Drop old runs (the app
   keeps a done run for 1 hour, at most 50 runs): each one holds its grid in memory.
6. **Never billed twice on a retry.** Each job has an idempotency key. When a
   submit gets no answer, the SDK sends the same key again and the server
   returns the job it has. A failed tile is sent again once (`retries=1`)
   with a new key. Do not wrap `run_area_and_wait` in your own retry loop.
7. **Several analyses, same site.** Keep the same buildings object and the
   same client. All analyses except wind share one tile grid. On the same grid and
   layers they also share the uploads. Wind has its own grid.
8. **Wind speed: always merge with the directional blend.** The default merge
   crops each tile at its centre and leaves visible seams in a wind field.
   `analyses.run_area` does it for wind:

   ```python
   schedule = client.run_area(request, polygon, buildings=buildings)
   known = {}
   while not client.check_area_state(schedule, known=known).is_complete:
       time.sleep(1)
   result = client.merge_area_jobs(schedule, strategy="directional_blend",
                                   wind_direction_deg=request.wind_direction)
   ```

   The app also resubmits failed tiles once (`run_area(..., retry_from=schedule,
   known=known)`). `merge_area_jobs` raises `AreaRunError` when a tile is
   still missing, so you never get a map with holes.

## Own data first

The user's own model is the main input. Public data is the fallback for a
user with no model.

### Buildings from footprints

The SDK needs buildings as closed meshes `{id: {coordinates, indices}}` in
metres. Most users have footprints with a height. `geometry.py` extrudes
them:

- Origin (0, 0, 0) = south-west corner of the bounding box of the run
  polygon. x is east, y is north, z is up, in metres.
- Lon/lat to metres on the sphere the SDK uses:
  `x = 6371000 * dlon * cos(origin_lat)`, `y = 6371000 * dlat` (radians).
- Caps with `shapely.constrained_delaunay_triangles`: concave shapes and
  courtyards stay correct, and no new points are added.
- Each building is one closed solid with a bottom face and outward faces.
  An open mesh gives wrong shade and no error.

```python
def extrude_footprints(features: dict, polygon: dict, default_height: float = 10.0) -> dict:
    origin = polygon_origin(polygon)              # SW corner of the polygon bbox
    for feature in features["features"]:
        height = float(feature["properties"].get("height") or default_height)
        local = Polygon([to_local(origin, *p[:2]) for p in ring], holes).buffer(0)
        coords, indices = _extrude(local, height) # bottom, top, walls
```

A bare buildings map is read in the frame of the run polygon. So extrude
for the same polygon that you run.

Other own layers go straight to the run, in lon/lat: trees
(`vegetation=`, GeoJSON Points with `genus`, `height`, `crownDiameter`) and
ground materials (`ground_materials=`, one FeatureCollection per layer:
`asphalt`, `concrete`, `soil`, `vegetation`, `water`). Only the thermal
comfort analyses read the ground. See "Your inputs" in the SDK guide.

### Public fallback

```python
# needs: pip install "infrared-sdk[geodata]==1.0.0"
buildings = client.buildings.get_area(polygon, analysis_type=analysis)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
```

Pass the returned object itself, not `buildings.buildings`. The object keeps
its origin, so the SDK places it correctly. Give `analysis_type`: the read
margin for wind is smaller than for the solar family.

### Silent traps in user data

The SDK refuses some bad input before you pay. These go through, are billed
and give a wrong map:

- Lat and lon swapped (silent in most of Europe and the Americas).
- A Y-up model, or centimetres or feet instead of metres.
- The origin at the polygon centre instead of the south-west corner.
- Heights as text with units ("18 m"). Parse them to a number first.

## The code, in four parts

### 1. One client for the process

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    state["client"] = InfraredClient()          # reads INFRARED_API_KEY
    state["pool"] = ThreadPoolExecutor(max_workers=2)
    yield
    state["pool"].shutdown(wait=False, cancel_futures=True)
    state["client"].close()
```

### 2. Preview

```python
@app.post("/preview")
def preview(site: SiteRequest) -> dict:
    return {**check_site(site), "cached": store.has_key(site.key())}

def check_site(site: SiteRequest) -> dict:
    request = build_request(site.analysis, site.polygon, site.params)
    try:
        p = state["client"].preview_area(site.polygon, payload=request,
                                         max_tiles_override=site.max_tiles(), buildings=...)
    except ValueError as exc:              # for example over the 100-tile cap
        raise HTTPException(422, str(exc)) from None
    return {"tiles": p.tile_count, "jobs": p.would_bill_jobs,
            "estimated_cost_tokens": p.estimated_cost_tokens}
```

Show tiles, jobs and tokens only.

Price from `would_bill_jobs`, not from `tile_count`. One grid tile is one
job; a tile with no part of the polygon is skipped.

### 3. Run in the background, cached by input hash

```python
@app.post("/runs", status_code=202)
def start_run(site: SiteRequest) -> dict:
    check_site(site)                               # 422 before anything is billed
    run, is_new = store.claim(site.key(), site)    # check + insert under one lock
    if is_new:
        state["pool"].submit(execute, run)
    return {"run_id": run.id, "cached": not is_new}

def execute(run: Run) -> None:
    def on_progress(s):                    # AreaState from the SDK
        run.jobs_done, run.jobs_total = s.succeeded, s.total
    try:
        run.result = run_area(client, request, polygon,      # analyses.py
                              buildings=buildings, on_progress=on_progress)
        store.finish(run, "done")
    except AreaRunError:                   # a tile failed twice: no partial map
        store.finish(run, "failed", "the run did not complete (one or more tiles failed); try again")
```

Log the full exception on the server. Send only a short message to the
client: an SDK error can hold details that the public must not see.

### 4. Results

```python
result.to_list()          # physical values, NaN -> None, ready for JSON
result.physical_grid()    # the same as a numpy array (NaN = no value)
result.bounds             # (west, south, east, north) of the GRID
result.min_legend, result.max_legend
```

- **Use the helpers.** `merged_grid` is in the wire type. Always use
  `to_list()` or `physical_grid()`.
- **JSON is large.** One cell is 1 m, so 1 km² is 1 million values (tens of MB
  as JSON). `result.json?step=4` keeps every 4th row and column. For the full
  grid, cache the encoded body or send the PNG.
- **Bounds describe the grid, not the polygon.** The grid is padded north
  and east to the next tile step. Draw the image on `result.bounds`. Polygon
  corners move the map by tens of metres.
- **Row 0 is south.** Flip the rows for an image with north at the top.
- **PNG:** `client.weather.gen_grid_image(grid=rows[::-1], analysis_type=...)`
  renders locally in the official colours. No-data cells are transparent, so
  the PNG goes straight onto a map on the grid bounds.
- **Units:** sky view factor is 0 to 100 (%), not 0 to 1. Look up the unit of
  each analysis in the SDK guide ("All analyses at a glance").

## Add an analysis

Add one entry to `analyses.py`: a function `(lat, lon, params) -> request`.
The endpoints do not change.

- Wind speed: `WindModelRequest(wind_speed=..., wind_direction=...)`. Merge
  it with the directional blend (speed rule 8).
- Sun hours and daylight: `SolarModelRequest(time_period=TimePeriod(...))`.
  One `TimePeriod` can wrap the year (Dec to Feb).
- Weather analyses (UTCI, thermal comfort statistics, solar radiation,
  wind comfort): build them with `.from_weatherfile_payload(...)` and a
  weather file (`parse_epw`) or a public station. Read "Weather and time
  period" in the SDK guide. Cache the weather per station and period.
- Several analyses on one site: pass a list of requests to
  `run_area_and_wait`. You get one result for each request. Run wind on its
  own, with the directional blend.

Add the new name to the `Literal` in `SiteRequest`, so that FastAPI refuses
unknown names before any SDK work.

## Frontend tips

- Flow: draw or pick the site → load buildings → **preview** → the user
  approves the price → **run** → poll status → show the map. Never start a
  run on a keystroke or a map move.
- Disable Run while the inputs equal the last run. The server cache catches
  a double click anyway.
- Keep the request that made the result next to the result. The legend and
  the labels must come from that request, not from the current form.
- Draw the PNG as an image layer on `bounds` (deck.gl `BitmapLayer`,
  MapLibre image source, Leaflet `imageOverlay`).
- For a hover value, read `result.json` once and look up the cell. Do not
  ask the server per pixel.
- More on colours, legends and maps:
  [`rendering-results-well.md`](rendering-results-well.md).

## Deploy

Any container host works (Railway, Render, Fly.io, Cloud Run, a VM). The app
folder has a short `Dockerfile`; the host sets `PORT`.

1. Set `INFRARED_API_KEY` as a secret on the host. Never in the image, the
   repo or the frontend.
2. Run **one instance with one worker**. Runs and the cache are in process
   memory. A second worker does not see the runs of the first one, and it has its own upload cache.
3. To scale out: keep runs in a database, results in object storage (store
   `result.to_dict()` or the PNG and JSON), and let any instance serve them.
   See [`persistence-and-users.md`](persistence-and-users.md).
4. Allow only your frontend origin (CORS). Add a user check and a run limit
   per user in front of `POST /runs`: the key bills your account.
5. A host that sleeps when idle (free tiers) needs some seconds to wake up.
   Call `/health` before a demo.

Railway:

```bash
railway init
railway variable set INFRARED_API_KEY --stdin   # paste the key
railway up
railway domain
```

For long runs that must survive a restart, use `run_area` (it returns a
schedule you can save) or webhooks instead of a thread. See the Python
reference for `run_area`, `check_area_state`, `merge_area_jobs` and
https://infrared.city/docs/sdk/1.0/python/webhooks/index.md.

## Check before you call it done

- [ ] `POST /preview` returns jobs and tokens and sends no job.
- [ ] `POST /runs` returns a `run_id` in well under one second.
- [ ] The same body again returns `"cached": true` and no new job.
- [ ] `GET /runs/{id}` shows `jobs_done` / `jobs_total` while it runs.
- [ ] `result.png` has north at the top: the buildings in the map are where
      they are in your input. Look at it on a basemap.
- [ ] `result.json` has `null` (not `NaN`) for cells with no value.
- [ ] The key is only in the server environment. No key in logs or responses.
- [ ] A failed run shows a short error and the same inputs can run again.

## Verified

The cookbook app ran for real on SDK 1.0.0: preview of a 200 m site
(1 tile, 1 job), then one sky view factor run with three own buildings
(a tower, an L-shaped block and a courtyard block). The PNG showed each
building at its input position, north up, with lower sky view in the
courtyard. A wind speed run on a 500 m site (4 tiles, public buildings,
directional blend) showed no seams at the tile edges. FastAPI `TestClient`
checks: over 100 tiles and bad polygons give 422, eight equal requests at the
same moment give one run.
