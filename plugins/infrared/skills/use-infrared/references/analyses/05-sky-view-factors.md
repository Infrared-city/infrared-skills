# Sky view factor (`sky-view-factors`)

How much open sky each cell sees, in % (100 = open, 0 = closed). It is pure geometry:
no time period, no weather, no sun.

```python
from infrared_sdk import SvfModelRequest
from infrared_sdk.analyses.types import AnalysesName

# Pass every input you have. Your own data wins; public data is the fallback.
buildings = client.buildings.get_area(polygon)
trees = client.vegetation.get_area(polygon).features

request = SvfModelRequest(analysis_type=AnalysesName.sky_view_factors,
                          ground_geometry=terrain)   # your terrain {id: mesh}; None = flat plane
# Ground materials are not read here.
result = client.run_area_and_wait(request, polygon, buildings=buildings, vegetation=trees,
                                  installations=installations)   # {id: mesh} or None
svf = result.physical_grid()            # 0 to 100, NaN = no value
```

## Parameters

- No other field is needed. Requests refuse unknown fields (`time_period`, weather).
- `latitude` and `longitude` are optional.
- Trees count as obstacles when you give `vegetation`. SVF always uses the leaf-on value.
- Facades, roofs, own sensor points and `context_geometry` work
  ([../python/surfaces-and-sensors.md](../python/surfaces-and-sensors.md)).

## Pitfalls

- If every cell reads 100, you forgot to pass `buildings`. Trees, terrain and installations also change the value: pass them.
- It does not change with season or weather. One run covers all.
- It is not shade. A high SVF point can be in shade for hours.

Read the result: [../interpretation/solar-results.md](../interpretation/solar-results.md)
