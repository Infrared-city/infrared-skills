"""Analysis request for one label. Only SDK classes are used here."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from infrared_sdk import (
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
    UtciModelBaseRequest,
)
from infrared_sdk.models import Location, TimePeriod

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


def _weather_rows(client: Any, lat: float, lon: float, period: TimePeriod) -> Any:
    stations = client.weather.get_weather_file_from_location(
        lat=lat, lon=lon, radius=WEATHER_RADIUS_KM
    )
    if not stations:
        raise RuntimeError(
            "No weather station within %d km of %.4f, %.4f."
            % (WEATHER_RADIUS_KM, lon, lat)
        )
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
        SDK frame. Svf, sun hours, daylight, solar and utci take it. Wind does
        not (the SDK refuses it): for wind it only switches the buildings to
        ``terrain_alignment="to-ground"``.
    client : InfraredClient, optional
        Needed for the analyses that read weather.
    """
    request = _request(
        analysis, surface, lat, lon, months, hours, surfaces, grid_m,
        wind_speed, wind_direction, client,
    )  # fmt: skip
    if not ground_geometry:
        return request
    if analysis.key == "wind":
        # No terrain for wind. Its worker reads a building's height from the raw
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
    rows = _weather_rows(client, lat, lon, period)
    location = Location(latitude=lat, longitude=lon)
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
