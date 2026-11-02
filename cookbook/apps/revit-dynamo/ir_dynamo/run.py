"""One call for a Dynamo script: preview the cost, or run, and get plain data back.

Typical use in a Dynamo Python node (see the README of this folder)::

    from ir_dynamo.run import run_analysis
    out = run_analysis("ground", "svf", soups, site_lon, site_lat, preview_only=True)
    out["status"], out["cost"]
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import env, meshes, payloads, results, settings
from . import terrain as terrain_mod
from . import frame as frame_mod

DEFAULT_BUFFER_M = {"ground": 30.0, "facades": 5.0}
# Terrain triangles this far outside the run area are kept (shade, slope at the edge).
TERRAIN_MARGIN_M = 20.0


def _cost_text(preview: Any) -> str:
    text = "%d tile(s), %d job(s), about %d tokens" % (
        preview.tile_count,
        preview.would_bill_jobs,
        preview.estimated_cost_tokens,
    )
    if preview.sensor_count:
        text += ", %d sensors" % preview.sensor_count
    return text


def _scene(
    frame: frame_mod.SiteFrame,
    buildings_m: Dict[str, Sequence[float]],
    terrain_m: Optional[Dict[str, Sequence[float]]],
    bbox: Sequence[float],
    buffer: float,
    is_wind: bool,
) -> Tuple[Dict[str, dict], Dict[str, dict], Optional[terrain_mod.Sampler], float, List[str]]:
    """Buildings and terrain in the SDK frame, around one ground reference.

    The ground reference (z = 0 of the SDK) is the lowest terrain point of the
    run area. Without terrain it is Revit z = 0: no offset.
    Returns ``(buildings, ground_geometry, sampler, z_offset, warnings)``.
    """
    warnings: List[str] = []
    ground: Dict[str, dict] = {}
    sampler = None
    z_offset = 0.0
    if terrain_m:
        tris, notes = terrain_mod.prepare(terrain_m, bbox, buffer + TERRAIN_MARGIN_M)
        warnings += notes
        if tris:
            every = np.concatenate(list(tris.values()))
            sampler = terrain_mod.Sampler(every)
            z_offset = float(every[:, :, 2].min())
            ground = meshes.build_terrain(frame, tris, z_offset)
    buildings, z_offset, notes = meshes.build_buildings(frame, buildings_m, z_offset, sampler)
    warnings += notes
    if ground and is_wind:
        warnings.append(
            "Wind does not take terrain: it is not sent. Each building is lowered "
            "to its own base; the result is drawn on the terrain."
        )
    lowest = min(float(terrain_mod.triangles(f)[:, :, 2].min()) for f in buildings_m.values())
    if sampler is None and lowest > 5.0:
        warnings.append(
            "No terrain: the ground is Revit elevation 0 and the buildings start %.0f m "
            "above it. Select the terrain to place them on it." % lowest
        )
    return buildings, ground, sampler, z_offset, warnings


def run_analysis(
    surface: str,
    analysis: str,
    buildings_m: Dict[str, Sequence[float]],
    site_lon: float,
    site_lat: float,
    *,
    preview_only: bool = True,
    months: str = "6-8",
    hours: str = "8-18",
    buffer_m: Optional[float] = None,
    surfaces: str = "all",
    grid_m: float = payloads.DEFAULT_GRID_M,
    wind_speed: float = 5.0,
    wind_direction: int = 270,
    fetch_context: bool = False,
    terrain_m: Optional[Dict[str, Sequence[float]]] = None,
    on_status: Optional[Callable[[str], None]] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Preview the cost of one analysis, or run it and return the result.

    Parameters
    ----------
    surface : str
        ``"ground"`` (grid around the buildings) or ``"facades"`` (walls and roofs).
    analysis : str
        A label from ``settings.ANALYSES`` for that surface: ``svf``, ``solar``,
        ``sun-hours``, ``daylight`` (facades only), ``wind``, ``utci``
        (ground only). Aliases like ``"sun hours"`` work.
    buildings_m : dict
        ``{building_id: flat [x, y, z, ...]}``. Every 9 numbers are one
        triangle, in metres, in the Revit frame (origin = site location, x
        east, y true north, z up).
    site_lon, site_lat : float
        The origin of the Revit frame, in degrees. Also the weather location.
    preview_only : bool
        True (default): only the free preview, no tokens spent.
    months, hours : str
        Window for the analyses that need one, for example ``"6-8"``, ``"8-18"``.
    buffer_m : float, optional
        Margin around the buildings. Default 30 m (ground), 5 m (facades).
    surfaces : str
        Facades only: ``"facades"``, ``"roofs"`` or ``"all"``.
    grid_m : float
        Facades only: cell size in metres.
    wind_speed, wind_direction : float, int
        Wind only: m/s and bearing in whole degrees (270 = from the west).
    fetch_context : bool
        Add the public buildings around the selection (needs the geodata libs).
    terrain_m : dict, optional
        ``{terrain_id: flat [x, y, z, ...]}``, same units and frame as
        ``buildings_m``. With terrain, z = 0 of the SDK is the lowest terrain
        point of the run area and the ground result follows the terrain. Without
        it the ground is Revit z = 0. Wind does not take terrain (a warning says so).
    on_status : callable, optional
        Called with a short text at each stage. It is called on the calling thread.
    client : InfraredClient, optional
        Leave it out to build one from the API key.

    Returns
    -------
    dict
        ``status`` (text), ``cost`` (text), ``tokens`` (int, the estimate), ``ran`` (bool), ``title``, ``unit``,
        ``analysis_type`` (the SDK name, for the colours),
        ``warnings`` (list of text), and ``result``: ``None`` after a preview, else
        the dict of ``results.ground_points`` or ``results.facade_triangles``
        (``kind``, geometry, ``values``, ``legend_min``, ``legend_max``).

    Raises
    ------
    ValueError
        For input the user can fix (unknown label, a bad month text, no buildings).
    RuntimeError
        For a missing API key or SDK.
    """
    say = on_status or (lambda text: None)
    row = settings.find_analysis(analysis, surface)
    started = time.time()
    own_client = client is None
    if own_client:
        env.setup()
        from infrared_sdk import InfraredClient

        client = InfraredClient(api_key=env.read_api_key())
    try:
        buffer = DEFAULT_BUFFER_M[surface] if buffer_m is None else float(buffer_m)
        bbox = meshes.soup_bbox(buildings_m)
        frame = frame_mod.make_frame(site_lon, site_lat, bbox, buffer)
        buildings, ground, sampler, z_offset, warnings = _scene(
            frame, buildings_m, terrain_m, bbox, buffer, row.key == "wind"
        )
        if fetch_context:
            say("reading public buildings")
            fetched = client.buildings.get_area(
                frame.polygon, analysis_type=row.sdk_type
            )
            buildings, added = meshes.merge_context(buildings, dict(fetched.buildings))
            warnings.append("%d public building(s) added as context." % added)
            if ground:
                warnings.append(
                    "Public context buildings stand at z = 0 of the SDK (the lowest "
                    "terrain point), not on the terrain."
                )
        say("building the request")
        payload = payloads.build_payload(
            row,
            surface,
            site_lat,
            site_lon,
            months=months,
            hours=hours,
            surfaces=surfaces,
            grid_m=grid_m,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            ground_geometry=ground or None,
            client=client,
        )
        preview = client.preview_area(
            frame.polygon,
            analysis_type=row.sdk_type,
            payload=payload,
            buildings=buildings,
        )
        cost = _cost_text(preview)
        out: Dict[str, Any] = {
            "title": row.title,
            "unit": row.unit,
            "analysis_type": row.sdk_type,
            "cost": cost,
            "tokens": int(preview.estimated_cost_tokens),
            "warnings": warnings,
            "ran": False,
            "result": None,
        }
        if preview_only:
            out["status"] = "Preview only: %s. Set preview_only to False to run." % cost
            return out

        def progress(state: Any) -> None:
            say("server %d/%d jobs" % (state.succeeded, state.total))

        say("running: %s" % cost)
        run = client.run_area_and_wait(
            payload, frame.polygon, buildings=buildings, on_progress=progress
        )
        say("reading the result")
        if surface == "ground":
            out["result"] = results.ground_points(frame, run, z_offset, sampler)
        else:
            out["result"] = results.facade_triangles(frame, run, z_offset)
        out["ran"] = True
        out["status"] = "Done in %.0f s: %s (%s)." % (
            time.time() - started,
            row.title,
            cost,
        )
        return out
    finally:
        if own_client:
            client.close()
