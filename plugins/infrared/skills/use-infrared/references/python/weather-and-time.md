# Python: weather and time period

Thermal comfort, solar radiation and pedestrian wind comfort read weather.
Direct sun hours and daylight availability need a time period and a location, but no weather array.
Sky view factor and wind speed need neither.

Docs: guide chapter "Your inputs" (<https://infrared.city/docs/sdk/1.0/sdk.md>),
[Layers (weather)](https://infrared.city/docs/sdk/1.0/python/layers/index.md),
[Models](https://infrared.city/docs/sdk/1.0/python/models/index.md).

## Time period

A `TimePeriod` is a date span with a daily hour range. It keeps only the hours in that window.
Use keyword arguments. The object is frozen.

```python
from infrared_sdk import InfraredClient, parse_epw
from infrared_sdk.models import Location, TimePeriod

summer_day = TimePeriod(start_month=7, start_day=15, start_hour=12,
                        end_month=7, end_day=15, end_hour=16)

# 1 Jun to 31 Aug, 08:00 to 18:00 every day: 1,012 hours.
summer = TimePeriod(start_month=6, start_day=1, start_hour=8,
                    end_month=8, end_day=31, end_hour=18)

# A winter window is ONE window: Dec, Jan and Feb. Do not split it.
# The values come in file order (January first).
winter = TimePeriod(start_month=12, start_day=1, start_hour=8,
                    end_month=2, end_day=28, end_hour=18)

# A full year, for pedestrian wind comfort.
year = TimePeriod(start_month=1, start_day=1, start_hour=0,
                  end_month=12, end_day=31, end_hour=23)
```

- The window is a cascade: months, then days, then hours. `end_*` is inclusive.
- Use the same `TimePeriod` for the weather filter and the request.
- `direct-sun-hours` on the ground counts night hours as sun. Keep the hours inside sunrise to sunset
  ([../analyses/04-direct-sun-hours.md](../analyses/04-direct-sun-hours.md)).

## Weather source

Two sources. Both give hourly rows.

1. The public catalog: 16,757 stations, one typical year each (TMYx). It has no forecast,
   no future climate and no single year that you choose.
2. Your own `.epw` file: `parse_epw("site.epw")`. It needs hourly data, 8760 rows.
   The SDK reads it on your machine. Nothing uploads as a file.

```python
client = InfraredClient()
lat, lon = 48.208, 16.371

# Nearest stations, nearest first.
stations = client.weather.get_weather_file_from_location(lat=lat, lon=lon)
print(stations[0]["fileName"])

# The hourly rows inside the window.
rows = client.weather.filter_weather_data(
    identifier=stations[0]["uuid"], time_period=summer_day)
print(len(rows), "hours")      # 5 hours: 12, 13, 14, 15, 16
```

For your own file, pass `weather_data=parse_epw("vienna.epw")` to the classmethods below.
They cut the time window themselves. A gap raises before you pay.

## Weather into a request

The classmethods take the rows and keep only the columns that the model needs.

```python
import numpy as np
from infrared_sdk.analyses.types import (
    AnalysesName, BaseAnalysisPayload, SolarRadiationModelRequest,
    TcsModelBaseRequest, TcsModelRequest, TcsSubtype,
    UtciModelBaseRequest, UtciModelRequest,
)

place = Location(latitude=lat, longitude=lon)

# UTCI: 7 weather columns, picked for you.
utci = UtciModelRequest.from_weatherfile_payload(
    payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
    location=place, time_period=summer_day, weather_data=rows)

# Thermal comfort statistics: the same columns, plus a subtype per call.
tcs = TcsModelRequest.from_weatherfile_payload(
    payload=TcsModelBaseRequest(
        analysis_type=AnalysesName.thermal_comfort_statistics,
        subtype=TcsSubtype.heat_stress),             # or thermal_comfort, cold_stress
    location=place, time_period=summer_day, weather_data=rows)

# Solar radiation: direct and diffuse radiation only.
winter_rows = client.weather.filter_weather_data(
    identifier=stations[0]["uuid"], time_period=winter)
solar = SolarRadiationModelRequest.from_weatherfile_payload(
    payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
    location=place, time_period=winter, weather_data=winter_rows)
print(len(winter_rows), "winter hours")      # 990
```

The UTCI default has a wall afterglow of about 3 hours and a ground lag of about 43 minutes,
and no memory over days. The air comes from the weather file.
Comfort materials are optional fields on the UTCI and TCS request:
`wall_albedo`, `wall_absorptivity`, `canopy_transmissivity`, `ground_albedo`, `ground_dt_max`.

## Wind

```python
from infrared_sdk.analyses.types import PwcCriteria, PwcModelRequest, WindModelRequest
from infrared_sdk.models import extract_weather_fields

# One speed and one direction. Use a float speed. Direction is a whole-degree int.
wind = WindModelRequest(analysis_type=AnalysesName.wind_speed,
                        wind_speed=4.5, wind_direction=270)      # wind FROM the west

# Pedestrian wind comfort: hourly speeds and directions of a full year.
year_rows = client.weather.filter_weather_data(
    identifier=stations[0]["uuid"], time_period=year)
pwc = PwcModelRequest(
    analysis_type=AnalysesName.pedestrian_wind_comfort,
    criteria=PwcCriteria.lawson_lddc,
    **extract_weather_fields(year_rows, ["windSpeed", "windDirection"]))
```

## Run them

```python
polygon = {"type": "Polygon", "coordinates": [[
    [lon, lat], [lon + 0.004, lat], [lon + 0.004, lat + 0.003],
    [lon, lat + 0.003], [lon, lat]]]}
xy = [(100, 100), (120, 100), (120, 120), (100, 120)]
coordinates = [c for z in (0, 30) for x, y in xy for c in (x, y, z)]
indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
           1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]
buildings = {"tower": {"coordinates": coordinates, "indices": indices}}

# Preview each request with its own payload. Cost grows with the number of requests.
for name, req in {"utci": utci, "tcs": tcs, "solar": solar, "wind": wind, "pwc": pwc}.items():
    p = client.preview_area(polygon, payload=req)
    print(name, p.would_bill_jobs, "job(s)", p.estimated_cost_tokens, "tokens")

# One call, several analyses on the same geometry. Results keep the list order.
res_utci, res_solar = client.run_area_and_wait([utci, solar], polygon, buildings=buildings)
print("UTCI (C):", float(np.nanmin(res_utci.physical_grid())), float(np.nanmax(res_utci.physical_grid())))
print("Winter solar (kWh/m2):", float(np.nanmax(res_solar.physical_grid())))
```

Wind tiles step 256 m, solar and thermal tiles step 512 m: the preview shows 4 wind jobs where a
solar run has 1. Always give `payload=` to `preview_area`, or it prices the wind grid.
