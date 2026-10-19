# Pedestrian wind comfort (`pedestrian-wind-comfort`)

A comfort class for each cell, from a full time series of wind. The class follows one standard
that you choose. Cells hold class codes, not speeds.

```python
from infrared_sdk import PwcModelRequest
from infrared_sdk.analyses.types import AnalysesName, PwcCriteria
from infrared_sdk.models import TimePeriod, extract_weather_fields

year = TimePeriod(start_month=1, start_day=1, start_hour=0,
                  end_month=12, end_day=31, end_hour=23)
rows = client.weather.filter_weather_data(identifier=station_uuid, time_period=year)

request = PwcModelRequest(
    analysis_type=AnalysesName.pedestrian_wind_comfort,
    criteria=PwcCriteria.lawson_lddc,
    **extract_weather_fields(rows, ["windSpeed", "windDirection"]),   # two hourly lists
)
result = client.run_area_and_wait(request, polygon, buildings=buildings)
classes = result.physical_grid()        # class codes; NaN = no value
labels = result.legend                  # class names, indexed by the code
safety = result.safety                  # yearly wind safety check; None if there is none
```

## Safety layer

Safety is a separate yearly check. It is not a class of the comfort ladder. The comfort grid and
`result.legend` do not change. `result.safety` (`result.safety` in TypeScript) holds, for each cell,
the share of hours per year above a safety speed (the hourly mean) and a class:

| Criteria | Safety speed | Fails when | `classes` |
|---|---|---|---|
| `lawson_lddc` | 15 m/s | more than 0.022 % of hours | pass, fail |
| `lawson_2001` | 15 m/s (S15), 20 m/s (S20) | more than 0.023 % of hours | pass, S15, S20 (worst wins) |
| `davenport` | 15.1 m/s | 0.01 % of hours or more | pass, fail |
| `nen_8100_comfort`, `nen_8100_safety` | 15 m/s | 0.05 % (limited), 0.30 % (dangerous) | none, limited, dangerous |
| `vdi_3787` | 15 m/s | 0.01 % of hours or more | pass, danger-not-excluded |
| `lawson_1970` | none | no layer, `safety` is `None` | |

```python
if safety is not None:
    ratio = safety.ratio                 # exceedance / limit; 1 = at the limit; NaN = no value
    codes = safety.class_codes           # index into safety.classes; 0 = pass; 255 = no value
    failing = (codes > 0) & (codes < 255)
    pct = safety.exceedance              # [speeds, rows, cols], % of hours per year
    names = safety.labels                # object array of class names, None = no value
```

```ts
const safety = result.safety;            // undefined when there is none
if (safety) console.log(safety.classes, safety.thresholdsMs, safety.classCodes, safety.ratio);
```

## Parameters

- `criteria` (`PwcCriteria`): `vdi_3787`, `lawson_1970`, `lawson_2001`, `lawson_lddc`, `davenport`,
  `nen_8100_comfort`, `nen_8100_safety`. Pick the one that your client or city uses.
- `wind_speed` and `wind_direction` are lists with one value per hour, of equal length.
  Do not mix them up with the single numbers of `wind-speed`.
- A full-year window is the normal choice.

## Pitfalls

- Class codes are not numbers to average. Report the area share for each class, or the mode.
- Mask NaN before you count a share: `valid = grid[~np.isnan(grid)]`.
- `nen_8100_safety` answers a safety question (storms) in its own comfort grid. For every criteria, read
  the yearly safety check in `result.safety`. A Lawson comfort grid never shows class S.
- `result.safety` is `None` for a server that does not send it, and for `lawson_1970`. It is not in `to_dict()`.
- Summer-only and yearly weather give different classes. Keep the weather fixed when you compare designs.
- Use a discrete colour map and a class legend ([../recipes/rendering-results-well.md](../recipes/rendering-results-well.md)).

Read the result: [../interpretation/wind-results.md](../interpretation/wind-results.md)
