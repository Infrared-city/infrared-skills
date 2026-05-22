# Recipe: SketchUp Plugin for Infrared Simulations

Build a SketchUp Ruby extension that lets users click a point in their 3D model, extract building geometry, submit an Infrared microclimate simulation, poll until done, and render a coloured heatmap grid as real faces directly in the model — no browser, no export, no manual steps.

## How to use this recipe

> **Read the whole file once before writing any code.** The data-transformation chain (SketchUp model space → geographic coords → dotBIM mesh dict → ZIP-wrapped JSON → async job → result grid → coloured faces) has several non-obvious invariants. A first-pass read builds the mental model; then re-read the section matching your current phase.

When you need deeper Infrared API detail, route to:

- `../00-setup.md` — auth, key management.
- `../01-quickstart.md` — minimum async request shape.
- `../02-geometry.md` — polygon format, `[lon, lat]` coord order.
- `../03-time-period.md` — `TimePeriod` semantics, single-month constraint.
- `../04-weather-data.md` — station lookup, EPW parsing, `filter_weather_data`.
- `../async-and-jobs.md` — job lifecycle, polling, result download.
- `../byo-inputs.md` — `buildings=` / `vegetation=` payload shapes.
- `../analyses/0N-*.md` — per-analysis payload details.

## User Stories

1. **City planner reviewing a massing model**: I open my SketchUp urban model, click a courtyard, pick "Pedestrian Wind Comfort (Summer)", and within 4 minutes a teal-to-red heatmap appears on the ground plane showing me which seating areas are too windy.
2. **Architect checking daylight**: I run "Daylight Availability (June)" without leaving SketchUp. The heatmap renders on the ground and I can immediately compare it against my floor plan geometry — no file export required.
3. **Developer extending the plugin**: I want to add a "Vegetation" toggle. The simulation_tool.rb and api_client.rb are under 400 lines combined, clearly separated, and I can add a new SIM_TYPE entry and a UI checkbox without touching the renderer.
4. **First-time user**: I install the `.rbz`, paste my API key in the Settings panel, and save it. The toolbar shows me exactly two buttons: Settings and Run Simulation. My key is validated implicitly on the first simulation run.

## Target Stack

Use:
- **SketchUp 2018+** (Ruby 2.5 runtime; 2020+ ships Ruby 2.7).
- **Pure Ruby stdlib only**: `net/http`, `net/https`, `json`, `uri`, `zlib`, `stringio`. No external gems — they cannot be reliably bundled in a `.rbz` across platforms.
- **SketchUp `UI::HtmlDialog`** for all UI panels (replaces the deprecated `UI::WebDialog`).
- **Infrared async API v2**: `POST /async/{analysis-type}` (ZIP-wrapped JSON), `GET /async/jobs/{id}` for polling, `GET /async/jobs/{id}/results` for download.
- **dotBIM-like mesh dict** as the buildings payload format (see Geometry section).

SketchUp API reference: https://ruby.sketchup.com/  
Extension packaging guide: https://extensions.sketchup.com/developers  
Infrared API docs: https://infrared.city/docs/sdk (Python SDK — use for API contract reference; auth headers and payload shapes are identical)

## File Structure

```
ir_city.rb                          ← loader; registers SketchupExtension
ir_city/
  extension.rb                      ← toolbar, menu, dialogs, prefs I/O
  api_client.rb                     ← all HTTP, polling, ZIP, decompression
  simulation_tool.rb                ← Sketchup::Tool subclass + geometry extractor
  grid_renderer.rb                  ← heatmap faces + colour legend
  result_stats.rb                   ← KPI + chart data computed from result grid
  export_tool.rb                    ← optional: OBJ export helper
  dialogs/
    settings.html                   ← API key input panel
    simulate.html                   ← analysis picker + parameters panel
    results.html                    ← post-run KPI panel (stats + chart)
```

**Loader (`ir_city.rb`):**

```ruby
require "sketchup.rb"
require "json"

Dir[File.join(File.dirname(__FILE__), "ir_city", "*.rb")].each { |f| require f }

module IRCity
  unless file_loaded?(__FILE__)
    ex = SketchupExtension.new("IR City", File.join(PLUGIN_DIR, "extension"))
    ex.version     = "1.0.1"
    ex.description = "Infrared microclimate simulations inside SketchUp"
    Sketchup.register_extension(ex, true)
    file_loaded(__FILE__)
  end
end
```

