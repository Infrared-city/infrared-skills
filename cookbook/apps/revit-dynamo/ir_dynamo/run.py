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

from . import env, grid_check, meshes, payloads, results, settings, variants
from . import terrain as terrain_mod
from . import frame as frame_mod

DEFAULT_BUFFER_M = {"ground": 30.0, "facades": 5.0}
# Terrain triangles this far outside the run area are kept (shade, slope at the edge).
TERRAIN_MARGIN_M = 20.0
# Model elements this far from the run area can still shade it. The SDK reads
# public buildings up to 384 m from the middle of a 512 m tile.
SHADE_REACH_M = 400.0


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
    shade_m: Optional[Dict[str, Sequence[float]]] = None,
) -> Tuple[Dict[str, dict], Dict[str, dict], Optional[terrain_mod.Sampler], float, List[str]]:
    """Buildings and terrain in the SDK frame, around one ground reference.

    ``shade_m``: elements that only shade. Those near the run area are added to
    the buildings; a line gives their number.

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
    close = meshes.near(shade_m or {}, bbox, buffer + SHADE_REACH_M)
    if close:
        try:
            shade, _, _ = meshes.build_buildings(frame, close, z_offset, sampler)
        except ValueError:  # none of them has a usable triangle above the ground
            shade = {}
        buildings.update((k, v) for k, v in shade.items() if k not in buildings)
    if shade_m:
        warnings.append(
            "Shade only: %d other element(s) of the model within %.0f m (%d in all). "
            "No result is drawn on them." % (len(close), SHADE_REACH_M, len(shade_m))
        )
    if ground and is_wind:
        warnings.append(
            "The wind models do not take terrain: it is not sent. Each building is lowered "
            "to its own base; the result is drawn on the terrain."
        )
    lowest = min(float(terrain_mod.triangles(f)[:, :, 2].min()) for f in buildings_m.values())
    if sampler is None and lowest > 5.0:
        warnings.append(
            "Warning: no terrain. The ground is Revit elevation 0 and the buildings start %.0f m "
            "above it. Model the site as a Toposolid to place them on it." % lowest
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
    shade_m: Optional[Dict[str, Sequence[float]]] = None,
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
        ``sun-hours``, ``daylight``, ``wind``, ``utci``, ``pwc``,
        ``tcs`` (ground only). Aliases like ``"sun hours"`` work. PWC and TCS
        take a criterion or subtype as the last word: ``"pwc lawson-2001"``.
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
        Margin around the buildings. Default 30 m (ground), 5 m (facades); with
        ``fetch_context`` the largest margin that costs no extra tile
        (``frame.fill_buffer``), so the area is about 500 m wide.
    surfaces : str
        Facades only: ``"facades"``, ``"roofs"`` or ``"all"``.
    grid_m : float
        Facades only: cell size in metres.
    wind_speed, wind_direction : float, int
        Wind only: m/s and bearing in whole degrees (270 = from the west).
    fetch_context : bool
        Add the public buildings around the selection (needs the geodata libs).
        The result covers them too, inside the run area.
    shade_m : dict, optional
        Other elements of the model, same shape as ``buildings_m``. They shade
        the result; no result is drawn on them, and they do not size the area.
    terrain_m : dict, optional
        ``{terrain_id: flat [x, y, z, ...]}``, same units and frame as
        ``buildings_m``. With terrain, z = 0 of the SDK is the lowest terrain
        point of the run area and the ground result follows the terrain. Without
        it the ground is Revit z = 0. Wind and PWC do not take terrain (a warning says so).
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
        bbox = meshes.soup_bbox(buildings_m)
        buffer = DEFAULT_BUFFER_M[surface] if buffer_m is None else float(buffer_m)
        if fetch_context and buffer_m is None:
            buffer = frame_mod.fill_buffer(site_lon, site_lat, bbox, buffer, row.sdk_type)
        frame = frame_mod.make_frame(site_lon, site_lat, bbox, buffer)
        buildings, ground, sampler, z_offset, warnings = _scene(
            frame, buildings_m, terrain_m, bbox, buffer, row.no_terrain, shade_m
        )
        shade_ids = set(buildings) - {str(k) for k in buildings_m}
        warnings.insert(
            0,
            "Area: %.0f x %.0f m (the selection and a margin of %.0f m%s)."
            % (frame.size_m[0], frame.size_m[1], buffer,
               "; set it with the word margin" if buffer_m is None else ""),
        )
        if row.needs_period:
            warnings += settings.window_note(row, months, hours)
        if fetch_context:
            say("reading public buildings")
            fetched = client.buildings.get_area(
                frame.polygon, analysis_type=row.sdk_type
            )
            buildings, added = meshes.merge_context(buildings, dict(fetched.buildings))
            warnings.append(
                "%d public building(s) added as context. The result covers them too, "
                "inside the area." % added
            )
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
            notes=warnings,
        )
        preview = client.preview_area(
            frame.polygon,
            analysis_type=row.sdk_type,
            payload=payload,
            buildings=buildings,
        )
        cost = _cost_text(preview)
        out: Dict[str, Any] = {
            "title": row.full_title,
            "unit": row.unit,
            # The colour registry key: the SDK name, and the PWC criterion or TCS subtype.
            "analysis_type": variants.colour_key(row.sdk_type, row.variant),
            "cost": cost,
            "tokens": int(preview.estimated_cost_tokens),
            "warnings": warnings,
            "ran": False,
            "result": None,
        }
        if preview_only:
            out["status"] = "Preview only: %s. Add the word run to the command to run it." % cost
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
            try:  # where does the matrix sit? (a check only; it never stops the run)
                warnings += grid_check.alignment_lines(frame, run, buildings)
            except Exception as error:
                warnings.append("Grid alignment check failed: %s" % error)
        else:
            out["result"] = results.facade_triangles(
                frame, run, z_offset, skip=shade_ids, box_m=frame.size_m
            )
            gone = out["result"].pop("left_out")
            if gone["shade"] or gone["outside"]:
                warnings.append(
                    "Facade cells not drawn: %d triangle(s) on shade-only elements, %d on "
                    "public buildings outside the area." % (gone["shade"], gone["outside"])
                )
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
