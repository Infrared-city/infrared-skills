# Thermal comfort results

## thermal-comfort-index (UTCI)

Returns UTCI in **°C** per pixel at pedestrian height (~1.5 m). Point-in-time for the chosen `time_period` — not an annual aggregate.

Output grid conventions match wind: 2-D `merged_grid`, NaN outside polygon, 1 m cell pitch, row 0 = south.

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

Returns **% of time** (0–100) per pixel that the location falls into the chosen stress class, over a season × hours-of-day window.

Three subtypes — `thermal-comfort` (% comfortable hours, UTCI 9–26°C), `heat-stress` (% UTCI ≥ 26°C), `cold-stress` (% UTCI ≤ 9°C). **TCS subtype is per-call** — to get all three, run three separate jobs.

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
