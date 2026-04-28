# Wind results — interpretation guide

> **Draft 2026-04-28** — generated from AIBackend mining. Items flagged `[REVIEW]` need product confirmation.

This guide explains how to read the output of two wind analyses: `wind-speed` and `pedestrian-wind-comfort` (PWC).

## Wind Speed

### Output schema

`client.run_area_and_wait(WindModelRequest(...))` returns an `AreaResult` dataclass.

| Field | Type | Unit / meaning |
|---|---|---|
| `merged_grid` | `numpy.ndarray` (2-D, `float64`) | Wind speed in **m/s**, one value per cell. Cells outside polygon = `NaN`. |
| `polygon` | `dict` (GeoJSON) | The polygon you submitted, echoed back. |
| `analysis_type` | `str` | `"wind-speed"`. |
| `grid_shape` | `tuple[int, int]` | `(num_rows, num_cols)`. Cell pitch ~**1 m × 1 m**. Row 0 = southernmost; column 0 = westernmost. |
| `min_legend` / `max_legend` | `Optional[float]` | Recommended colour-scale bounds in m/s. Use these for plotting — distributions are heavy-tailed. |
| `failed_jobs`, `skipped_jobs`, `total_jobs`, `succeeded_jobs` | `list[str]` / `int` | Tile-level run health. Inspect on large NaN patches inside the polygon. |

`AreaResult.to_dict()` produces a JSON-safe dict where NaNs become `None`. There is no parquet or GeoTIFF in the SDK return — convert the grid yourself if you need to export.

### Value ranges and physical units

- **Unit:** metres per second (m/s).
- **Typical range:** 0–30 m/s; most urban analyses 0–12 m/s.
- **Inflow request:** `wind_speed` integer 1–100 m/s; `wind_direction` 0–360° meteorological convention (0° = wind **from** the north, 90° = from the east).
- **Rule-of-thumb interpretation:**
  - **< 1.5 m/s** — calm, may feel stagnant in heat.
  - **1.5–3.5 m/s** — comfortable for most outdoor activities.
  - **3.5–6.0 m/s** — breezy; papers and hair disturbed.
  - **6.0–8.0 m/s** — fresh / strong; uncomfortable for sitting.
  - **> 10 m/s** — strong-to-dangerous; design red flag, check PWC for safety classes.

### Height-above-ground convention

Cells represent steady-state magnitude **near pedestrian level (~1.5 m AGL)**, for one (speed, direction) inflow condition. The grid is 2-D — no per-cell height field. Multiple heights or directions = multiple analyses.

### Common interpretation traps

- **Single-direction snapshot, not a climatology.** One run = one inflow direction + one inflow speed. To represent annual exposure, run multiple directions and aggregate (the "natural ventilation potential" pattern aggregates over 8 directions).
- **Direction is meteorological, not vector.** `wind_direction=270` means wind **from** the west, not "wind blowing toward 270°".
- **NaN ≠ zero wind.** NaN means cell is outside polygon or its tile failed; missing data, not still air. Mask before computing means/percentiles.
- **Grid orientation.** Row 0 = southernmost, column 0 = westernmost — opposite of most image libraries.
- **Inflow speed ≠ surface speed.** Returned values are speed at the cell, modulated by buildings — typically lower than your inflow in sheltered courtyards, higher in venturi'd corner zones.

## Pedestrian Wind Comfort

### Output schema

`PwcModelRequest` returns the same `AreaResult` container, but `merged_grid` holds a **comfort class per cell**, not wind speed.

| Field | Type | Meaning |
|---|---|---|
| `merged_grid` | `numpy.ndarray` (2-D) | Comfort class encoded as integer-valued floats `0–4` (occasionally up to 5–6 for criteria with multiple unsafe sub-classes). NaN outside polygon. |
| Other fields | as for Wind Speed | identical semantics. |

The class index maps to letter classes A → S in the chosen criterion (A = 0 = best comfort; highest index = least comfortable / unsafe). Mapping order follows alphabetical sort of unique class strings emitted by the model (so A=0, B=1, C=2, D=3, E=4, S=5 for Lawson-style criteria).