## Auth and Preferences

The API key is stored as plain JSON in SketchUp's Plugins folder (`ir_city_prefs.json`). The `.gitignore` must exclude this file. On shared machines, document that the key is readable by any local process.

**Preference helpers (`extension.rb`):**

```ruby
module IRCity
  PLUGIN_DIR = File.dirname(__FILE__).freeze
  PREFS_FILE = File.join(
    Sketchup.find_support_file("Plugins"), "ir_city_prefs.json"
  ).freeze

  def self.prefs
    @prefs ||= File.exist?(PREFS_FILE) ?
      (JSON.parse(File.read(PREFS_FILE)) rescue {}) : {}
  end

  def self.save_prefs(hash)
    @prefs = prefs.merge(hash)
    File.write(PREFS_FILE, JSON.generate(@prefs))
  end

  def self.api_key
    prefs["api_key"].to_s
  end
end
```

**Invariants:**
- Always call `IRCity.api_key` at request time, never cache it in a local variable that survives across dialog sessions.
- Empty string == no key. Guard with `api_key.empty?` before any API call.

## UX: Panels and Interactions

The plugin exposes exactly two top-level actions: **Settings** and **Run Simulation**, both accessible from the toolbar and the Plugins menu.

### Settings Panel (`dialogs/settings.html`)

Single-purpose panel, 420 × 220 px.

```
┌─────────────────────────────────────┐
│  IR City — Settings                 │
│  Get your key at infrared.city →    │
│  Account → API Key                  │
│                                     │
│  API Key                            │
│  [••••••••••••••••••••••••]         │  ← type="password"
│                                     │
│  [       Save API Key       ]       │  ← teal button, full width
└─────────────────────────────────────┘
```

**Interactions:**
- On load: `sketchup.get_prefs()` → Ruby reads `ir_city_prefs.json` → calls `loadPrefs({api_key: "..."})` back to JS → fills the input.
- On "Save": trims whitespace, rejects empty, calls `sketchup.save_prefs(JSON.stringify({api_key: key}))` → Ruby merges and writes → shows `UI.messagebox("API key saved.")` → dialog closes.
- No validation call on save (avoids blocking the dialog for a network round-trip). Validation happens implicitly on the first simulation run.

**Ruby bridge callbacks:**

```ruby
dialog.add_action_callback("get_prefs") do |_ctx|
  dialog.execute_script("loadPrefs(#{JSON.generate(prefs)})")
end

dialog.add_action_callback("save_prefs") do |_ctx, data|
  save_prefs(JSON.parse(data)) rescue nil
  dialog.close
  UI.messagebox("API key saved.")
end
```

### Simulate Panel (`dialogs/simulate.html`)

400 × 560 px. Opened by the "Run Simulation" toolbar button. Closes when the user clicks Run (the SketchUp viewport regains focus for the point-click tool).

```
┌──────────────────────────────────┐
│  IR City — Run Simulation        │
│                                  │
│  Analysis                        │
│  [Wind Speed              ▼]     │  ← <select> with 7 options
│                                  │
│  ── Wind parameters ──           │  ← shown only for wind analyses
│  Wind Speed (m/s)  [  5 ]        │
│  Wind Direction °  [180 ]        │
│                                  │
│  ── Time period ──               │  ← shown for sun/thermal analyses
│  Start  Month [6▼] Day [1 ] Hour [9 ]
│  End    Month [6▼] Day [30] Hour [17]
│  [Jun ▼] [Mar ▼] [Sep ▼] [Dec ▼] │  ← season presets
│                                  │
│  ── Weather source ──            │  ← shown for weather-dependent analyses
│  ○ Nearby station                │
│    [Loading stations…      ]     │  ← <select>, populated via API
│  ○ Local EPW file                │
│    [Browse…] /path/to/file.epw  │
│                                  │
│  [         Run          ]        │  ← teal, full width
└──────────────────────────────────┘
```

**Analysis selector:**
- 7 options: Wind Speed, Pedestrian Wind Comfort, Sky View Factor, Daylight Availability, Direct Sun Hours, Solar Radiation, Thermal Comfort (UTCI).
- On change: show/hide parameter sections with `display: block/none`. Wind parameters show only for `wind_speed` and `wind_comfort`. Time period shows for all except `wind_speed` and `sky_view_factor`. Weather source shows for `wind_comfort`, `solar_radiation`, `thermal_comfort`.

