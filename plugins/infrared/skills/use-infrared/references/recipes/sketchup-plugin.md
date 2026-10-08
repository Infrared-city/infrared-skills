# Recipe: a SketchUp plugin for Infrared

Build a SketchUp extension: the user clicks a point in the model, the plugin sends the
buildings around it, and the result appears in the model as a coloured ground plane.
The same shape works for other CAD tools (Revit, Archicad, Blender): only the geometry
export and the drawing change.

## The shape: a thin plugin and a small Python service

Do not call the Infrared HTTP API from Ruby. SketchUp Ruby has no Infrared SDK, and the
SDK does a lot of work for each run: tiling, geometry upload, idempotent retries, batched
polling, and decoding of the binary result (half floats). Rewriting that in Ruby is slow
and fragile.

Put the SDK in a small Python service, and keep the plugin thin:

```
SketchUp (Ruby)                          Python service (FastAPI + SDK)       Infrared
  meshes in metres + polygon ──POST /preview──▶ preview_area()  (free, local)
                             ──POST /runs─────▶ thread: run_area_and_wait() ──▶ cloud
  UI.start_timer, every 1.5 s ─GET /runs/{id}─▶ status, jobs_done / jobs_total
  draw a textured face       ◀─GET /runs/{id}/result.png, result.json
```

The service is the cookbook app [`cookbook/apps/python-fastapi`](../../../../../../cookbook/apps/python-fastapi/)
with one small change (below). Read [python-fastapi-app.md](python-fastapi-app.md) for why it is fast.

Where the service runs:

| Option | API key | Good for |
|---|---|---|
| On the user's computer (`uvicorn main:app --port 8000`) | In the user's own environment | One user, a pilot, a workshop |
| Hosted, for many users | Only on your server. Users sign in to your service. | A plugin that you give to clients |

For the hosted option, add sign-in, a quota and stored results:
[persistence-and-users.md](persistence-and-users.md). The plugin then stores a user token, never the Infrared key.

## The service change: accept meshes

The cookbook app takes GeoJSON footprints. A SketchUp model has real meshes, so accept them
as they are. In `main.py`:

```python
class SiteRequest(BaseModel):
    ...
    # Own meshes: {id: {"coordinates": [x, y, z, ...], "indices": [...]}},
    # metres, x east, y north, z up, origin = SW corner of the polygon bbox.
    meshes: dict | None = None

def site_buildings(site: SiteRequest, fetch_public: bool) -> Any:
    if site.meshes:                       # own model first
        return site.meshes                # a bare map is read in the run polygon's frame
    ...                                   # footprints, then the public fallback, as before
```

`SiteRequest.key()` hashes every field, so the result cache also covers meshes: the same
model and settings again return the stored run and are not billed again.

## Plugin files

```
ir_infrared.rb                ← loader, registers the SketchupExtension
ir_infrared/
  extension.rb                ← toolbar, menu, dialogs, preferences
  service_client.rb           ← HTTP to your service (net/http + json, stdlib only)
  geometry.rb                 ← model -> meshes in metres + polygon in lon/lat
  result_layer.rb             ← textured result face, legend, stats
  dialogs/settings.html       ← service URL (+ token for a hosted service)
  dialogs/run.html            ← analysis picker and its parameters
  dialogs/results.html        ← mean, p90, share above a threshold
```

Use the Ruby standard library only. Gems do not install reliably from an `.rbz`.

## Geometry: model space to the run frame

SketchUp stores every length in **inches**, whatever the display unit. The model location
is in `model.shadow_info["Latitude"]`, `["Longitude"]`, and `["NorthAngle"]`
(degrees, clockwise from the model +Y axis to true north).

The run frame has its origin at the south-west corner of the polygon. Pick a square around
the click, express every vertex relative to its south-west corner, and make the polygon
from the same corner with the SDK projection (sphere, R = 6,371,000 m, cosine at the corner):

