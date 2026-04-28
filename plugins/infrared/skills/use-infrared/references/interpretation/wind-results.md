# Wind results

Grid layout (cell pitch, NaN, row/column orientation, legend bounds, scenario diffs, GeoTIFF export) is shared across analyses — see [grid-conventions.md](grid-conventions.md). This file covers wind units, classes, and gotchas.

## wind-speed

Returns a 2-D `merged_grid` of wind magnitude in **m/s** at pedestrian level (~1.5 m) for one (speed, direction) inflow.

| m/s | Feel |
|---|---|
| < 1.5 | Calm, may feel stagnant in heat |
| 1.5–3.5 | Comfortable |
| 3.5–6 | Breezy |
| > 6 | Strong / uncomfortable for sitting |

`wind_speed` payload field is `int` 1–100. Don't pass floats from weather data.

**Pitfalls:** single-direction snapshot (run several to estimate annual exposure); `wind_direction=270` means wind **from** the west; NaN ≠ zero.

## pedestrian-wind-comfort (PWC)

Returns a 2-D grid where each cell is a **comfort class index** (0 = best, higher = worse), under one of several criteria. Each criterion bins the *probability* (over the weather time series) that wind speed at that cell exceeds a fixed threshold; the class is the worst bin a cell falls into.

### Classes — Lawson LDDC

This is the criterion we use by default and the one to communicate to users.

| Class | Index | Activity / feel |
|---|---|---|
| A | 0 | Sitting long (cafés, parks, plazas) — calm, suitable for prolonged stationary use |
| B | 1 | Sitting short (waiting, brief stops) — light breeze |
| C | 2 | Standing / strolling (entrances, transitions) — moderate flow |
| D | 3 | Walking (sidewalks, busy routes) — windy, marginal for lingering |
| E | 4 | Business walking — uncomfortable for stationary use; flags safety-level exposure |

The SDK output range is `int 0–4` for PWC. **For default reporting, anything class E is flagged as a hotspot.**

**Pitfalls:** values are class indices, not speeds — don't average; use mode or area-share. Frequency-based over the weather time series — re-running with summer-only vs annual weather shifts classes.

## See also

- [grid-conventions.md](grid-conventions.md) — shared grid/plot/diff/GeoTIFF conventions
- `../analyses/01-wind-speed.md` — wind-speed payload reference
- `../analyses/02-pedestrian-wind-comfort.md` — PWC payload + criteria options