**Station picker sub-interaction:**
- On panel open (if analysis needs weather): JS calls `sketchup.get_location()` → Ruby reads `Sketchup.active_model.shadow_info["Latitude/Longitude"]` → calls `setLocation([lat, lng])` → JS calls `sketchup.fetch_weather_stations(JSON.stringify({lat, lng}))` → Ruby calls `ApiClient#fetch_weather_stations` → populates the `<select>`.
- If no model geo-location, the station select shows "Set model location in SketchUp first."

**EPW file picker sub-interaction:**
- "Browse…" calls `sketchup.browse_epw_file()` → Ruby calls `UI.openpanel("Select EPW", "", "EPW Files|*.epw||")` → on selection, calls `setEpwPath(JSON.stringify(path))` → JS shows the filename.

**Run button:**
- Collects all form values into a single params object.
- Calls `sketchup.run_simulation(JSON.stringify(data))`.
- Dialog closes immediately. Ruby activates `SimulationTool` after a `0.1 s` timer tick (gives dialog time to fully close).

**Season preset buttons:**
- Set start/end month + default day/hour ranges in one click.
- Labels: `Jun`, `Mar`, `Sep`, `Dec`. Inline, small, teal text buttons.

### In-Viewport Interaction (SimulationTool)

After the dialog closes, the user is dropped into a custom SketchUp tool:

- Status bar: `IR City ▸ Click any surface or ground to place the 512 m simulation tile  |  Esc = cancel`
- Hover: a 512 m-diameter teal circle follows the cursor at the ground Z elevation, with a small crosshair.
- Click: snaps to the model surface under the cursor. Collects nearby geometry. Shows a confirmation messagebox:

```
IR City — Ready to simulate

Type:      wind speed
Tile:      512 × 512 m centred on click point
Geometry:  14 buildings (all faces included)

Top-level objects are highlighted in blue.
Proceed?

[ Yes ]  [ No ]
```

- On Yes: API submission begins. Status bar updates: `IR City: Running wind-speed simulation…` → `IR City: Downloading results…` → `IR City: Done.`
- On error: `UI.messagebox("IR City error:\n\n{message}")`.
- Esc / No: cancels, returns to normal SketchUp state.

### Result Heatmap

After a successful run:
- A flat grid of coloured faces is added to the model at the ground elevation, grouped as `IR City: wind-speed result`.
- A colour legend is added as a small set of faces + 3D text ~20 m east of the tile, outside the simulation area.
- The legend shows min/max values with the analysis unit (m/s, hours, °C, etc.) and the analysis name.
- All result geometry is inside one group so the user can delete it cleanly with a single click.

### Results Panel (`dialogs/results.html`)

Opens automatically after every successful render. 300 × 380 px, `STYLE_DIALOG` (stays in front of the SketchUp viewport on all platforms — `STYLE_UTILITY` hides behind the viewport on macOS when the user clicks the model to inspect results).

The panel has **two rendering modes** driven by the `mode` field in the stats payload:

**Continuous mode** (wind speed, SVF, daylight, direct sun, solar radiation, UTCI):

```
┌──────────────────────────────────┐
│  IR City — Wind Speed            │
│  wind_speed · 1 024 ground cells │  ← building pixels excluded
├──────────────────────────────────┤
│  MEAN       P90        MAX       │
│  3.2 m/s    6.1 m/s    9.4 m/s  │
├──────────────────────────────────┤
│  Uncomfortable (>5 m/s)          │
│  ████████░░░░░░░░  34%           │  ← threshold progress bar
├──────────────────────────────────┤
│  Distribution                    │
│  │ ▂▄▇█▆▃▂▁        │            │  ← canvas histogram, 12 bins
│  0                  9.4 m/s     │
├──────────────────────────────────┤
│  [      New Simulation      ]    │
└──────────────────────────────────┘
```

**Categorical mode** (pedestrian wind comfort — Lawson classes A–E):

```
┌──────────────────────────────────┐
│  IR City — Pedestrian Wind …     │
│  wind_comfort · 1 024 cells      │
├──────────────────────────────────┤
│  COMFORTABLE   DANGEROUS  CELLS  │
│  62.4%         6.8%       1024   │
├──────────────────────────────────┤
│  ● A — Calm         ████  36.5% │
│  ● B — Sitting      ███   25.9% │  ← per-class colour-coded bars
│  ● C — Standing     ██    16.2% │
│  ● D — Uncomfortable█     14.6% │
│  ● E — Dangerous    ▌      6.8% │
├──────────────────────────────────┤
│  62.4% comfortable · 6.8% dangerous
│  [      New Simulation      ]    │
└──────────────────────────────────┘
```