```ruby
module IRInfrared
  INCH = 0.0254
  M_PER_DEG = 6_371_000.0 * Math::PI / 180   # metres per degree on the SDK sphere

  # Model point (inches) -> metres east/north of the model origin, rotated to true north.
  def self.model_to_en(pt, north_rad)
    x, y = pt.x * INCH, pt.y * INCH
    [x * Math.cos(north_rad) - y * Math.sin(north_rad),
     x * Math.sin(north_rad) + y * Math.cos(north_rad)]
  end

  # Square of size_m around the click. Returns [polygon, corner_en].
  def self.site_polygon(click_en, size_m, origin_lat, origin_lon)
    ce, cn = click_en[0] - size_m / 2.0, click_en[1] - size_m / 2.0   # SW corner, metres
    lat0 = origin_lat + cn / M_PER_DEG                                # latitude of the corner
    ll = lambda do |e, n|                                             # [lon, lat], GeoJSON order
      [origin_lon + e / (M_PER_DEG * Math.cos(lat0 * Math::PI / 180)), origin_lat + n / M_PER_DEG]
    end
    ring = [ll.(ce, cn), ll.(ce + size_m, cn), ll.(ce + size_m, cn + size_m),
            ll.(ce, cn + size_m), ll.(ce, cn)]
    [{ "type" => "Polygon", "coordinates" => [ring] }, [ce, cn]]
  end
end
```

Meshes: one mesh for each top-level group or component. Go into nested groups and add
their faces to the parent mesh. `face.mesh(4)` triangulates a face.

```ruby
# One face -> flat coordinates and indices in the run frame (metres).
def self.face_arrays(face, transform, north_rad, corner_en, ground_z_m)
  tm = face.mesh(4)
  coords = []
  (1..tm.count_points).each do |i|
    pt = transform * tm.point_at(i)
    e, n = model_to_en(pt, north_rad)
    coords.push((e - corner_en[0]).round(3), (n - corner_en[1]).round(3),
                (pt.z * INCH - ground_z_m).round(3))
  end
  indices = tm.polygons.flatten.map { |i| i.abs - 1 }   # 1-based, signed -> 0-based
  [coords, indices]
end
```

Keep the offset of each face's points when you merge faces into one mesh
(`indices.map { |i| i + coords_so_far / 3 }`).

- Negative coordinates are correct. Buildings south or west of the corner cast shade into the site.
- A mesh must be closed. An open shell gives wrong shade and no error.
- Z is the height above the clicked ground. On sloped terrain, read
  [../analyses/11-terrain-and-context.md](../analyses/11-terrain-and-context.md) and set `terrain_alignment`.
- If `Latitude` and `Longitude` are both 0, the model has no location. Ask the user to set it
  (Window > Model Info > Geo-location). Do not guess a city.

## The run flow

1. **Preview.** `POST /preview` with `{polygon, analysis, params, meshes}`. Show the jobs and
   tokens in a `UI.messagebox` with Yes / No. The preview is free and sends no job.
2. **Run.** `POST /runs` returns a `run_id` at once. `"cached": true` means a stored result:
   no new bill.
3. **Wait without a frozen UI.** Do not loop with `sleep`. Ask for the status from a timer:

```ruby
def self.watch(run_id)
  timer = UI.start_timer(1.5, true) do
    status = ServiceClient.get("/runs/#{run_id}")
    Sketchup.status_text = "Infrared: #{status['jobs_done']}/#{status['jobs_total']} jobs"
    case status["status"]
    when "done"   then UI.stop_timer(timer); ResultLayer.draw(run_id)
    when "failed" then UI.stop_timer(timer); UI.messagebox("Infrared: #{status['error']}")
    end
  rescue StandardError => e
    UI.stop_timer(timer)
    UI.messagebox("Infrared service not reachable: #{e.message}")
  end
end
```

4. **Draw.** Get `result.png` and `result.json`, then draw (next section).

HTTP from Ruby: `Net::HTTP` with `use_ssl = true` and
`verify_mode = OpenSSL::SSL::VERIFY_PEER`. Set both. Set `open_timeout` and `read_timeout`.

## Draw the result: one textured face

`result.png` has the official colours, north at the top, and transparent cells where there
is no value. Put it on **one face** over the grid bounds. That is fast for any grid size.
Thousands of coloured faces make SketchUp slow (a 512 m tile has 262,144 cells).

The grid starts at the polygon's south-west corner, one cell for each metre.
`result.json` gives `shape` (rows, columns) and `legend` (min, max).

