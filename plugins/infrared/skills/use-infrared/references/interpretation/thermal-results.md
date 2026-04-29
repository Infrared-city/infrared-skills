# Thermal comfort results

Grid layout (cell pitch, NaN, row/column orientation, legend bounds, scenario diffs, GeoTIFF export) is shared across analyses — see [grid-conventions.md](grid-conventions.md). This file covers UTCI units, stress classes, and TCS subtype semantics.

## thermal-comfort-index (UTCI)

Returns the **UTCI equivalent temperature in °C** per pixel at pedestrian height (~1.5 m) — felt temperature combining air temperature, mean radiant temperature (MRT), humidity, and wind. The grid represents the filtered `time_period` window (not a single instant, not an annual mean) — interpret it as the representative value across the filtered hours.

| UTCI (°C) | Stress class |
|---|---|
| > 38 | Strong-to-extreme heat stress — dangerous |
| 32–38 | Strong heat stress |
| 26–32 | Moderate heat stress |
| **9–26** | **No thermal stress (comfortable)** |
| 0–9 | Slight cold stress |
| < 0 | Moderate-to-extreme cold stress |

(The codebase implements the full ISO/Bröde 10 categories; this collapses the extreme tails.)

UTCI is driven by air temperature, wind, humidity, and mean radiant temperature (MRT). Hourly weather and a `Location` (lat/lon for sun position) are required. **MRT is computed internally** from geometry + radiation — don't try to pass it. Use `UtciModelRequest.from_weatherfile_payload(...)`.

**Pitfalls:** aggregated over the chosen `time_period` window (not a single instant, not annual); varies sharply with surface material — don't average across material classes; sunny asphalt vs shaded grass can differ 10–15°C three metres apart.

## thermal-comfort-statistics (TCS)

Returns the **time spent** in the chosen UTCI band per pixel — count of filtered hours that fell in that band (range `0` to the total length of the requested window in hours). Divide by the window length to get a fraction / `% time`. The same window length applies to every cell in a run, so absolute hours and the derived fraction are interchangeable for ranking.

The "season × hours-of-day window" comes entirely from the `TimePeriod` you pass — there is no separate season or hours enum. Cascade filter: months, then days within those months, then hours within those days. Example: `TimePeriod(start_month=6, start_day=1, start_hour=9, end_month=6, end_day=30, end_hour=17)` = June, all days, 09:00–17:00. (`TimePeriod` is Pydantic v2 — kwargs only.)

> **Server-side limitation (as of 2026-04):** TCS / UTCI / Solar runs currently fail with `DNI length N != sun_vectors M` for multi-month windows — `sun_vectors` is not yet computed across full multi-month periods. Until fixed, run sequential single-month TCS jobs and aggregate client-side if you need a multi-month summary. See `references/03-time-period.md`.

Three subtypes via `TcsSubtype` (per-call — to get all three, run three jobs):

| Member | Enum value | Meaning |
|---|---|---|
| `TcsSubtype.thermal_comfort` | `"thermal-comfort"` | Hours comfortable (UTCI 9–26°C) |
| `TcsSubtype.heat_stress` | `"heat-stress"` | Hours with heat stress (UTCI ≥ 26°C) |
| `TcsSubtype.cold_stress` | `"cold-stress"` | Hours with cold stress (UTCI ≤ 9°C) |

The grid stores absolute hours; the `% time` framing is just `cell_hours / window_total_hours`.

**Pitfalls:** absolute hours scale with the time window — a 7-day request returns 7-day totals, so do NOT compare runs with different `TimePeriod`s without normalising; subtypes are computed independently per cell and do not necessarily cover the whole window between them; results are sensitive to which weather file is used — keep the EPW constant when comparing designs.

## See also

- [grid-conventions.md](grid-conventions.md) — shared grid/plot/diff/GeoTIFF conventions
- `../analyses/07-thermal-comfort-utci.md` — UTCI payload reference
- `../analyses/08-thermal-comfort-statistics.md` — TCS payload + subtype reference
- `../03-time-period.md` — cascade-filter semantics for the season × hours window
