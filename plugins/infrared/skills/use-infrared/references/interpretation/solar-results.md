# Solar results

## solar-radiation

Cumulative shortwave irradiance per pixel in **kWh/m²/month** over the requested `time_period`.

Typical horizontal-ground monthly values: < 85 heavily shaded, 85–100 partial shade, 100–120 mostly sunny, > 120 full sun. Annual totals: ~1,000–1,200 kWh/m²/year (Central Europe), ~1,500–1,800 (Mediterranean).

**Pitfalls:** energy density (kWh/m²), not power (W/m²); season matters (60 in January is normal, in July signals occlusion); raster represents the simulated ground/canopy surface, not vertical facades.

## daylight-availability

**Percentage of analysed time** with sufficient natural light, per pixel (0–100). Conceptually sDA-like — not lux.

< 30 = poorly lit, 30–50 = adequate for transit, 50–70 = good for seating, > 70 = excellent.

**Pitfalls:** not lux, don't compare to indoor lighting standards; an annual % hides huge winter/summer variation — pair with `direct-sun-hours` to disambiguate.

## direct-sun-hours

Cumulative hours of direct (un-occluded) sunlight per pixel, in **hours/month**. Astronomical maximum is ~250–300 hrs/month.

< 85 heavily shaded, 85–170 partial, 170–250 significant, > 250 near-max.

**Pitfalls:** astronomical, **not weather-corrected** — cloud cover is not subtracted; values scale with the time window (a 7-day request returns 7-day totals); high summer values can be a heat-stress driver, not an amenity.

## sky-view-factor

Dimensionless **0–1**, geometric (no time dependence). 0 = obstructed, 1 = full sky visible.

Realistic plaza centroids: 0.7–0.85. Rooftops: 0.9–1.0. If every pixel reads 1.0 you forgot to load buildings.

**Pitfalls:** low SVF cuts both ways (less daytime gain *and* less nighttime cooling); not the same as shade — a high-SVF point can still be in shade for hours.
