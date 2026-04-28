# Thermal comfort results

Grid layout (cell pitch, NaN, row/column orientation, legend bounds, scenario diffs, GeoTIFF export) is shared across analyses — see [grid-conventions.md](grid-conventions.md). This file covers UTCI units, stress classes, and TCS subtype semantics.

## thermal-comfort-index (UTCI)

Returns UTCI in **°C** per pixel at pedestrian height (~1.5 m). Point-in-time for the chosen `time_period` — not an annual aggregate.

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

**Pitfalls:** point-in-time only; varies sharply with surface material — don't average across material classes; sunny asphalt vs shaded grass can differ 10–15°C three metres apart.

## thermal-comfort-statistics (TCS)

Returns **% of time** (0–100) per pixel that the location falls into the chosen stress class.

The "season × hours-of-day window" comes entirely from the `TimePeriod` you pass — there is no separate season or hours enum. Cascade filter: months, then days within those months, then hours within those days. Example: `TimePeriod(6, 1, 9, 8, 31, 17)` = Jun-Aug, all days, 09:00–17:00 — the classic "summer daytime" window.

Three subtypes via `TcsSubtype` (per-call — to get all three, run three jobs):

| Member | Enum value | Meaning |
|---|---|---|
| `TcsSubtype.thermal_comfort` | `"thermal-comfort"` | % hours comfortable (UTCI 9–26°C) |
| `TcsSubtype.heat_stress` | `"heat-stress"` | % hours with heat stress (UTCI ≥ 26°C) |
| `TcsSubtype.cold_stress` | `"cold-stress"` | % hours with cold stress (UTCI ≤ 9°C) |

| Comfort % | Quality |
|---|---|
| > 70 | Excellent |
| 50–70 | Good |
| 30–50 | Moderate |
| < 30 | Poor |

| Stress % | Severity |
|---|---|
| > 60 | Extreme |
| 40–60 | High |
| 20–40 | Moderate |
| < 20 | Low |

**Pitfalls:** % of the season ∩ hours window, not of the year; subtypes are computed independently per cell — they don't necessarily sum to 100; results are sensitive to which weather file is used — keep it constant when comparing designs.

## See also

- [grid-conventions.md](grid-conventions.md) — shared grid/plot/diff/GeoTIFF conventions
- `../analyses/07-thermal-comfort-utci.md` — UTCI payload reference
- `../analyses/08-thermal-comfort-statistics.md` — TCS payload + subtype reference
- `../03-time-period.md` — cascade-filter semantics for the season × hours window
