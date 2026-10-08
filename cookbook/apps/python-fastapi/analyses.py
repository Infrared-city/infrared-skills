"""Analysis name -> SDK request, and one function that runs and merges it.

Add an analysis here and every endpoint can use it. These three need no
weather. For weather analyses (UTCI, solar radiation, wind comfort) see
https://infrared.city/docs/sdk/1.0/sdk.md (section "Weather and time period").
"""

from __future__ import annotations

import time
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


def run_area(client: Any, request: Any, polygon: dict, **kw: Any) -> Any:
    """Run one area analysis and return the merged AreaResult.

    `kw`: buildings, on_progress, max_tiles_override (passed to the SDK).
    Most analyses: one call to run_area_and_wait (tile, upload, submit, poll,
    merge, one retry of failed tiles).
    Wind speed: always merge with the directional blend. The default merge
    crops each tile at its centre and leaves visible seams in a wind field.
    """
    if not isinstance(request, WindModelRequest):
        return client.run_area_and_wait(request, polygon, **kw)
    on_progress = kw.pop("on_progress", None)
    schedule = client.run_area(request, polygon, **kw)
    known: dict[str, Any] = {}  # job id -> status; finished jobs are not asked again
    for attempt in range(2):  # the first try and one retry of the failed tiles
        while not (state := client.check_area_state(schedule, known=known)).is_complete:
            if on_progress:
                on_progress(state)
            time.sleep(1)
        if on_progress:
            on_progress(state)
        if not state.failed or attempt == 1:
            break
        # Resubmit only the failed tiles; succeeded jobs carry forward (not billed again).
        schedule = client.run_area(request, polygon, retry_from=schedule, known=known, **kw)
    # Raises AreaRunError if a tile is still missing: never a map with holes.
    return client.merge_area_jobs(
        schedule, strategy="directional_blend", wind_direction_deg=request.wind_direction
    )
