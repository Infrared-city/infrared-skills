"""One small table: analysis name -> SDK request.

Add an analysis here and every endpoint can use it. These three need no
weather. For weather analyses (UTCI, solar radiation, wind comfort) see
https://infrared.city/docs/sdk/1.0/sdk.md (section "Weather and time period").
"""

from __future__ import annotations

from typing import Any, Callable

from infrared_sdk import AnalysesName, SolarModelRequest, SvfModelRequest, WindModelRequest
from infrared_sdk.models import TimePeriod


def _svf(lat: float, lon: float, p: dict[str, Any]) -> SvfModelRequest:
    return SvfModelRequest(analysis_type=AnalysesName.sky_view_factors, latitude=lat, longitude=lon)


def _wind(lat: float, lon: float, p: dict[str, Any]) -> WindModelRequest:
    return WindModelRequest(
        analysis_type=AnalysesName.wind_speed,
        wind_speed=float(p.get("wind_speed", 5)),  # m/s at the reference height
        wind_direction=int(p.get("wind_direction", 270)),  # degrees, wind from the west
    )


def _sun_hours(lat: float, lon: float, p: dict[str, Any]) -> SolarModelRequest:
    # One TimePeriod can wrap the year (for example Dec to Feb).
    month = int(p.get("month", 6))
    return SolarModelRequest(
        analysis_type=AnalysesName.direct_sun_hours,
        latitude=lat,
        longitude=lon,
        time_period=TimePeriod(
            start_month=month,
            start_day=1,
            start_hour=8,
            end_month=month,
            end_day=28,
            end_hour=18,
        ),
    )


ANALYSES: dict[str, Callable[[float, float, dict[str, Any]], Any]] = {
    "sky-view-factors": _svf,
    "wind-speed": _wind,
    "direct-sun-hours": _sun_hours,
}


def build_request(name: str, polygon: dict, params: dict[str, Any]) -> Any:
    """Make the SDK request for one analysis at the centre of the polygon."""
    ring = polygon["coordinates"][0]
    lon = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
    lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
    return ANALYSES[name](lat, lon, params)