**Interactions:**
- On load: `waitForBridge()` retry loop polls for `window.sketchup` up to 20 × 50 ms before calling `sketchup.get_stats()`. Prevents blank panel on first open due to bridge injection timing.
- Ruby responds with `execute_script("render(#{JSON.generate(stats)})")`.
- "New Simulation" calls `sketchup.new_simulation()` → Ruby closes results dialog, opens simulate dialog.
- **Show Last Result** in Plugins menu: Ruby caches `@last_stats` and reopens the panel without re-running. Shows messagebox if no simulation has been run yet.

**Stats payload shape (Ruby → JS):**

```json
// continuous
{ "sim_type": "wind_speed", "label": "Wind Speed", "unit": "m/s",
  "mode": "continuous", "cell_count": 1024,
  "stats": { "mean": 3.2, "p90": 6.1, "min": 0.1, "max": 9.4 },
  "threshold": { "label": "Uncomfortable (>5 m/s)", "pct": 34.0 },
  "histogram": { "edges": [0.1, 0.9, ...], "counts": [12, 45, ...] } }

// categorical
{ "sim_type": "wind_comfort", "label": "Pedestrian Wind Comfort", "unit": "",
  "mode": "categorical", "cell_count": 1024,
  "classes": [
    { "id": 0, "label": "A — Calm",          "color": "#00c9a7", "count": 374, "pct": 36.5 },
    { "id": 4, "label": "E — Dangerous",     "color": "#e63946", "count":  70, "pct":  6.8 }
  ],
  "comfortable_pct": 62.4, "dangerous_pct": 6.8 }
```

## Data Transformation Chain

Understanding this chain is the highest-value section for debugging and extending.

### 1. SketchUp Model Space → Geographic Coords

SketchUp stores coordinates in **inches** (always, regardless of model units setting). The model's geographic origin is in `model.shadow_info["Latitude"]` / `"Longitude"]`. North angle offset is in `shadow_info["NorthAngle"]` (degrees CW from +Y axis).

```ruby
# inches → metres
metres = sketchup_inches * 0.0254

# Model-space (X=right, Y=forward) → geographic (east, north)
east_m  = x_m * cos(north_rad) - y_m * sin(north_rad)
north_m = x_m * sin(north_rad) + y_m * cos(north_rad)

# Offset from model origin to absolute lat/lng
lat = origin_lat + north_m / 111_000.0
lng = origin_lng + east_m  / (111_000.0 * cos(origin_lat * π / 180))
```

The `111_000` m/degree approximation is accurate enough for 512 m tiles. Do not use a sphere formula — it is not meaningfully more accurate at this scale.

If `shadow_info["Latitude"] == 0 && shadow_info["Longitude"] == 0`, the model is not georeferenced. The plugin prompts for manual lat/lng with a default of Madrid.

### 2. SketchUp Entities → Mesh Dict (Buildings Payload)

The Infrared API expects buildings as a dict of mesh objects:

```json
{
  "b0": { "mesh-id": 0, "coordinates": [x,y,z, x,y,z, ...], "indices": [0,1,2, ...] },
  "b1": { "mesh-id": 1, "coordinates": [...], "indices": [...] }
}
```

**Coordinates** are in the **polygon-bbox-SW frame**: origin at the SW corner of the 512 m tile, X = geographic east (metres), Y = geographic north (metres), Z = height above the click ground elevation (metres).

**Extraction rules:**
- One mesh per top-level `Sketchup::Group` or `Sketchup::ComponentInstance`.
- Recursively traverse nested groups/components accumulating faces into the parent mesh.
- Exclude faces whose highest vertex is less than `MIN_HEIGHT_M = 1.0 m` above `ground_z` — flat ground cover is not useful to the simulation.
- Use SketchUp's built-in `face.mesh(4)` to triangulate; `.polygons` returns signed index triplets (absolute value - 1 = 0-indexed vertex).

