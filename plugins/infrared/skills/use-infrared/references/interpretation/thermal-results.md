# Thermal comfort results — interpretation guide

> **Draft 2026-04-28** — generated from AIBackend mining. Items flagged `[REVIEW]` need product confirmation.

## UTCI (Universal Thermal Climate Index)

### Output schema

The `thermal-comfort-index` analysis returns a 2-D field of UTCI values across the analysis tile.

- **GeoTIFF raster** (single float band, georeferenced) — one UTCI value per pixel at pedestrian height (~1.5 m).
- **GeoJSON** sidecar with tile bounding box and any categorical bins, in `EPSG:4326` (WGS84).
- **PNG overlay** for visualisation.

| Field | Type | Unit | Notes |
|---|---|---|---|
| Raster band 1 | `float32` | °C (UTCI) | Per-pixel apparent temperature |
| `bbox` | `[lon_min, lat_min, lon_max, lat_max]` | degrees | Tile extent |
| `crs` | string | — | `EPSG:4326` |

Stats summary (when loaded via the SDK helper): `min`, `max`, `mean`, `median`, `std`, percentiles (`p10`, `p25`, `p50`, `p75`, `p90`), `binned_distribution` (one entry per UTCI category with `count`, `percent`, `range_min`, `range_max`), `spatial_coverage` (`valid_pixels`, `coverage_percent`).

### Thermal-stress categories (ISO/Bröde 2012)

The codebase implements the full ten-category UTCI scale. Bin edges (left-inclusive, right-exclusive):

| UTCI (°C) | Category | Comfort |
|---|---|---|
| < −40 | Extreme cold stress | dangerous |
| −40 to −27 | Very strong cold stress | uncomfortable |
| −27 to −13 | Strong cold stress | uncomfortable |
| −13 to 0 | Moderate cold stress | acceptable |
| 0 to 9 | Slight cold stress | comfortable |
| 9 to 26 | **No thermal stress** | **comfortable** |
| 26 to 32 | Moderate heat stress | acceptable |
| 32 to 38 | Strong heat stress | uncomfortable |
| 38 to 46 | Very strong heat stress | dangerous |
| > 46 | Extreme heat stress | dangerous |

These match the standard exactly. No deviation from Bröde 2012.

### Inputs (what drives UTCI)

UTCI is computed from four physical drivers; the user supplies (or accepts resolved) hourly weather data for the location:

- **Air (dry-bulb) temperature** — ambient °C (`dryBulbTemperature`).
- **Wind speed** — m/s at 10 m, internally adjusted (`windSpeed`).
- **Relative humidity** — % (`relativeHumidity`).
- **Mean Radiant Temperature (MRT)** — derived internally from solar exposure of the site geometry plus radiation channels (`globalHorizontalRadiation`, `directNormalRadiation`, `diffuseHorizontalRadiation`, `horizontalInfraredRadiationIntensity`).

In the SDK these are bundled by `UtciModelRequest` (via `ThermalModelRequestWeatherDataMixin`) and a `time_period` window. The convenience constructor `UtciModelRequest.from_weatherfile_payload(...)` ingests a `list[WeatherDataPoint]` and extracts the seven fields automatically — **you do not pass MRT directly**; the platform reconstructs the radiative environment from geometry + radiation inputs.

### Time aggregation

UTCI is **point-in-time** in the report bundle workflow: pick a `month` (1–12) and an `hours` slot (`morning`, `noon`, `afternoon`, `evening`). Default in `report_bundle_workflow.py` is `month=7, hours=noon` (peak-summer noon). The lower-level SDK request takes a `TimePeriod` window and returns the field for that window.

### Common interpretation traps

- UTCI is a **point-in-time field** for one weather snapshot — it does not tell you how often a place is comfortable across the year. For that, run TCS.
- The user does **not** supply MRT directly — it is computed internally from solar exposure of buildings, ground and (optionally) vegetation. Changing geometry, ground material or trees changes MRT and therefore UTCI.
- UTCI varies sharply across small distances: a sunlit asphalt patch can be 10–15 °C hotter than shaded grass three metres away. **Do not average across surface-material classes** when comparing design options — compare like-with-like (e.g. seating zones, walking spines).
- Wind speed below ~0.5 m/s is treated as effectively still; tiny CFD wakes can make local UTCI look colder than it really is.
- The default report uses noon in July. A site that looks "fine" at noon may be problematic at 16:00 (lagging surface temperatures) — re-run with `hours=afternoon` if the brief is about late-day occupancy.
- The 9–26 °C "no thermal stress" band is wide; treat values near 26 °C as a *warning*, not a green light, when humidity is high.

### Architect's quick-decision guide