### Comfort criteria — exact thresholds

PWC integrates a wind-speed time series (from a weather file) and a directional rose with the building geometry, then assigns each cell the most-restrictive comfort class it satisfies under the chosen criterion.

**Lawson LDDC** (default in workflows; `criteria=lawson_lddc`)
- A — Frequent sitting: wind < 2.5 m/s for >95% of time
- B — Occasional sitting: wind < 4.0 m/s for >95% of time
- C — Standing: wind < 6.0 m/s for >95% of time
- D — Walking: wind < 8.0 m/s for >95% of time
- E — Uncomfortable: wind > 8.0 m/s for >5% of time
- S — Unsafe: wind > 15.0 m/s more than 0.022% of time (~2 h/year)

**Lawson 1970** — A:<1.8 / B:<3.6 / C:<5.3 / D:<7.6 m/s for >98%; E ≥ 7.6 m/s for >2%.

**Lawson 2001** — A:<4.0 / B:<6.0 / C:<8.0 / D:<10.0 m/s for >95%; E > 10 m/s for >5%; S15 > 15 m/s for >0.023%; S20 > 20 m/s for >0.023%.

**Davenport** — A:<3.6 / B:<5.3 / C:<7.6 / D:<9.8 m/s for >98.5%; E ≥ 9.8 m/s for >1.5%; S ≥ 15.1 m/s for >0.01%.

**NEN-8100 Comfort** — single threshold of 5 m/s, varying frequency: A >97.5% / B >95% / C >90% / D >80%; E ≥ 5 m/s for >20%.

**NEN-8100 Safety** — A: <15 m/s for >99.95%; B: <15 m/s for >99.7%; C (dangerous): ≥ 15 m/s for >0.3%.

**VDI-3787** — A:<6 / B:<9 / C:<12 / D:<15 m/s for >99.99%; E ≥ 15 m/s for >0.01%.

The default composite threshold treats **class E or worse as unsafe / hotspot**.

### Common interpretation traps

- **Cells are classes, not speeds.** Cell value `3.0` ≠ 3 m/s; it means "class index 3" (typically D). Do not average PWC grids — aggregate via mode or area share per class.
- **Class semantics depend on criterion.** Class C under Lawson LDDC ("standing") is not the same as class C under Davenport ("walking leisurely"). Always carry the `criteria` value alongside the grid.
- **It is an exceedance-frequency assessment, not instantaneous.** Each class is defined by *how often* a threshold is exceeded across the input weather series. Re-running with summer-only or winter-only weather will shift classes.
- **An "A" cell can still feel windy occasionally.** Class A means the high-comfort threshold is met >95% (or 98%) of the time — gusty events still happen.
- **No vertical dimension.** PWC is a 2-D grid at pedestrian level (~1.5 m AGL). No separate output for balcony or seated heights.
- `[REVIEW]` Class-index encoding is derived at merge time from alphabetical order of unique strings. For criteria with non-alphabetic class names (e.g. `S15`, `S20`), numeric ordering may not match severity order. For safety-critical use, decode against the `criteria` parameter rather than trusting "higher number = worse".

## Source files mined (private repo references — internal only)

- `infrared-api-sdk/src/infrared_sdk/analyses/types.py` — `WindModelRequest`, `PwcModelRequest`, `PwcCriteria`
- `infrared-api-sdk/src/infrared_sdk/tiling/types.py` — `AreaResult`
- `infrared-api-sdk/src/infrared_sdk/_area/_merging.py` — categorical-grid encoding
- `AIBackend/services/vlm_service.py` — full criteria threshold tables
- `AIBackend/workflows/composite/defaults.yaml` — PWC defaults, hotspot rule
- `AIBackend/workflows/metrics_reference.md` — wind speed comfort bands
- `AIBackend/prompts/vlm/pedestrian-wind-comfort/system.md` — criteria narratives