```ruby
def face_to_arrays(face, transform, north_rad, sw_east_m, sw_north_m, ground_z_m)
  tmesh  = face.mesh(4)
  coords = []
  tmesh.count_points.times do |i|
    pt  = transform * tmesh.point_at(i + 1)
    x_m = pt.x * 0.0254
    y_m = pt.y * 0.0254
    east_m  = x_m * Math.cos(north_rad) - y_m * Math.sin(north_rad)
    north_m = x_m * Math.sin(north_rad) + y_m * Math.cos(north_rad)
    coords.push(
      (east_m  - sw_east_m ).round(4),
      (north_m - sw_north_m).round(4),
      ((pt.z * 0.0254) - ground_z_m).round(4)
    )
  end
  indices = tmesh.polygons.flatten.map { |i| i.abs - 1 }
  [coords, indices]
end
```

### 3. Payload → ZIP → POST

The API requires the JSON payload wrapped in a ZIP file (`Content-Type: application/zip`, filename `payload.json` inside the ZIP). The plugin implements ZIP generation from scratch using `Zlib::Deflate` and manual ZIP record packing — no external gems.

```
[Local file header][filename]["payload.json"][deflated data]
[Central directory header]
[End of central directory record]
```

The ZIP file is posted as the raw request body. The API returns `{"jobId": "..."}`.

**Payload shape per analysis type:**

| Analysis | Required fields |
|---|---|
| `wind-speed` | `analysis-type`, `geometries`, `wind-speed` (int m/s), `wind-direction` (int °) |
| `pedestrian-wind-comfort` | + `time-period`, `wind-speed` (array), `wind-direction` (array) from weather |
| `sky-view-factors` | `analysis-type`, `geometries` only |
| `daylight-availability` | + `latitude`, `longitude`, `time-period` |
| `direct-sun-hours` | + `latitude`, `longitude`, `time-period` |
| `solar-radiation` | + `latitude`, `longitude`, `time-period`, weather arrays |
| `thermal-comfort-index` | + `latitude`, `longitude`, `time-period`, full weather array set |

`time-period` shape:
```json
{ "start-month": 6, "start-day": 1, "start-hour": 9,
  "end-month": 6, "end-day": 30, "end-hour": 17 }
```

Single-month constraint: `start-month` must equal `end-month` for all sun-position-dependent analyses. The plugin enforces this before submission with a descriptive error message.

### 4. Polling

```
GET /async/jobs/{job_id}
→ { "jobStatus": "Pending" | "Running" | "Succeeded" | "Succeded" | "Failed" }
```

**The API has a known typo: `"Succeded"` (one 'c'). Handle both spellings.**

```ruby
DONE_STATUSES = %w[Succeeded Succeded].freeze

loop do
  resp   = api_get("#{BASE_URL}/async/jobs/#{job_id}")
  status = resp["jobStatus"] || resp["status"] || "Unknown"
  return download_result(resp, job_id) if DONE_STATUSES.include?(status)
  raise "Job failed: #{resp['error']}" if status == "Failed"
  raise "Timeout" if Time.now > deadline
  sleep 4
end
```

The 4 s fixed sleep is safe for interactive use. For batch / scripted use, add exponential backoff (double every poll, cap at 30 s).

### 5. Result Download and Decompression

The result endpoint may respond in three ways (the plugin handles all):

1. **302 redirect** → presigned S3 URL; follow the `Location` header without auth headers.
2. **200 + `Link` header** → the presigned URL is in the `Link` header (format: `<url>;...`).
3. **200 + body** → result content directly in the response body.

Result content may be ZIP-compressed, GZIP-compressed, or plain JSON. The plugin detects format by magic bytes:
- `\x50\x4b\x03\x04` = ZIP
- `\x1f\x8b` = GZIP
- anything else = plain JSON

After decompression, some API backends return the grid as a top-level array instead of `{"output": [...]}`. Normalise: `parsed.is_a?(Array) ? { "output" => parsed } : parsed`.

### 6. Grid → Heatmap Faces

The result `output` is a 2D array (row-major, Y rows × X cols). Each cell maps to a square face in the tile:

```
grid[row][col] → face at:
  SW corner = [sw_east + col * cell_size_m, sw_north + row * cell_size_m]
  NE corner = [SW + cell_size_m, SW + cell_size_m]
  Z = ground_z
```

Cell size is inferred from tile width / grid width (typically `512 / 64 = 8 m` per cell).

