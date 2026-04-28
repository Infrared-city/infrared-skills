# Wind results

## wind-speed

Returns a 2-D grid of wind magnitude in **m/s** at pedestrian level (~1.5 m), one (speed, direction) inflow.

| m/s | Feel |
|---|---|
| < 1.5 | Calm, may feel stagnant in heat |
| 1.5–3.5 | Comfortable |
| 3.5–6 | Breezy |
| 6–8 | Strong, uncomfortable for sitting |
| > 10 | Unsafe — design red flag |

`merged_grid` is a `numpy.ndarray`; cells outside polygon = `NaN`. Row 0 = south, column 0 = west.

**Pitfalls:** single-direction snapshot (run several to estimate annual exposure); `wind_direction=270` means wind **from** the west; NaN ≠ zero.

## pedestrian-wind-comfort (PWC)

Returns a 2-D grid where each cell is a **comfort class index** (0 = best, higher = worse), under one of several criteria (Lawson LDDC, Lawson 1970/2001, Davenport, NEN-8100, VDI-3787).

Class A → comfortable for sitting. Class E → uncomfortable. Class S → unsafe. Default: anything class E or worse is flagged as a hotspot.

The exact thresholds depend on the `criteria` parameter you pass — pick one (Lawson LDDC is a sensible default) and the SDK applies the standard mapping.

**Pitfalls:** values are class indices, not speeds — don't average; aggregate by mode or area-share. Class meaning depends on the chosen `criteria`. Frequency-based, not instantaneous: re-running with summer-only weather will shift classes.
