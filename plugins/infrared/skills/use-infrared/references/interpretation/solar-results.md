# Solar results — interpretation guide

> **Draft 2026-04-28** — generated from AIBackend mining. Items flagged `[REVIEW]` are model-internals kept out of the public skill pending product confirmation.

This guide helps you interpret outputs from four solar-family analyses returned by the `infrared-sdk` (PyPI). Each analysis returns gridded results over a tiled site bbox; the SDK orchestrates tiling and gives you back a job whose results you download as raster + statistics.

## Solar Radiation

### Output schema
- **Raster**: a 2D grid of cumulative shortwave solar irradiance per pixel, one band per tile, mosaicked over the requested bbox. Pixel values are floats in `kWh/m²/month`.
- **Per-tile JSON statistics**: `min`, `max`, `mean`, `median`, `std`, `percentiles` (p10/p25/p50/p75/p90), all floats in the same unit.
- **Histogram / binned distribution**: four bins — `low_pct`, `moderate_pct`, `high_pct`, `extreme_pct` (all 0–100, percent of valid pixels).
- **Spatial coverage**: `total_pixels`, `valid_pixels`, `coverage_percent` (NoData masked).
- **Request type**: `SolarRadiationModelRequest` — caller must pass `time_period`, `diffuse_horizontal_radiation`, `direct_normal_radiation` weather lists. The SDK can populate these via `from_weatherfile_payload` from a resolved EPW.

### Units and value ranges
- Unit: **kWh/m²/month** (cumulative shortwave received per surface element over the requested month/window).
- Realistic urban ranges (horizontal ground / open plaza):
  - Heavily shaded street canyons / north facades: **< 85 kWh/m²/month**
  - Partial shade: **85–100 kWh/m²/month**
  - Mostly sunny: **100–120 kWh/m²/month**
  - Full sun (rooftops, south-facing in summer): **> 120 kWh/m²/month**
- Annual cumulative on horizontal ground in Central Europe sits roughly around 1,000–1,200 kWh/m²/year; Mediterranean 1,500–1,800 kWh/m²/year. Flag isolated pixels above ~250 kWh/m²/month as suspect.

### Time aggregation
- **Default = monthly cumulative**, controlled by `time_period: TimePeriod` (start/end month, day, hour) on `SolarRadiationModelRequest`. Sub-monthly windows are valid if you narrow `time_period`.
- The model integrates pixel-wise direct + diffuse contributions over the chosen window. `[REVIEW]` Internal split of direct vs diffuse is not exposed on the user-facing response — only the cumulative is returned.

### Common interpretation traps
- **Unit confusion**: this is energy density (kWh/m²), not power (W/m²). Don't compare to weather-station instantaneous irradiance.
- **Window matters**: a "low" 60 kWh/m² value in January is normal; the same in July signals heavy occlusion. Always re-bin against the season.
- **Surface orientation**: the raster represents the simulated ground/canopy surface; vertical facade values (south facade Central Europe ~700–1,100 kWh/m²/year) are NOT separately returned by this analysis.
- **Shaded outliers**: pixels well under 30 kWh/m²/month in summer usually indicate persistent geometric occlusion, not bad data.

## Daylight Availability

### Output schema
- **Raster**: per-pixel **percentage of analysed time** with sufficient natural light, float in 0–100.
- **Per-tile statistics**: `min`, `max`, `mean`, `median`, `std`, percentile breakdown — all in `%`.
- **Histogram bins**: `low_pct` (<30%), `moderate_pct` (30–50%), `high_pct` (50–70%), `excellent_pct` (>70%).
- **Request type**: `SolarModelRequest` with `analysis_type = daylight-availability`. Requires `time_period` and `latitude/longitude`.

### Units (sDA / UDI / lux)
- Output is reported as **% of analysed time** with daylight above the platform's threshold — conceptually closest to a **daylight-autonomy / sDA-style metric**, not raw lux and not full LM-83 sDA300/50%.
- Lux is **not** in the response schema — the user-facing field is a percentage. `[REVIEW]` Lux threshold internal to the model is not part of the public contract.
- Annual UDI is **not** computed.

### Value ranges
- < 30% = poorly lit (deep canyon, dense canopy).
- 30–50% = adequate for transit / passing-through.
- 50–70% = good for outdoor seating, retail.
- > 70% = excellent (open plazas, rooftops).
- Central Europe open-plaza values typically land 60–80%; very narrow Mediterranean alleyways can drop to 10–25%.