| UTCI at pedestrian height | What to do |
|---|---|
| > 38 °C (very strong heat stress) | Site not occupiable in this scenario. Add deep shade (canopy / trees / pergola) and increase air movement. |
| 32–38 °C (strong heat stress) | Add shading and vegetation; introduce evaporative surfaces (water, planting). Re-check after intervention. |
| 26–32 °C (moderate heat stress) | Acceptable for short stays / transit. For seating or play, add partial shade. |
| 9–26 °C (no thermal stress) | Comfortable. Preserve current sun/wind balance. |
| 0–9 °C (slight cold stress) | OK for activity. For lingering uses, add solar access and wind shelter. |
| < 0 °C (moderate cold stress and below) | Provide wind shelter, southern solar exposure, warm materials underfoot. Avoid wind-funnel geometry. |

## TCS (Thermal Comfort Statistics)

### Output schema

The `thermal-comfort-statistics` analysis returns a per-pixel raster where each value is a **percentage of time** (0–100) the pixel falls into the requested thermal-stress class over the requested season + hours window. Companion outputs (GeoTIFF + GeoJSON + PNG) match the UTCI envelope.

| Field | Type | Unit | Notes |
|---|---|---|---|
| Raster band 1 | `float32` | % of hours in window | One pixel = one fraction-of-time |
| `subtype` | enum | — | `thermal-comfort` / `heat-stress` / `cold-stress` |
| `season` | enum | — | `full-year` / `winter` / `spring` / `summer` / `autumn` |
| `hours` | enum | — | `morning` / `noon` / `afternoon` / `evening` |

### Statistic definitions

**TCS is exceedance-fraction (percentage-of-hours), not percentile.** From `TcsSubtype`:

- `thermal-comfort` — % of hours with UTCI in the 9–26 °C "no thermal stress" band.
- `heat-stress` — % of hours with UTCI ≥ 26 °C (any heat-stress class).
- `cold-stress` — % of hours with UTCI ≤ 9 °C (any cold-stress class).

Interpretive bands (guidance-level, not standardised):

| Heat / cold stress % | Interpretation |
|---|---|
| < 20 | Low — rarely uncomfortable |
| 20–40 | Moderate — sometimes uncomfortable |
| 40–60 | High — often uncomfortable |
| > 60 | Extreme — usually uncomfortable |

| Comfort % | Interpretation |
|---|---|
| > 70 | Excellent — very usable space |
| 50–70 | Good — reasonably usable |
| 30–50 | Moderate — limited usability |
| < 30 | Poor — problematic space |

`[REVIEW]` Exact UTCI cutoffs the backend uses to classify each hour into the three subtypes (whether boundaries are 9/26 °C strict or include moderate-stress as comfortable) need product confirmation. The categorical thresholds in `services/stats_service.py` follow the standard 9 and 26 °C boundaries.

### Time aggregation

TCS is **window-aggregated**, not instantaneous. Pick:

- A **season** (`full-year`, `winter`, `spring`, `summer`, `autumn`) — set of months sampled.
- A **time-of-day slot** (`hours` = `morning` / `noon` / `afternoon` / `evening`).

Result = fraction of (season ∩ hours) hours during which each pixel sits in the requested stress class. Default: `subtype=thermal-comfort, season=summer, hours=noon`.

### Common interpretation traps

- TCS values are **percentages of a window**, not absolute hour counts. A pixel showing 40% heat-stress for `season=summer, hours=noon` means 40% of summer noon-slot hours, not 40% of the year.
- Three subtypes are **not complementary across all UTCI values**: comfort + heat + cold do not necessarily sum to 100% depending on how moderate-stress hours are bucketed (see [REVIEW] above). Use them as independent indicators, not as a probability partition.
- A high `thermal-comfort` % during summer-noon does not imply a usable space year-round — re-run with `season=winter` or `full-year` for occupied public space.
- TCS is sensitive to the **weather file** chosen for the location. Two TMY files for the same city can shift comfort percentages by 5–10 points. Document which weather source was used.
- Geometry, vegetation and ground-material inputs strongly modulate TCS via MRT — comparing "before" and "after" designs must hold the weather input fixed.
- Don't compare TCS values across different `hours` slots directly: noon and evening are sampled from different hour pools.

## Source files mined (private repo references — internal only)

- `AIBackend/services/stats_service.py` — UTCI 10-category thresholds, binning logic
- `AIBackend/workflows/metrics_reference.md` — public-facing UTCI table, TCS interpretation bands
- `AIBackend/schemas/report_workflow.py` — `Hours`, `UtcHours`, `Season`, `ThermalComfortSubtype` enums
- `AIBackend/services/report_bundle_workflow.py` — defaults, methodology
- `AIBackend/services/simulation_service.py` — weather-required process list
- `infrared-api-sdk/src/infrared_sdk/analyses/types.py` — `TcsSubtype`, `UtciModelRequest`, `TcsModelRequest`
- `infrared-api-sdk/src/infrared_sdk/models.py` — `Location`, `WeatherDataPoint`, `extract_weather_fields`
