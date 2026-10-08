# TimePeriod

Solar, thermal and wind-comfort analyses use a `TimePeriod` for the simulation window.
Weather-driven analyses also use it to keep the matching hourly rows.
Code and examples: [python/weather-and-time.md](python/weather-and-time.md).

```python
from infrared_sdk.models import TimePeriod

tp = TimePeriod(start_month=6, start_day=1, start_hour=9,
                end_month=8, end_day=31, end_hour=17)
```

All six fields are required ints, as keyword arguments:

| Field | Range |
|---|---|
| `start_month`, `end_month` | 1 to 12 |
| `start_day`, `end_day` | 1 to 31 |
| `start_hour`, `end_hour` | 0 to 23 |

## Cascade

The window is a recurring filter of every year in the weather file, in three levels:
months (start to end), then days inside those months, then hours inside those days.
`end_*` is inclusive at each level.

1 Jun to 31 Aug, 08:00 to 18:00 keeps 92 days x 11 hours = 1,012 hours.
1 Jun to 20 Aug, 09:00 to 17:00 keeps about 3 months x 20 days x 9 hours = 540 hours, not a continuous
range. So direct sun hours sums over days x hours.

## Winter and year windows

A window across the new year is **one** `TimePeriod`: `start_month=12 ... end_month=2` keeps
December, January and February (990 hours at 08 to 18 h). The values come in file order:
January first. Do not split it. A full-year window is normal for pedestrian wind comfort.

## Which analyses use it

| Analysis | TimePeriod | Weather columns |
|---|---|---|
| wind speed, sky view factor | no | no |
| daylight availability, direct sun hours | yes | no (needs location) |
| solar radiation | yes | direct and diffuse radiation |
| UTCI, TCS | yes | 7 columns |
| pedestrian wind comfort | yes (to cut the weather) | wind speed and direction lists |
| energy balance (interior) | no (one year) | 2 or 4 series |

## Pitfalls

- Use the same `TimePeriod` for the weather filter and for the request.
- Direct sun hours on the ground: keep the hours inside daylight
  ([analyses/04-direct-sun-hours.md](analyses/04-direct-sun-hours.md)).
- `TimePeriod` is frozen. Build a new one to change it.
- Impossible dates (31 April, 30 February), zero-length windows raise at construction (a window across the new year is valid).
  29 February is accepted.
- A gap in your EPW inside the window is an error before you pay. The SDK never fills a gap.
