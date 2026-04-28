# Solar results

Output grids share the same conventions as wind: 2-D `merged_grid: numpy.ndarray`, NaN outside polygon, row 0 = south, 1 m cell pitch. Use `result.min_legend` / `result.max_legend` for plot bounds.

## solar-radiation

Cumulative shortwave irradiance per pixel in **kWh/m²** over the requested `time_period` (so the unit is per-window — e.g. per-month if `time_period` covers one month).

Typical horizontal-ground monthly values: < 85 heavily shaded, 85–100 partial, 100–120 mostly sunny, > 120 full sun. Annual horizontal totals: ~1,000–1,200 kWh/m² (Central Europe), ~1,500–1,800 (Mediterranean).

Requires hourly weather (`SolarRadiationModelRequest.from_weatherfile_payload(...)` is the easy path).

**Pitfalls:** energy density (kWh/m²), not power (W/m²); season matters (60 in January is normal, in July signals occlusion); raster represents the simulated ground/canopy surface, not vertical facades.

## daylight-availability

**Percentage of analysed time** with sufficient natural light per pixel (0–100). Conceptually sDA-like — not lux.

< 30 = poorly lit, 30–50 = adequate for transit, 50–70 = good for seating, > 70 = excellent.

**Pitfalls:** not lux, don't compare to indoor lighting standards; an annual % hides huge winter/summer variation — pair with `direct-sun-hours` to disambiguate.

## direct-sun-hours

Cumulative hours of direct (un-occluded) sunlight per pixel, scaled by `time_period` (commonly read as **hours/month**). Astronomical maximum ~250–300 hrs/month.

< 85 heavily shaded, 85–170 partial, 170–250 significant, > 250 near-max.

**Pitfalls:** astronomical, **not weather-corrected** — cloud cover not subtracted; values scale with the time window (a 7-day request returns 7-day totals); high summer values can be a heat-stress driver, not an amenity.

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
