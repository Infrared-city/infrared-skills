# Solar results

Grid layout (cell pitch, NaN, row/column orientation, legend bounds, scenario diffs, GeoTIFF export) is shared across analyses — see [grid-conventions.md](grid-conventions.md). This file covers solar units, classes, and gotchas.

## solar-radiation

Cumulative solar irradiance on the ground per pixel in **kWh/m²** over the requested `TimePeriod` (per-window — e.g. per-month if the window covers one month).

| kWh/m² (monthly) | Class |
|---|---|
| < 85 | Heavily shaded |
| 85–100 | Partial |
| 100–120 | Mostly sunny |
| > 120 | Full sun |

Annual horizontal totals: ~1,000–1,200 kWh/m² (Central Europe), ~1,500–1,800 (Mediterranean). Requires hourly weather (`SolarRadiationModelRequest.from_weatherfile_payload(...)` is the easy path; see [../python/weather-and-time.md](../python/weather-and-time.md)).

**Pitfalls:** energy density (kWh/m²), not power (W/m²); season matters (60 kWh/m² in January is normal, in July signals occlusion); the default grid raster represents the simulated ground/canopy surface — to get results **on** building facades or roofs, use `analysis_surfaces` ([analyses/09-facade-terrain.md](../analyses/09-facade-terrain.md)), which returns a `SurfaceAnalysisResult` rather than a grid ([../surface-results-integration.md](../surface-results-integration.md)).

## daylight-availability

The **share of the window with enough daylight** per pixel (percent, 0 to 100). Conceptually sDA-like — not lux. Classify it as a fraction of the window.

| Fraction of window with daylight | Class |
|---|---|
| < 0.30 | Poorly lit |
| 0.30–0.50 | Adequate for transit |
| 0.50–0.70 | Good for seating / casual use |
| > 0.70 | Excellent — open or south-facing |

**Pitfalls:** not lux — don't compare to indoor lighting standards; absolute hours scale with the time window so don't compare runs with different `TimePeriod`s without normalising; an annual fraction hides huge winter/summer variation — pair with `direct-sun-hours` to disambiguate diffuse-only vs direct-sun coverage.

## direct-sun-hours

Cumulative hours of direct (un-occluded) sunlight per pixel, **summed across the filtered hour set in `TimePeriod`** (cross-product of days × hours-of-day, NOT a continuous range — see `../03-time-period.md`). So `(month=6, day=1..30, hour=11..14)` sums ~120 hours per cell, not ~700. Keep the hour window inside daylight: on the grid path a night sample counts as sun (a 24-hour window reads 24.0 h on open ground). Within a single month a 06–20 window reaches 15 h × days at fully sunlit pixels. Not a per-day average. Always normalise before classifying — divide by the filtered hour count (`days_in_window × hours_per_day`) for a universal `hrs/day` reading.

| hrs/day (cell_hours / days_in_window) | Class |
|---|---|
| < 2 | Heavily shaded |
| 2–5 | Partial sun |
| 5–8 | Significant sun |
| > 8 | Near-astronomical max (open rooftop, summer) |

`max_legend` is the exact maximum of this run, not the window length. For cross-run comparison, normalise first (hrs/day, fraction of run max, or fraction of theoretical daylight at `lat/lon`).

**Pitfalls:** **night hours in the window count as sun on the grid path** — `grid.max()` reaching the window's sample count although the window includes night hours is the smell; see [`../analyses/04-direct-sun-hours.md`](../analyses/04-direct-sun-hours.md#keep-the-window-inside-daylight); astronomical, **not weather-corrected** — cloud cover not subtracted, so reported hours overstate cloudy regions; absolute values scale with the filtered hour count — never compare raw hour grids across different `TimePeriod`s; high summer values can be a heat-stress driver, not an amenity; **low sun angles on multi-tile polygons can show seam artefacts** because buildings outside a tile's 128 m context margin don't cast shadows across tile boundaries — avoid early-morning / late-afternoon hours and winter months when the polygon spans multiple tiles, or fall back to a single-tile polygon. Use `estimate_sun_context_loss(polygon, latitude, longitude, time_period)` from `infrared_sdk` to gauge the loss before submission. In 1.0 no layer adds shade from beyond 128 m.

## sky-view-factors

Percent **0–100**, geometric (no time dependence). 0 = obstructed, 100 = full sky visible.

| SVF | Class |
|---|---|
| < 30 | Enclosed (deep canyon, dense canopy) |
| 30–60 | Partial |
| 60–80 | Open |
| > 80 | Exposed (rooftops, open plazas) |

If every pixel reads 100 you forgot to load buildings.

**Pitfalls:** low SVF cuts both ways (less daytime gain *and* less nighttime cooling); not the same as shade — a high-SVF point can still be in shade for hours.

## See also

- [grid-conventions.md](grid-conventions.md) — shared grid/plot/diff/GeoTIFF conventions
- `../analyses/03-daylight-availability.md`, `04-direct-sun-hours.md`, `05-sky-view-factors.md`, `06-solar-radiation.md` — payload references
