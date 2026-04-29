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

`TimePeriod` is a recurring window — the API filters every year in the weather file as a 3-level cascade (filtering happens server-side; the client just POSTs the period):

1. **Months** — only data from `start_month` through `end_month`.
2. **Days** — within those months, only days from `start_day` through `end_day`.
3. **Hours** — within those days, only hours from `start_hour` through `end_hour`.

Example: `TimePeriod(start_month=6, start_day=1, start_hour=9, end_month=8, end_day=20, end_hour=17)` keeps ~3 months × 20 days × 9 hours = **540 hourly points per year**. (`TimePeriod` is a Pydantic v2 model — pass kwargs only, positional args raise `TypeError`.)

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
| Pedestrian Wind Comfort    | Yes (for weather filtering) | Yes (wind speed/direction arrays) |

## Pitfalls

- Pass the **same** `TimePeriod` to `filter_weather_data()` and the analysis payload — mismatched windows desync weather arrays from the simulation.
- `end_*` fields are inclusive on each cascade level.
- `TimePeriod` is frozen (Pydantic `frozen=True`); construct a new one to change values.
- Impossible calendar dates (April 31, June 31, September 31, November 31, February 30), zero-length windows, and `end < start` raise `ValidationError` at construction. February 29 is accepted (no year context). Year-wrap windows (e.g. Nov→Feb) are not supported — split into two periods.

## See also

- `04-weather-data.md` — feeding weather into payloads
- `analyses/07-thermal-comfort-utci.md` — UTCI uses TimePeriod + weather
- `analyses/06-solar-radiation.md` — Solar Radiation uses TimePeriod + weather
