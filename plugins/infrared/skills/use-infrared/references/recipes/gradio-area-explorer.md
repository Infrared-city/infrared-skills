# Recipe: Gradio Area Explorer

Build a compact Gradio app for the Infrared SDK area workflow: pick a 1 km area, fetch contextual layers, run `thermal-comfort-index`, `direct-sun-hours`, or `wind-speed`, and show the result grid in a spatial results tab.

## Target Stack

Use:
- Python 3.10+.
- `infrared-sdk`.
- `gradio==6.13.0`.
- `plotly` for interactive result grids.
- `numpy` for summaries.
- `python-dotenv` for local `.env` loading.
- `socksio` when the local environment has SOCKS proxy variables. Without it, Gradio/httpx can fail on import with `Using SOCKS proxy, but the 'socksio' package is not installed`.
- Leaflet in a `gr.HTML` iframe for the map picker. Gradio 6.13.0 does **not** include a native map component.

## Secrets and Deployment

Local usage:
- Keep `INFRARED_API_KEY` in a local `.env` and load it via `python-dotenv`.
- Do not commit `.env` files or hard-code keys in code/config.

Hugging Face Spaces deployment:
- Create a Gradio Space and set `INFRARED_API_KEY` in **Settings -> Secrets**.
- Read the key from `os.getenv("INFRARED_API_KEY")` at runtime.
- Use Space secrets for sensitive values; use Space variables only for non-sensitive config.