Colour mapping (teal → amber → red gradient, 5 stops):
```ruby
PALETTE = [
  [0.00, Sketchup::Color.new(0,   150, 140)],  # teal
  [0.25, Sketchup::Color.new(0,   201, 167)],  # light teal
  [0.50, Sketchup::Color.new(255, 200,   0)],  # yellow
  [0.75, Sketchup::Color.new(255, 120,   0)],  # orange
  [1.00, Sketchup::Color.new(220,  30,  30)],  # red
]

def lerp_color(t)
  t = t.clamp(0.0, 1.0)
  # find surrounding palette stops and lerp RGB
end
```

`min_v` / `max_v` come from `result["minLegend"]` / `result["maxLegend"]`. If absent, fall back to `flat_sorted_values.first` and `.last`; for direct-sun and daylight, use the 10th-percentile as min to avoid a washed-out scale (near-zero shadow cells would otherwise dominate the range).

All faces are created inside a single `model.start_operation / commit_operation` block. The group is named `IR City: {sim_type} result` so users can identify and delete it.

### 7. Grid → Stats (`result_stats.rb`)

After `commit_operation`, the same flat grid that fed the renderer is passed to `ResultStats.compute(grid, sim_type)`. Building pixels (`nil`) and non-finite values are excluded at the source — all stats operate only on real ground cells:

```ruby
cells = grid.flatten.compact.select { |v| v.is_a?(Numeric) && v.finite? }
```

**Continuous path** (`wind_speed`, `sky_view_factor`, `daylight`, `direct_sun`, `solar_radiation`, `thermal_comfort`):
- Sort cells once; derive mean, P90, min, max from the sorted array.
- Threshold: count cells above (or below, for `below: true` types) a fixed value; express as %. Every analysis type should define a threshold — omitting it leaves a visual gap in the panel layout.
- 12-bin histogram: equal-width bins between min and max; bin index clamped to `[0, bins-1]`.

**Categorical path** (`wind_comfort` only):
- Cast cells to int; count occurrences of each Lawson class (0–4).
- Compute `comfortable_pct` (A+B, classes 0–1) and `dangerous_pct` (E, class 4).

Per-analysis metadata (label, unit, mode, threshold) lives in `ResultStats::ANALYSIS_META`. Adding a new analysis requires only one new entry in that hash — no other code changes.

**Adding a threshold for a new analysis:**
```ruby
"new_type" => { label: "New Analysis", unit: "val", mode: :continuous,
                threshold: { value: 10.0, label: "Above threshold (>10)", below: false } }
```

## SSL / TLS Note

Ruby's `Net::HTTP` defaults to `VERIFY_NONE` when `use_ssl = true` is set without an explicit `verify_mode`. **Always set:**

```ruby
http.verify_mode = OpenSSL::SSL::VERIFY_PEER
```

Without this, the API key is sent in plaintext-equivalent conditions on networks where TLS can be intercepted.

## API Client Architecture

```
ApiClient
  ├── run_and_wait(params, lat, lng, buildings) → result hash
  │     ├── submit_analysis(type, payload) → job_id
  │     ├── poll_until_done(job_id) → download_result(...)
  │     └── download_result(...) → decompress_and_parse(...)
  ├── fetch_weather_stations(lat, lng, radius_km:) → [{identifier, city, lat, lng}]
  └── fetch_weather_data(identifier, time_period) → hourly rows array
```

The client has no state beyond `@api_key`. Every method is a pure function of its arguments. This makes testing straightforward: stub `Net::HTTP` or extract and test `parse_epw_file` independently.

**Weather data paths (runtime, not compile-time):**

```
if epw_path given and File.exist?(epw_path)
  → parse_epw_file(path, time_period)   ← local parse, no network
else
  → fetch_weather_data(station_id, tp)  ← API call
end
```

EPW column indices (0-indexed, 8-line header skipped):
`1=Month, 2=Day, 3=Hour(1-24→0-23), 6=DryBulbTemp, 8=RelHumidity, 12=HorzInfraRad, 13=GlobHorzRad, 14=DirNormRad, 15=DifHorzRad, 20=WindDir, 21=WindSpd`

## Implementation Phases

