# Wind results

## wind-speed

Returns a 2-D `merged_grid: numpy.ndarray` of wind magnitude in **m/s** at pedestrian level (~1.5 m), one (speed, direction) inflow. **Cell pitch is 1 m × 1 m.** Cells outside polygon = `NaN`. Row 0 = south, column 0 = west. Use `result.min_legend` / `result.max_legend` for plot bounds.

| m/s | Feel |
|---|---|
| < 1.5 | Calm, may feel stagnant in heat |
| 1.5–3.5 | Comfortable |
| 3.5–6 | Breezy |
| > 6 | Strong / uncomfortable for sitting |

`wind_speed` payload field is `int` 1–100. Don't pass floats from weather data.

**Pitfalls:** single-direction snapshot (run several to estimate annual exposure); `wind_direction=270` means wind **from** the west; NaN ≠ zero.

## pedestrian-wind-comfort (PWC)

Returns a 2-D grid where each cell is a **comfort class index** (0 = best, higher = worse), under one of several criteria (Lawson LDDC, Lawson 1970/2001, Davenport, NEN-8100 comfort, NEN-8100 safety, VDI-3787).

Most criteria run A → E (A best, E uncomfortable) and add an S (or S15/S20) class for unsafe. Two exceptions:
- **NEN-8100 comfort** stops at E (no S class).
- **NEN-8100 safety** has only A/B/C (C = dangerous).

For default reporting, anything class E or worse is flagged as a hotspot.

**Pitfalls:** values are class indices, not speeds — don't average; use mode or area-share. Class meaning depends on the chosen `criteria` — carry it alongside the grid. Frequency-based (over a weather time series), not instantaneous; re-running with summer-only weather will shift classes.