Deployment references:
- [Hugging Face Spaces Overview](https://huggingface.co/docs/hub/spaces-overview)
- [Managing Secrets in Spaces](https://huggingface.co/docs/hub/spaces-overview#managing-secrets)
- [Gradio Sharing and Hosting](https://www.gradio.app/guides/sharing-your-app)

## UX Goal

Make one dense, calm, demo-quality tool:

- Header: one compact title and one short sentence.
- Main left panel: tabs for `Layers` and `Results`.
- Right sidecar: simulation selection and run controls.
- Area controls: below the map as a small strip with `City`, `Lat`, `Lon`, and one prominent `Fetch layers` button.
- No separate diameter input. State "1 km" only as copy if needed; the app uses a fixed 1 km diameter.
- No duplicate KPI block in the sidecar. KPIs belong in the `Results` tab.
- On run completion, automatically select the completed analysis result and switch to `Results`.
- If the user selects an analysis that already has a completed result, sync the result dropdown/plot/KPIs to that analysis and switch to `Results`.

Design aesthetic: light background, white cards, teal primary action (`#00a6a6`), very dark text (`#092f32`). Prefer compact rows over stacked inputs. Never use Streamlit state/rerun patterns — Gradio state and event handlers only.

## Layout Spec

Use a `gr.Blocks` page with:

1. Compact hero header.
2. A two-column row:
   - Left column, wider:
     - `gr.Tabs(selected="layers_tab")`
     - `Layers` tab: Leaflet map in `gr.HTML`.
     - `Results` tab: result selector, Plotly result heatmap, KPIs.
     - Area strip below tabs: city preset, lat, lon, fetch button.
   - Right column, narrower:
     - `Run` title.
     - Radio/select for analysis.
     - Short one-line explanation.
     - Analysis-specific controls.
     - Run button.
     - Compact status/progress.

Do not place `City`, `Lat`, `Lon`, or `Diameter` in a large top toolbar. It makes the app feel like a form before it feels like a map tool.

### Compact Control Rules

- `thermal-comfort-index` and `direct-sun-hours`:
  - Show `Month` full width.
  - Row: `Start day`, `End day`.
  - Row: `Start hour`, `End hour`.
- `wind-speed`:
  - Show only `Speed m/s` and `From deg` in one row.
  - Hide month/day/hour controls entirely.
- Keep labels short:
  - `Lat`, `Lon`, `City`, `Month`, `Start day`, `End day`, `Start hour`, `End hour`, `Speed m/s`, `From deg`.
- Avoid nested bordered containers around every field group. One sidecar card is enough.
- Avoid visible empty `gr.HTML`, `gr.Markdown`, or output components. Empty outputs can render as gray slabs in Gradio.

## Visual Design Guidelines

Use an Infrared-style teal palette:

- Primary teal: `#00a6a6`.
- Dark teal: `#007f83` or `#008f93`.
- Text: very dark teal/ink such as `#092f32`.
- Muted text: `#355a5e`.
- Border: translucent teal, around `rgba(0, 96, 101, 0.18)`.
- Background: very light blue-green, not pure gray.
- Cards: white or near-white with subtle border and shadow.

Avoid low-contrast pale teal labels on pale background. Labels can be teal, but body text and values must be dark.

Button guidance:
- The main run button and fetch button should be visually strong but simple.
- Do not let a Gradio button sit inside a large gray output column. If a button wrapper creates unwanted gray background, use CSS on the button element/classes or simplify the surrounding layout.

## Gradio 6.13.0 Lessons

Critical differences and pitfalls for this specific version:

- `theme` and `css` belong in `demo.launch(...)` in Gradio 6.0+, not the `Blocks(...)` constructor.
- There is no built-in `gr.Map` in Gradio 6.13.0. Use Leaflet in a `gr.HTML` iframe and write clicked lat/lon into Gradio number inputs with DOM events.
- `gr.Plot` supports display, but do not rely on map-click events from Plotly through Gradio. Use the Leaflet iframe for picking.
- `gr.Dropdown` may send `[]` when it has no selected value. Normalize list values before using them as dictionary keys.
- Avoid returning a raw component object when an update is enough. Prefer `gr.update(...)` for choices, value, visibility, and selected tab state.
- To auto-switch tabs, return `gr.update(selected="results_tab")` to the `gr.Tabs` component.
- Hidden or empty status components should be `visible=False` or omitted. Empty visible `HTML/Markdown` blocks can appear as gray UI artifacts.
- Gradio progress messages can show in multiple places during long runs. Keep progress text short and avoid placing status components near large result containers if visual noise matters.

## State Model

Use one `gr.State` dict as the source of truth:

- `area`
  - `center_lat`
  - `center_lon`
  - `polygon`
  - `area_key`
  - `preview`
- `layers`
  - `area` from `client.buildings.get_area(...)`
  - `area_veg` from `client.vegetation.get_area(...)`
  - `area_gm` from `client.ground_materials.get_area(...)`
  - lightweight `building_features` only for the `Layers` map
  - counts for compact status
- `runs`
  - keyed by analysis name
  - each run stores `result`, `station`, and relevant params such as `wind_direction`

Reset `layers` and `runs` when the city or area center changes.

Guard the run path:
- If the end-user clicks `Run` without a prior explicit layer fetch, call the layer fetch internally before submitting the simulation. Never surface "Fetch layers first" as a UI error — only fail if credentials, network, or SDK calls actually fail.

## SDK Integration Flow

Area setup:
- Build the 1 km circle as GeoJSON with coordinates in `[longitude, latitude]`.
- Fetch:
  - `client.preview_area(polygon)` for cost/context preview if desired.
  - `client.buildings.get_area(polygon)`.
  - `client.vegetation.get_area(polygon)`.
  - `client.ground_materials.get_area(polygon)`.

Run:
- `wind-speed`:
  - `WindModelRequest`.
  - Needs `latitude`, `longitude`, `wind_speed`, `wind_direction`.
  - Does not need `TimePeriod`.
  - `wind_direction` is meteorological "from" direction.
- `direct-sun-hours`:
  - `SolarModelRequest` with `AnalysesName.direct_sun_hours`.
  - Needs `latitude`, `longitude`, `TimePeriod`.
  - Does not need weather data.
  - Requires single-month windows (`start_month == end_month`).
- `thermal-comfort-index`:
  - `UtciModelRequest.from_weatherfile_payload(...)`.
  - Find nearest station with `client.weather.get_weather_file_from_location(...)`.
  - Filter weather with the same `TimePeriod`.
  - Use `UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index)`.

Area execution:
- For UI apps, use async area execution:
  - `client.run_area(...)`
  - poll with `client.check_area_state(schedule)`
  - `client.merge_area_jobs(schedule)` after terminal state
- Pass fetched layers into `run_area(...)`:
  - `buildings=area.buildings`
  - `vegetation=area_veg.features`
  - `ground_materials=ground_materials_for_run(area_gm)` or equivalent guard to avoid huge request bodies.

## Direct Sun Hours Caution

If direct sun hours fails, first check `TimePeriod`:
- `start_month` and `end_month` must be the same month.
- Direct sun hours values are cumulative hours over the filtered month/day/hour set, not a daily average.
- Low sun angles and large tiled polygons can show tile-context shadow artifacts. For demos, prefer mid-day hours and simple single-month windows.

## Map Rendering

Use Leaflet for the `Layers` tab:

- Base map: OpenStreetMap tiles are acceptable for local demos.
- Draw the 1 km circle and center marker.
- Draw fetched layers in deterministic order:
  1. asphalt
  2. concrete
  3. soil
  4. vegetation
  5. water
  6. buildings
  7. trees
- Use fetched building polygons only in the `Layers` tab.
- Do not overlay buildings/trees on result plots unless needed. It slows rendering and can make result failures harder to debug.

For click picking:
- A Leaflet click should update the Gradio `Lat` and `Lon` `Number` inputs.
- Re-fetch layers after changing the center.

## Result Rendering

Use Plotly heatmaps for results:

- Convert `result.merged_grid` to a float `numpy` array.
- Preserve `NaN` outside the polygon.
- Use `result.min_legend` and `result.max_legend` when present.
- Always guard for `None` legend fields with finite-grid fallbacks.
- Keep Plotly result traces simple: one heatmap is the reliable baseline.
- Use `Turbo` or another high-contrast sequential palette only if analysis-specific server palettes are not being used.

Color mapping guidance:
- For exact SDK palette consistency, use `client.weather.gen_grid_image(grid=result.merged_grid.tolist(), analysis_type=<analysis>)` and display the generated PNG.
- For interactive Plotly, use legend bounds and choose analysis-appropriate colors:
  - wind: sequential blue/teal or `Turbo`, units m/s.
  - direct sun hours/daylight: yellow-orange sequential scale, units hours.
  - UTCI: thermal scale, units °C, with KPIs for mean, p90, heat-stress share, and strong heat-stress share.

Wind arrow:
- If drawing a wind arrow in Plotly, remember `wind_direction` is "from".
- Plotly annotation arrows cannot use `axref="paper"` in this environment. Use `axref="pixel"` and `ayref="pixel"` for arrow offsets, or draw a small shape/annotation in data coordinates.

## Results Sync Behaviour

Make result state feel automatic:

- After a run completes:
  - save it under `runs[analysis]`.
  - update the result dropdown choices.
  - set dropdown value to the completed analysis.
  - render that result plot and KPIs.
  - return `gr.update(selected="results_tab")` for the left tabs.
- When the user changes the analysis selector:
  - update visible controls.
  - if `runs[analysis]` exists, update result dropdown/plot/KPIs and switch to `Results`.
  - if no run exists, keep the map as-is and show the relevant controls only.

## KPI Placement

Put KPIs only in the `Results` tab.

Recommended KPIs:
- all analyses:
  - mean
  - p90
  - valid cell count
- UTCI:
  - heat stress share (`>=32°C`)
  - strong heat stress share (`>=38°C`)
- wind:
  - mean m/s
  - p90 m/s
  - incoming direction
- direct sun hours:
  - mean hours
  - p90 hours
  - optional hours/day if the app computes number of days

Do not duplicate KPIs in the right run sidecar.

## App Acceptance Checklist

Before considering the app done:

- The app imports with `gradio==6.13.0`.
- `socksio` is installed if the environment uses SOCKS proxies.
- The Leaflet map appears in the `Layers` tab and map clicks update lat/lon.
- `Fetch layers` renders layer polygons in the fixed order.
- `Run` works even if the user skipped explicit layer fetch.
- Wind controls show only speed/direction.
- Direct sun and UTCI controls show only time inputs.
- Month is full width; start/end day are one row; start/end hour are one row.
- Results switch automatically to `Results` after a run.
- Selecting an already-completed analysis switches to its result.
- Result Plotly rendering uses one heatmap trace by default.
- Result rendering does not fail on missing `min_legend` / `max_legend`.
- No empty gray status slabs are visible.
- Text contrast is strong enough to read in screenshots.

## Related References

- `../00-setup.md`
- `../02-geometry.md`
- `../03-time-period.md`
- `../05-area-api.md`
- `../07-images.md`
- `../analyses/01-wind-speed.md`
- `../analyses/04-direct-sun-hours.md`
- `../analyses/07-thermal-comfort-utci.md`
- `../interpretation/grid-conventions.md`
- `../interpretation/solar-results.md`
- `../interpretation/thermal-results.md`
- `../interpretation/wind-results.md`
