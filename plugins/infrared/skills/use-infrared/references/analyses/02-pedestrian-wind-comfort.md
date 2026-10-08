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
- `nen_8100_safety` answers a safety question (storms), not a comfort question.
- Summer-only and yearly weather give different classes. Keep the weather fixed when you compare designs.
- Use a discrete colour map and a class legend ([../recipes/rendering-results-well.md](../recipes/rendering-results-well.md)).

Read the result: [../interpretation/wind-results.md](../interpretation/wind-results.md)
