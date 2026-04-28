# Thermal comfort results

## thermal-comfort-utci

Returns UTCI in **°C** per pixel at pedestrian height (~1.5 m). Point-in-time for the chosen `time_period` — not an annual aggregate.

| UTCI (°C) | Stress class |
|---|---|
| > 38 | Very strong heat stress — dangerous |
| 32–38 | Strong heat stress — uncomfortable |
| 26–32 | Moderate heat stress — short stays only |
| **9–26** | **No thermal stress — comfortable** |
| 0–9 | Slight cold stress |
| < 0 | Moderate cold stress and below |

UTCI is driven by air temperature, wind, humidity, and mean radiant temperature (MRT). The user supplies hourly weather; **MRT is computed internally** from geometry + radiation — don't try to pass it.

**Pitfalls:** point-in-time only; varies sharply with surface material — don't average across material classes; default report uses noon in July, re-run with `hours=afternoon` for late-day briefs.

## thermal-comfort-stats (TCS)

Returns **% of time** (0–100) per pixel that the location falls into the chosen stress class, over a season × hours-of-day window.

Three subtypes: `thermal-comfort` (% comfortable hours), `heat-stress` (% hours UTCI ≥ 26°C), `cold-stress` (% hours UTCI ≤ 9°C).

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

**Pitfalls:** % of the season ∩ hours window, not of the year; subtypes don't necessarily sum to 100; results are sensitive to which weather file is used — keep it constant when comparing designs.
