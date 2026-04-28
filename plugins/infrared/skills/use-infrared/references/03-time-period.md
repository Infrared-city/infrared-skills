# TimePeriod

Solar, thermal, and wind-comfort analyses need a `TimePeriod` to define the simulation window and (for weather-driven analyses) which hourly weather rows to keep.

## Format

```python
from infrared_sdk.models import TimePeriod

tp = TimePeriod(
    start_month=6, start_day=1, start_hour=9,
    end_month=8, end_day=31, end_hour=17,
)
```

All 6 fields are required ints:

| Field         | Range |
| ------------- | ----- |
| `start_month` | 1-12  |
| `start_day`   | 1-31  |
| `start_hour`  | 0-23  |
| `end_month`   | 1-12  |
| `end_day`     | 1-31  |
| `end_hour`    | 0-23  |

## Cascade behaviour

`TimePeriod` is a recurring window applied to every year in the weather file as a 3-level cascade filter:

1. **Months** — only data from `start_month` through `end_month`.
2. **Days** — within those months, only days from `start_day` through `end_day`.
3. **Hours** — within those days, only hours from `start_hour` through `end_hour`.

Example: `TimePeriod(6, 1, 9, 8, 20, 17)` keeps ~3 months x 20 days x 9 hours = **540 hourly points per year**.

## Which analyses need TimePeriod

| Analysis                   | TimePeriod | Weather Data |
| -------------------------- | ---------- | ------------ |
| Wind Speed                 | No         | No           |
| Sky View Factors           | No         | No           |
| Daylight Availability      | Yes        | No           |
| Direct Sun Hours           | Yes        | No           |
| Solar Radiation            | Yes        | Yes          |
| Thermal Comfort (UTCI)     | Yes        | Yes          |
| Thermal Comfort Statistics | Yes        | Yes          |
| Pedestrian Wind Comfort    | Yes        | Yes          |

## Pitfalls

- Pass the **same** `TimePeriod` to `filter_weather_data()` and the analysis payload — mismatched windows desync weather arrays from the simulation.
- `end_*` fields are inclusive on each cascade level.
- `TimePeriod` is frozen (Pydantic `frozen=True`); construct a new one to change values.
- Day 31 in a 30-day month silently has no effect for that month — the filter just yields fewer rows.

## See also

- `04-weather-data.md` — feeding weather into payloads
- `analyses/utci.md` — UTCI uses TimePeriod + weather
- `analyses/solar-radiation.md` — Solar Radiation uses TimePeriod + weather
