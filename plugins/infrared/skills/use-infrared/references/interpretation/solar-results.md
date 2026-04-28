# Solar results

Grid layout (cell pitch, NaN, row/column orientation, legend bounds, scenario diffs, GeoTIFF export) is shared across analyses — see [grid-conventions.md](grid-conventions.md). This file covers solar units, classes, and gotchas.

## solar-radiation

Cumulative shortwave irradiance per pixel in **kWh/m²** over the requested `time_period` (per-window — e.g. per-month if the window covers one month).

| kWh/m² (monthly) | Class |
|---|---|
| < 85 | Heavily shaded |
| 85–100 | Partial |
| 100–120 | Mostly sunny |
| > 120 | Full sun |

Annual horizontal totals: ~1,000–1,200 kWh/m² (Central Europe), ~1,500–1,800 (Mediterranean). Requires hourly weather (`SolarRadiationModelRequest.from_weatherfile_payload(...)` is the easy path).

**Pitfalls:** energy density (kWh/m²), not power (W/m²); season matters (60 kWh/m² in January is normal, in July signals occlusion); raster represents the simulated ground/canopy surface, not vertical facades.

## daylight-availability

**Cumulative hours of usable daylight** per pixel over the chosen `TimePeriod` (range: 0 to period length in hours). Conceptually sDA-like — not lux. Always interpret as a fraction of the window: compute `cell_hours / window_total_hours` first, then classify.

| Fraction of window with daylight | Class |
|---|---|
| < 0.30 | Poorly lit |
| 0.30–0.50 | Adequate for transit |
| 0.50–0.70 | Good for seating / casual use |
| > 0.70 | Excellent — open or south-facing |

**Pitfalls:** not lux — don't compare to indoor lighting standards; absolute hours scale with the time window (7-day request returns 7-day totals) so don't compare runs with different `TimePeriod`s without normalising; an annual fraction hides huge winter/summer variation — pair with `direct-sun-hours` to disambiguate diffuse-only vs direct-sun coverage.

## direct-sun-hours

Cumulative hours of direct (un-occluded) sunlight per pixel, scaled by `time_period` (commonly read as **hours/month**). Astronomical maximum ~250–300 hrs/month at mid-latitudes.

| hrs/month | Class |
|---|---|
| < 85 | Heavily shaded |
| 85–170 | Partial sun |
| 170–250 | Significant sun |
| > 250 | Near-astronomical maximum |

**Pitfalls:** astronomical, **not weather-corrected** — cloud cover not subtracted, so reported hours overstate cloudy regions; absolute values scale with the time window; high summer values can be a heat-stress driver, not an amenity.

## sky-view-factors

Dimensionless **0–1**, geometric (no time dependence). 0 = obstructed, 1 = full sky visible.

| SVF | Class |
|---|---|
| < 0.3 | Enclosed (deep canyon, dense canopy) |
| 0.3–0.6 | Partial |
| 0.6–0.8 | Open |
| > 0.8 | Exposed (rooftops, open plazas) |

If every pixel reads 1.0 you forgot to load buildings.

**Pitfalls:** low SVF cuts both ways (less daytime gain *and* less nighttime cooling); not the same as shade — a high-SVF point can still be in shade for hours.

## See also

- [grid-conventions.md](grid-conventions.md) — shared grid/plot/diff/GeoTIFF conventions
- `../analyses/03-daylight-availability.md`, `04-direct-sun-hours.md`, `05-sky-view-factors.md`, `06-solar-radiation.md` — payload references
