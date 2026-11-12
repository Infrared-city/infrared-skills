"""Analysis request for one label. Only SDK classes are used here."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional

from infrared_sdk import (
    PwcModelRequest,
    SolarModelRequest,
    SolarRadiationModelRequest,
    SvfModelRequest,
    UtciModelRequest,
    WindModelRequest,
)
from infrared_sdk.analyses.types import (
    AnalysesName,
    TerrainAlignment,
    BaseAnalysisPayload,
    PwcCriteria,
    TcsModelBaseRequest,
    TcsModelRequest,
    TcsSubtype,
    UtciModelBaseRequest,
)
from infrared_sdk.models import Location, TimePeriod, extract_weather_fields

from .settings import Analysis, parse_period

# Surface cell size for walls and roofs, in metres. The SDK default is the
# same; it is written here so the status text can name it.
DEFAULT_GRID_M = 2.0
WEATHER_RADIUS_KM = 50


def _surface_fields(surfaces: str, grid_m: float) -> Dict[str, Any]:
    # emit_cell_tris gives one drawable triangle list for each cell.
    return {
        "analysis_surfaces": surfaces,
        "surface_grid_size": grid_m,
        "emit_cell_tris": True,
    }


FAR_STATION_KM = 20.0  # farther than this: the line asks to check the location


def station_line(station: Dict[str, Any], lat: float, lon: float) -> str:
    """The Watch line of the weather station a run uses.

    ``station``: a row of ``client.weather.get_weather_file_from_location``
    (``fileName``, ``location_data`` with ``city``, ``country``, ``station_id``,
    ``source``, ``latitude``, ``longitude``). A row without ``location_data``
    gives its file name only.
    """
    where = station.get("location_data") or {}
    name = ", ".join(str(where[k]) for k in ("city", "country") if where.get(k))
    name = name or str(station.get("fileName") or station.get("uuid") or "unknown")
    about = [str(where["station_id"])] if where.get("station_id") else []
    about += [str(where["source"]).replace("SRC-", "")] if where.get("source") else []
    text = "Weather: station %s%s" % (name, " (%s)" % ", ".join(about) if about else "")
    try:
        km = _distance_km(lat, lon, float(where["latitude"]), float(where["longitude"]))
    except (KeyError, TypeError, ValueError):
        return text + "."
    text += ", %.1f km from the site." % km
    if km > FAR_STATION_KM:
        text += " Warning: that is far. Check the project location (Manage > Location)."
    return text


REVIT_DEFAULT_PLACE = (42.3584, -71.0597)  # Boston: where a new Revit project is
REVIT_DEFAULT_REACH_KM = 40.0  # other Revit versions and templates use places near it


def default_location_note(lat: float, lon: float, source: str) -> List[str]:
    """A warning when the location read from Revit is the default of a new project.

    A model of London that keeps the default is analysed with the sun and the
    weather of Boston (live runs 2026-11-09). ``source``: ``"revit"`` or ``"override"``.
    """
    if source != "revit" or _distance_km(lat, lon, *REVIT_DEFAULT_PLACE) > REVIT_DEFAULT_REACH_KM:
        return []
    return [
        "Warning: the project location is lat %.4f, lon %.4f, in the Boston area: the "
        "default of a new Revit project. If the project is not there, set Manage > "
        "Location, or add lat and lon to the command. The sun, the weather and the "
        "public buildings come from this place." % (lat, lon)
    ]


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (haversine, Earth radius 6371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))


def _weather_rows(
    client: Any, lat: float, lon: float, period: TimePeriod, notes: Optional[List[str]] = None
) -> Any:
    stations = client.weather.get_weather_file_from_location(
        lat=lat, lon=lon, radius=WEATHER_RADIUS_KM
    )
    if not stations:
        raise RuntimeError(
            "No weather station within %d km of %.4f, %.4f."
            % (WEATHER_RADIUS_KM, lon, lat)
        )
    if notes is not None:  # the SDK gives the nearest station first
        notes.append(station_line(stations[0], lat, lon))
    return client.weather.filter_weather_data(
        identifier=stations[0]["uuid"], time_period=period
    )


def build_payload(
    analysis: Analysis,
    surface: str,
    lat: float,
    lon: float,
    *,
    months: str = "6-8",
    hours: str = "8-18",
    surfaces: str = "all",
    grid_m: float = DEFAULT_GRID_M,
    wind_speed: float = 5.0,
    wind_direction: int = 270,
    ground_geometry: Optional[Dict[str, dict]] = None,
    client: Optional[Any] = None,
    notes: Optional[List[str]] = None,
) -> Any:
    """Build the SDK request for one analysis.

    Parameters
    ----------
    analysis : Analysis
        A row of ``settings.ANALYSES``.
    surface : str
        ``"ground"`` or ``"facades"``.
    lat, lon : float
        Location of the site, in degrees.
    months, hours : str
        The analysis window, for example ``"6-8"`` and ``"8-18"``.
    surfaces : str
        Facades only: ``"facades"``, ``"roofs"`` or ``"all"``.
    grid_m : float
        Facades only: cell size in metres.
    wind_speed, wind_direction : float, int
        Wind only: speed in m/s and the bearing in whole degrees (270 = wind
        from the west).
    ground_geometry : dict, optional
        The terrain, ``{id: {"coordinates": [...], "indices": [...]}}`` in the
        SDK frame. Svf, sun hours, daylight, solar, utci and tcs take it. The
        wind models (wind, pwc) do not (the SDK refuses it): for them it only
        switches the buildings to ``terrain_alignment="to-ground"``.
    client : InfraredClient, optional
        Needed for the analyses that read weather.
    notes : list of str, optional
        Gets the ``station_line`` of the weather station, for the analyses
        that read weather.
    """
    request = _request(
        analysis, surface, lat, lon, months, hours, surfaces, grid_m,
        wind_speed, wind_direction, client, notes,
    )  # fmt: skip
    if not ground_geometry:
        return request
    if analysis.no_terrain:
        # No terrain for the wind models. Its worker reads a building's height from the raw
        # z, so each building is lowered to its own lowest point (the grade).
        return request.model_copy(update={"terrain_alignment": "to-ground"})
    # "as-is" (the SDK default for a supplied scene, written here on purpose):
    # the buildings keep their Revit heights. "auto-align" would seat every
    # building on the terrain and move it; "assume-aligned" leaves the server
    # to check it. The terrain z and the building z share one datum (z_offset).
    return request.model_copy(
        update={
            "ground_geometry": ground_geometry,
            "terrain_alignment": TerrainAlignment.as_is,
        }
    )


def _request(
    analysis: Analysis,
    surface: str,
    lat: float,
    lon: float,
    months: str,
    hours: str,
    surfaces: str,
    grid_m: float,
    wind_speed: float,
    wind_direction: int,
    client: Optional[Any],
    notes: Optional[List[str]] = None,
) -> Any:
    extra = _surface_fields(surfaces, grid_m) if surface == "facades" else {}
    period = (
        TimePeriod(**parse_period(months, hours)) if analysis.needs_period else None
    )
    kind = AnalysesName(analysis.sdk_type)
    if analysis.key == "svf":
        return SvfModelRequest(analysis_type=kind, latitude=lat, longitude=lon, **extra)
    if analysis.key in ("sun-hours", "daylight"):
        return SolarModelRequest(
            analysis_type=kind, latitude=lat, longitude=lon, time_period=period, **extra
        )
    if analysis.key == "wind":
        return WindModelRequest(
            analysis_type=kind,
            latitude=lat,
            longitude=lon,
            wind_speed=float(wind_speed),
            wind_direction=int(wind_direction),
        )
    if client is None:
        raise ValueError("%s reads weather; pass a client." % analysis.title)
    rows = _weather_rows(client, lat, lon, period, notes)
    location = Location(latitude=lat, longitude=lon)
    if analysis.key == "pwc":
        # Hourly wind observations of the window, paired by position.
        return PwcModelRequest(
            analysis_type=kind,
            criteria=PwcCriteria(analysis.variant),
            latitude=lat,
            longitude=lon,
            **extract_weather_fields(rows, ["windSpeed", "windDirection"]),
        )
    if analysis.key == "tcs":
        return TcsModelRequest.from_weatherfile_payload(
            payload=TcsModelBaseRequest(analysis_type=kind, subtype=TcsSubtype(analysis.variant)),
            location=location,
            time_period=period,
            weather_data=rows,
        )
    if analysis.key == "solar":
        base = BaseAnalysisPayload[Literal[AnalysesName.solar_radiation]](
            analysis_type=kind
        )
        request = SolarRadiationModelRequest.from_weatherfile_payload(
            payload=base, location=location, time_period=period, weather_data=rows
        )
        return request.model_copy(update=extra) if extra else request
    return UtciModelRequest.from_weatherfile_payload(
        payload=UtciModelBaseRequest(analysis_type=kind),
        location=location,
        time_period=period,
        weather_data=rows,
    )
