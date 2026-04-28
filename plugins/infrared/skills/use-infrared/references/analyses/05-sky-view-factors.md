# Sky View Factors (sky-view-factors)

Fraction of the upper hemisphere visible from each ground cell, blocked only by buildings (and vegetation if injected). Pure geometry — no time period, no weather, no sun position.

## Request

```python
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import SvfModelRequest, AnalysesName

payload = SvfModelRequest(
    analysis_type=AnalysesName.sky_view_factors,
    latitude=48.1983,    # optional - only needed if you inject vegetation
    longitude=11.575,    # optional - only needed if you inject vegetation
)
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
```

## Response

`result.merged_grid` is a 2D `float` array of SVF in [0, 1] — 1.0 = fully open sky, 0.0 = fully obstructed. `min_legend` / `max_legend` are the canonical color-scale bounds.

## Pitfalls

- Geometry-only: do NOT pass `time_period` or weather arrays — they will be silently ignored or rejected.
- `latitude` / `longitude` are OPTIONAL. SVF inference itself ignores them; they exist so the vegetation validator can build a reference point. Set them only if you inject vegetation.
- SVF is a static building-shadowing metric — it does not change with season or weather. One run covers all conditions.
- A common downstream input to other thermal/comfort post-processing — but the SDK analysis itself returns only SVF.

## See also

- For result interpretation -> `interpretation/svf-results.md`
- For polygon/buildings setup -> `02-geometry.md`
- For vegetation injection -> `06-vegetation.md`