### Common interpretation traps
- **Not lux**: don't compare to indoor lighting standards or building-code lux thresholds.
- **Not seasonal**: a single annual percentage hides huge winter/summer differences — pair with `direct_sun_hours` to disambiguate.
- **Geometry-driven**: vegetation density and ground roughness change results. Compare like-with-like ground-material assumptions before claiming a design "improves daylight".
- **Saturation effect**: dense urban cores often saturate at 20–35%; small geometric tweaks rarely move the needle without removing buildings or changing height.

## Direct Sun Hours

### Output schema
- **Raster**: per-pixel cumulative hours of direct (un-occluded) sunlight over the analysis window.
- **Per-tile statistics**: `min`/`max`/`median` plus percentiles, unit `hours/month`.
- **Histogram bins**: `low_pct` (<85), `moderate_pct` (85–170), `high_pct` (170–250), `extreme_pct` (>250 hrs/month).
- **Request type**: `SolarModelRequest` with `analysis_type = direct-sun-hours`. Same `time_period` semantics.

### Units and time window
- Unit: **hours/month** (canonical reporting unit).
- Default window = the requested `time_period` aggregated to a monthly total. Sub-monthly windows produce a number scaled to that window — divide by days × 24 for fraction-of-day.
- Astronomical maximum is **~250–300 hrs/month** depending on latitude and month.

### Value ranges
- < 85 hrs/month: heavily shaded, minimal solar warming.
- 85–170: partial sun access.
- 170–250: significant exposure.
- > 250: near-astronomical-max — flag pixels above 350 hrs/month as suspect.
- Central Europe July plazas: 150–220 hrs/month; December: often 20–60 hrs/month. Mediterranean July: 220–300 hrs/month.

### Common interpretation traps
- **Astronomical vs weather-corrected**: the analysis treats the sun as a deterministic geometric source — cloud cover is **not** subtracted. Real lived hours are lower.
- **Not the same as solar radiation**: a south-facing facade can show high sun hours but moderate kWh/m² in winter (low sun angle).
- **Window scaling**: a 7-day request returns hours over 7 days, not normalized — divide manually for "hours per day".
- **Edge pixels**: pixels along tile boundaries can show artefacts; trust statistics over single pixels.
- **Summer high values are not automatically "good"**: in heat-island contexts > 170 hrs/month is a heat-stress driver, not an amenity.

## Sky View Factor

### Output schema
- **Raster**: per-pixel scalar in [0, 1].
- **Per-tile statistics**: `min`/`max`/`median`, unit "0–1".
- **Histogram bins**: `enclosed_pct` (<0.3), `partial_pct` (0.3–0.6), `open_pct` (0.6–0.8), `exposed_pct` (>0.8).
- **Request type**: `SvfModelRequest`. No `time_period` — SVF is geometric and time-independent.

### Convention (0–1 dimensionless)
- 0 = fully obstructed (no sky visible from the point).
- 1 = full upper hemisphere visible (open field / unobstructed rooftop).
- `[REVIEW]` Internal hemispherical-sampling configuration is not part of the public response contract.

### Spatial granularity
- Same gridded raster as the other analyses, mosaicked over the tiled bbox. Resolution is set by the SDK's tiling configuration (per-tile pixel grid). SVF is geometric only — vegetation porosity and ground material do not enter the calculation directly unless geometries explicitly include them.

### Common interpretation traps
- **SVF = 1.0 is rare in cities**: realistic plaza centroids sit 0.7–0.85; rooftops 0.9–1.0; if every pixel reads 1.0 you probably forgot to load buildings.
- **Low SVF cuts both ways**: less daytime solar gain *and* less nighttime longwave cooling — a low-SVF canyon traps heat at night.
- **Not the same as shade**: SVF is hemispheric sky openness, not direct-sun blockage. A point can have high SVF but still be in shade for half the day (a tree directly south).
- **Vegetation handling**: tree crowns may or may not be present in the simulated geometry — verify your `vegetation` payload before comparing scenarios.
- **Centred on a horizontal upward hemisphere**: don't use these values to reason about facade-level sky exposure.

## Source files mined (private repo references — internal only)

- `infrared-api-sdk/src/infrared_sdk/analyses/types.py` — request types
- `infrared-api-sdk/src/infrared_sdk/models.py` — `TimePeriod`, `Location`
- `AIBackend/workflows/metrics_reference.md` — canonical user-facing thresholds
- `AIBackend/workflows/workflows/01_heat_island_mitigation.yaml` — output_schema
- `AIBackend/workflows/workflows/02_pedestrian_comfort_optimization.yaml` — daylight schema
- `AIBackend/services/stats_service.py` — statistics structure
- `AIBackend/workflows/workflows/04_year_round_public_space_design_prompts.yaml` — climate-context bins
- `AIBackend/workflows/workflows/10_wind_chill_zone_identification_prompts.yaml` — wind-chill context