| Phase | Build | Done-when |
|---|---|---|
| **0** Read | This file end-to-end. Open `../00-setup.md` + `../async-and-jobs.md`. | You can sketch the ZIP→POST→poll→decompress chain from memory. |
| **1** Scaffold | `ir_city.rb` loader + `extension.rb` with toolbar, two menu items, `prefs` helpers. | SketchUp loads the extension. Toolbar appears. Settings dialog opens and saves a key to `ir_city_prefs.json`. |
| **2** HTTP client | `api_client.rb`: `submit_analysis`, `poll_until_done`, `download_result`, `decompress_and_parse`, `zip_string`. No weather yet. | Hard-code a Vienna payload as JSON; POST it; print the job_id; poll to completion; print the grid dimensions. |
| **3** Geometry | `simulation_tool.rb`: `collect_geometry`, `traverse_faces`, `face_to_arrays`, `model_point_to_latlng`. | `collect_geometry(model, point, 0)` returns a non-empty buildings dict for any SketchUp model with groups. |
| **4** Simulate dialog | `dialogs/simulate.html` + Ruby callbacks for `get_location`, `fetch_weather_stations`, `browse_epw_file`, `run_simulation`. | Dialog opens, populates nearby stations, runs wind-speed analysis end-to-end on a test model. |
| **5** Grid renderer | `grid_renderer.rb`: `render`, colour palette, legend. | After a completed run, a coloured face grid appears in the model inside a named group. |
| **5.5** Results panel | `result_stats.rb` + `dialogs/results.html` + `open_results_dialog` in `extension.rb`. | Panel opens automatically after render; shows correct mode (continuous/categorical); "New Simulation" button works. |
| **6** Weather analyses | Add weather field extraction (`merge_weather_fields`, `parse_epw_file`). | Thermal comfort and solar radiation analyses run successfully with an EPW file. |
| **7** Package | Build `.rbz`, write README, test install on a clean SketchUp. | `.rbz` installs without errors; all 7 analyses run; results panel opens on every analysis type. |

## Code Budget

Target **≤ 800 lines** across all Ruby files:

| File | Target | Notes |
|---|---|---|
| `api_client.rb` | ≤ 200 | HTTP, polling, ZIP, decompression |
| `simulation_tool.rb` | ≤ 200 | Tool subclass + geometry extraction |
| `grid_renderer.rb` | ≤ 150 | Heatmap faces + colour legend |
| `result_stats.rb` | ≤ 100 | KPIs, histogram, categorical breakdown |
| `extension.rb` | ≤ 100 | Toolbar, menus, all dialog management |
| `export_tool.rb` | ≤ 60 | OBJ export helper |
| HTML dialogs (combined) | ≤ 500 | settings + simulate + results |

The reference implementation (`ir-city-sketchup-plugin`) lands at ~730 lines of Ruby + ~740 lines of HTML/JS after the results panel.

## Packaging as .rbz

A `.rbz` file is a ZIP renamed with `.rbz`. SketchUp's extension manager installs it into the Plugins folder.

```bash
# Build script (macOS / Linux)
zip -r ir_city.rbz ir_city.rb ir_city/
# Then distribute ir_city.rbz
```

