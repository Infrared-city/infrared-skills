# Analyses at a glance

One row for each analysis: what it computes, what it needs, and what it reads from your model.
Detail and code: the numbered pages in [analyses/](analyses/01-wind-speed.md).

| Analysis (`analysis_type`) | Computes (unit) | Key inputs | Request class |
|---|---|---|---|
| `wind-speed` | Wind speed at pedestrian height (m/s), one speed and direction | `wind_speed`, `wind_direction` | `WindModelRequest` |
| `pedestrian-wind-comfort` | Comfort class per cell (Lawson, VDI, Davenport) | hourly `wind_speed` and `wind_direction` lists that you take from a weather file, `criteria` | `PwcModelRequest` |
| `sky-view-factors` | Open sky (%) | geometry only | `SvfModelRequest` |
| `direct-sun-hours` | Hours of direct sun (h) | `time_period`, location | `SolarModelRequest` |
| `daylight-availability` | Share of the window with enough daylight (%) | `time_period`, location | `SolarModelRequest` |
| `solar-radiation` | Solar energy on ground, facades, roofs (kWh/m2 over the window) | direct + diffuse radiation, `time_period` | `SolarRadiationModelRequest.from_weatherfile_payload` |
| `thermal-comfort-index` | UTCI, felt temperature at 1.5 m (C), mean over the window | 7 weather columns, `time_period`, location | `UtciModelRequest.from_weatherfile_payload` |
| `thermal-comfort-statistics` | % of the window in comfort, heat stress or cold stress | as UTCI, plus `subtype` | `TcsModelRequest.from_weatherfile_payload` |
| `daylight-factor` (Beta) | Daylight in a room (%) | rooms, own sensor points | `DaylightFactorModelRequest` |
| `energy-balance` (Beta) | Heating and cooling need (kWh/m2 a) | zones, air temperature, global radiation | `EnergyBalanceModelRequest` |

## Which model reads which input

"Yes" = the input changes the result. "Removed" = the SDK or server removes it and warns.
"Not read" = no effect; do not expect a warning.

| Input | UTCI, TCS | Solar radiation | Sun hours, SVF | Daylight availability | Wind, PWC |
|---|---|---|---|---|---|
| `buildings` | Yes | Yes | Yes | Yes | Yes (clipped at 100 m) |
| facade `material` | Yes (`standard` and `advanced`) | Removed | Removed | Removed | Not read |
| `roof-material` | Only with `physics="advanced"` (else ignored, `ROOF_MATERIAL_ADVANCED_ONLY`) | Removed | Removed | Removed | Not read |
| `vegetation` (trees) | Yes | Yes | Yes | Yes | Not confirmed |
| `ground_materials` | Yes (albedo, `irrigated`, `soil-moisture`, `dt-max`) | Yes (reflectance) | Not read | Not read | Not read |
| `installations` (shape) | Yes, shade | Yes, shade | Yes, every piece opaque | Yes, shade | Not read (`INSTALLATIONS_WIND_NOT_MODELLED` on UTCI says so) |
| installation `transmittance` | Yes | Yes | Removed (`MATERIAL_NOT_SUPPORTED`) | Yes | Not read |
| installation `pv` preset | Shade like an opaque piece | Shade + `pv_yield` | Opaque | Shade | Not read |
| `physics` | `standard` / `advanced` | not a field | not a field | not a field | not a field |

## Physics tiers (UTCI and TCS only)

- `standard` (default): the full daytime model. It reads facade `material`, trees, ground,
  `irrigated` ground and installations.
- `advanced`: adds the `roof-material` and the ground afterglow after sunset. **In daytime at
  street level it gives almost the same grid as `standard`.** Do not sell `advanced` as a
  daytime improvement; use it for evening and night windows and for roof materials.
- `advanced-moist` is the old name of `standard`. `v1` and `detail` are retired: they run as
  `standard` with `PHYSICS_TIER_RETIRED`. A typo raises before any job, with the valid values.

## Read the numbers honestly

- UTCI is one aggregate over the window, not one hour. Do not call night values validated.
- Solar radiation is one total for each cell over the window: there are no hourly values.
- All results are screening grade: good to rank design variants, not a replacement for a
  certified simulation.