```ruby
def self.draw(png_path, rows, cols, corner_en, north_rad, ground_z_m, name)
  model = Sketchup.active_model
  model.start_operation("Infrared result", true)
  # Run-frame metres -> model point (inches): undo the north rotation, add the corner.
  to_model = lambda do |x, y|
    e, n = corner_en[0] + x, corner_en[1] + y
    mx = e * Math.cos(north_rad) + n * Math.sin(north_rad)
    my = -e * Math.sin(north_rad) + n * Math.cos(north_rad)
    Geom::Point3d.new(mx / INCH, my / INCH, ground_z_m / INCH + 4)   # 0.1 m above the ground
  end
  sw, se, ne, nw = to_model.(0, 0), to_model.(cols, 0), to_model.(cols, rows), to_model.(0, rows)
  group = model.active_entities.add_group
  group.name = "Infrared: #{name}"
  face = group.entities.add_face(sw, se, ne, nw)
  face.reverse! if face.normal.z < 0
  mat = model.materials.add("Infrared #{name}")
  mat.texture = png_path
  # Pin the image corners to the face corners: PNG bottom-left = south-west.
  face.position_material(mat, [sw, [0, 0], se, [1, 0], ne, [1, 1], nw, [0, 1]], true)
  model.commit_operation
end
```

- Put the legend next to the site: the analysis name, the unit, the min and max from
  `result.json`, and the same colours. For wind comfort, show one swatch for each class.
- Compute statistics from `result.json` only over cells with a value (`null` = no value).
  Wind comfort gives class codes: report the share of each class, never a mean.
- Colours, scales and legends: [rendering-results-well.md](rendering-results-well.md).
- Keep every result in one named group, so that the user can delete it with one click.

## Dialogs and SketchUp traps

- Use `UI::HtmlDialog` with `STYLE_DIALOG` for the results panel. On macOS a
  `STYLE_UTILITY` panel goes behind the viewport when the user clicks the model.
- `window.sketchup` is not ready at `onload`. Retry: `function ready(fn, n = 0) {
  window.sketchup ? fn() : n < 20 && setTimeout(() => ready(fn, n + 1), 50); }`.
- To start a tool from a dialog callback, wait one tick:
  `UI.start_timer(0.1, false) { model.select_tool(PickTool.new) }`. A direct call can crash.
- Wrap the registration in `unless file_loaded?(__FILE__)` ... `file_loaded(__FILE__)`.
  Without it, each reload adds a second toolbar.
- `add_action_callback` blocks keep their local variables. A dialog that opens again
  ("Show last result") must read module state (`@last_result`), not a captured local.
- Do not use `Thread.new` for HTTP. SketchUp Ruby is single-threaded for extensions.
  The timer above keeps the UI free.
- Dialog state does not persist. Keep settings in a preferences file
  (`Sketchup.write_default` or a JSON file in the user folder), not in the dialog.

## Settings and keys

- **Local service:** the Infrared key is in the environment of the service
  (`INFRARED_API_KEY`), never in the plugin, the model file or the `.rbz`.
- **Hosted service:** the plugin stores only the service URL and the user's own token.
  The service checks the token, counts runs per user, and adds the Infrared key.

## Package as .rbz

An `.rbz` is a ZIP with another extension: `zip -r ir_infrared.rbz ir_infrared.rb ir_infrared/`.
Install it from Extension Manager. For the Extension Warehouse, sign it:
<https://extensions.sketchup.com/developers>. SketchUp Ruby API: <https://ruby.sketchup.com/>.

## Build order

| Step | Build | Done when |
|---|---|---|
| 1 | Run the cookbook service locally with the `meshes` change | `curl` on `/preview` and `/runs` with `sample-site.json` works |
| 2 | Loader, toolbar, settings dialog | The extension loads; the service URL is saved |
| 3 | `geometry.rb` | A test model gives meshes and a polygon; `/preview` returns 1 job |
| 4 | Run flow with the timer | Status updates in the status bar; the UI does not freeze |
| 5 | `result_layer.rb` | The textured face sits on the right buildings, north correct |
| 6 | Results panel and legend | Mean, p90 and the unit show; wind comfort shows class shares |
| 7 | `.rbz` | Installs on a clean SketchUp |

**Check step 5 by eye.** Rotate the model's north angle and run again: the shadows in the
result must still fall away from the sun side of the buildings, and the courtyards must sit
in the courtyards.

## Not tested here

The Ruby code is a sketch: it needs SketchUp to run. The service side is the tested
cookbook app ([python-fastapi-app.md](python-fastapi-app.md), "Verified").