Install paths:
- **macOS:** `~/Library/Application Support/SketchUp {year}/SketchUp/Plugins/`
- **Windows:** `%APPDATA%\SketchUp\SketchUp {year}\SketchUp\Plugins\`

For signed extension submission to the Extension Warehouse, follow: https://extensions.sketchup.com/developers

## Maintainability Notes

**Adding a new analysis type:**
1. Add one entry to `SIM_TYPES` in `api_client.rb`:
   ```ruby
   "new_type" => { type: "new-analysis-name", weather: true, location: true, time: true }
   ```
2. Add weather fields to `ANALYSIS_WEATHER_FIELDS` if needed.
3. Add one `<option>` to the simulate dialog `<select>`.
4. Show/hide relevant parameter sections in `updateUI()`.

That is the complete change. No other files need touching.

**Analysis type name mapping:**
The internal Ruby keys (`wind_speed`, `thermal_comfort`) are short aliases for developer ergonomics. The API receives kebab-case type strings (`wind-speed`, `thermal-comfort-index`). This mapping lives entirely in `SIM_TYPES` — never construct analysis type strings by hand elsewhere.

**Result group cleanup:**
Result groups are named `IR City: {sim_type} result`. Users can delete them manually. If you add a "Clear results" button, iterate `model.entities.grep(Sketchup::Group)` and check `.name.start_with?("IR City:")`.

**Dialog state vs Ruby state:**
HTML dialogs in SketchUp are stateless between openings (each `dialog.show` is a fresh browser context unless `preferences_key` persists state in Chrome's localStorage). Do not rely on dialog state surviving a dialog close. All persistent state lives in `ir_city_prefs.json` and in the SketchUp model itself.

**Thread safety:**
SketchUp's Ruby runtime is single-threaded from the extension perspective. Do not use `Thread.new` for API calls — SketchUp may crash or produce corrupted model state. All API calls run synchronously on the main thread. The status bar and SketchUp's progress indicator provide feedback. For very long analyses (>3 min), consider adding a cancellable progress messagebox.

**The `Succeded` typo:**
The Infrared API's job status endpoint sometimes returns `"Succeded"` (one 'c'). This is a known API inconsistency. Handle both spellings wherever you check job status. Do not "fix" it by normalising — if the API fixes the typo in a future version, your code should still work for both spellings.

## Pitfalls

1. **Units**: SketchUp stores all coords in **inches**. Multiply by `0.0254` to get metres. Do not use `model.options` or `model.units` — those are display preferences; the underlying data is always inches.
2. **Coord frame**: The simulation tile is in a **SW-corner-relative geographic frame**, not SketchUp model space. The conversion involves both the north-angle rotation and the lat/lng offset.
3. **`verify_mode`**: `Net::HTTP` with `use_ssl = true` defaults to `VERIFY_NONE`. Set `verify_mode = OpenSSL::SSL::VERIFY_PEER` explicitly.
4. **Single-month constraint**: `daylight-availability` and `direct-sun-hours` require `start_month == end_month`. Multi-month windows silently produce incorrect results server-side (as of v2). Validate before submission and show the user an explicit error message.
5. **`"Succeded"` typo**: Handle both `"Succeeded"` and `"Succeded"` in the polling loop.
6. **Result grid normalisation**: The API sometimes returns the output grid as a bare top-level array. Always normalise: `parsed.is_a?(Array) ? { "output" => parsed } : parsed`.
7. **Legend bounds for daylight/direct-sun**: Using `flat.first` (≈0) as `min_v` washes out the colour scale because most shadow cells are near-zero. Use the 10th-percentile as `min_v` for these analyses.
8. **No gems in `.rbz`**: SketchUp's sandbox does not have `rubygems` reliably available. Use only stdlib. This means implementing ZIP from scratch using `Zlib::Deflate` — do not try to bundle `rubyzip`.
9. **`file_loaded?` guard**: Wrap extension registration in `unless file_loaded?(__FILE__)` / `file_loaded(__FILE__)`. Without this, SketchUp re-registers the extension on every `Sketchup.require` call, creating duplicate toolbar buttons.
10. **Dialog timing**: Activating a SketchUp tool immediately inside a dialog callback can crash SketchUp on some versions. Use `UI.start_timer(0.1, false) { Sketchup.active_model.select_tool(...) }` to defer one tick.
11. **`window.sketchup` bridge race**: `window.onload` fires before the SketchUp JS bridge is injected. A bare `if (window.sketchup)` guard silently drops the call and renders a blank panel. Use a polling retry: `function waitForBridge(fn, n) { window.sketchup ? fn() : n < 20 && setTimeout(() => waitForBridge(fn, n+1), 50); }`.
12. **`STYLE_UTILITY` hides on macOS**: On macOS, `STYLE_UTILITY` panels fall behind the SketchUp viewport the moment the user clicks the model — exactly when they need to read the results. Use `STYLE_DIALOG` for any panel that needs to stay visible while the user interacts with the model.
13. **Closure vs instance variable in dialog callbacks**: `add_action_callback` blocks close over local variables. If the dialog can be reopened (e.g. "Show Last Result"), use the module-level `@last_stats` inside the callback rather than the local `stats` parameter, so reopened dialogs always reflect the stored value rather than a potentially stale closure.

## Related References

- `../00-setup.md`
- `../01-quickstart.md`
- `../02-geometry.md`
- `../03-time-period.md`
- `../04-weather-data.md`
- `../async-and-jobs.md`
- `../byo-inputs.md`
- `../analyses/01-wind-speed.md`
- `../analyses/02-pedestrian-wind-comfort.md`
- `../analyses/04-direct-sun-hours.md`
- `../analyses/06-solar-radiation.md`
- `../analyses/07-thermal-comfort-utci.md`
- `../interpretation/grid-conventions.md`
- `../interpretation/wind-results.md`
- `../interpretation/thermal-results.md`
