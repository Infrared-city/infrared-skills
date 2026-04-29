# Direct Sun Hours (direct-sun-hours)

Cumulative number of hours each ground cell receives direct sunlight over the requested time window, accounting for building shadowing. Geometry + sun-position only — no weather file needed.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import SolarModelRequest, AnalysesName
from infrared_sdk.models import TimePeriod

payload = SolarModelRequest(
    analysis_type=AnalysesName.direct_sun_hours,
    latitude=48.1983,
    longitude=11.575,
    time_period=TimePeriod(
        start_month=6, start_day=1, start_hour=9,
        end_month=6, end_day=30, end_hour=17,
    ),
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array of cumulative direct-sun hours **summed across the filtered hour set defined by `TimePeriod`** — not per-day, not a fraction. The sum runs over the **cross-product** of months × days-of-month × hours-of-day (cascade filter — see [03-time-period.md](../03-time-period.md)), not a continuous wall-clock range. So `(month=6, day=1..30, hour=11..14)` sums ~120 hours per cell, not ~700. A 3-month, 9 a.m.–5 p.m. window can reach hundreds; an all-day yearly window can reach thousands.

`min_legend` / `max_legend` are the SDK's recommended plot bounds for THIS run, derived from the observed grid distribution — NOT from the window length. A heavily shadowed scene may have a `max_legend` well below the astronomical maximum for the period; a sunny rooftop run will be near it.

## Make it interpretable

The raw cumulative value is hard to read across runs with different windows. Useful derivations:

- **Hours per day** — `cell_hours / number_of_days_in_window`. Universal mental model (5 hrs/day = significant sun, 2 hrs/day = heavily shaded).
- **Fraction of run maximum** — `cell_hours / grid.max()`. Within-run relative ranking, dimensionless 0–1.
- **Fraction of daylight in window** — `cell_hours / theoretical_daylight_hours_at_lat_lon`. Answers "what share of available sun does this spot get?"; needs an external sun-position lookup but is the most physically meaningful normalisation across sites and seasons.

For cross-run comparison always normalise first — never compare absolute hour grids from different `time_period`s.

## Pitfalls

- Request class is `SolarModelRequest`, NOT `SolarRadiationModelRequest`. Identical signature to Daylight Availability — only the `analysis_type` enum changes.
- `latitude` / `longitude` are REQUIRED — they drive sun position.
- For radiation in W/m^2 (intensity, not duration) use Solar Radiation instead.
- Always plot with `min_legend` / `max_legend`, not raw `grid.min()` / `grid.max()`.
- **Low sun angles (early-morning / late-afternoon hours, winter months) on multi-tile polygons can show seam artefacts** — buildings outside a tile's 77 m context margin don't occlude across the tile boundary, so long shadows clip at tile edges. Avoid framing analyses around hours when the sun is near the horizon, or stick to single-tile polygons.

## See also

- For result interpretation -> `interpretation/solar-results.md`
- For daylight availability -> `03-daylight-availability.md`
- For radiation in W/m^2 -> `06-solar-radiation.md`
- For time periods -> `03-time-period.md`
