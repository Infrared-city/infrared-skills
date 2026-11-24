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

from . import env, grid_check, meshes, own_layers, payloads, results, settings, variants
from . import terrain as terrain_mod
from . import frame as frame_mod

DEFAULT_BUFFER_M = {"ground": 30.0, "facades": 5.0}
# Terrain triangles this far outside the run area are kept (shade, slope at the edge).
TERRAIN_MARGIN_M = 20.0
# The public ground materials take about a minute to read (an Overture read, 61-89 s
# for a 80 m area in Vienna on 2026-11-20); the SDK default of 60 s stopped it.
GROUND_READ_TIMEOUT_S = 240
# A ground run warns (also in the free preview) when this share of the area is
# under buildings: ground sheets sent as buildings gave a wind run without values.
COVERED_WARN = 0.8


def _context_soups(
    frame: frame_mod.SiteFrame, buildings: Dict[str, Any], z_offset: float
) -> Dict[str, List[float]]:
    """The public buildings (``ctx-*``) as flat triangles in Revit-frame metres."""
    out: Dict[str, List[float]] = {}
    for name, mesh in buildings.items():
        if not str(name).startswith("ctx-"):
            continue
        xyz = np.asarray(mesh["coordinates"], dtype=np.float64).reshape(-1, 3)
        index = np.asarray(mesh["indices"], dtype=np.int64).reshape(-1, 3)
        moved = frame_mod.points_to_revit(frame, xyz[index].reshape(-1)).reshape(-1, 3)
        moved[:, 2] += z_offset
        out[str(name)] = moved.reshape(-1).tolist()
    return out


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
    lowest = min(float(terrain_mod.triangles(f)[:, :, 2].min()) for f in buildings_m.values())
    if ground and is_wind:
        warnings.append(
            "The wind models do not take terrain: it is not sent. Each building is lowered "
            "to its own base; the result is drawn on the terrain."
        )
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
    trees_m: Optional[Sequence[own_layers.Tree]] = None,
    ground_m: Optional[Dict[str, Sequence[own_layers.Ring]]] = None,
    on_status: Optional[Callable[[str], None]] = None,
    client: Optional[Any] = None,
    return_context: bool = False,
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
        Add the public buildings, trees and ground materials around the selection
        (needs the geodata libs). The result covers the buildings too, inside the run area.
    terrain_m : dict, optional
        ``{terrain_id: flat [x, y, z, ...]}``, same units and frame as
        ``buildings_m``. With terrain, z = 0 of the SDK is the lowest terrain
        point of the run area and the ground result follows the terrain. Without
        it the ground is Revit z = 0. Wind and PWC do not take terrain (a warning says so).
    trees_m : list, optional
        Own trees: ``[(x, y, height_m, crown_diameter_m), ...]`` in the Revit frame;
        a size of None or 0 is the default (6 m, 4 m). See ``own_layers``.
    ground_m : dict, optional
        Own ground materials: ``{material: [[(x, y), ...], ...]}`` in the Revit frame,
        material one of ``own_layers.MATERIALS``. Only utci and tcs read them.
    on_status : callable, optional
        Called with a short text at each stage. It is called on the calling thread.
    client : InfraredClient, optional
        Leave it out to build one from the API key.
    return_context : bool
        Put the trees and ground materials sent in ``out["trees_m"]`` and
        ``out["ground_m"]`` (``own_layers.display_*``, at height ``out["layers_z"]``), and,
        with ``fetch_context``, the public buildings in ``out["context_m"]``
        (``{id: flat triangles}``, Revit-frame metres), for a host that draws
        them. Revit does not; Rhino does.

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
            frame, buildings_m, terrain_m, bbox, buffer, row.no_terrain
        )
        warnings.insert(
            0,
            "Area: %.0f x %.0f m (the selection and a margin of %.0f m%s)."
            % (frame.size_m[0], frame.size_m[1], buffer,
               "; set it with the word margin" if buffer_m is None else ""),
        )
        warnings += own_layers.notes(row.sdk_type, trees_m or [], ground_m or {})
        vegetation = own_layers.trees_geojson(frame, trees_m) if trees_m else None
        materials = own_layers.ground_geojson(frame, ground_m) if ground_m else None
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
            say("reading public trees")
            public_trees = client.vegetation.get_area(frame.polygon, analysis_type=row.sdk_type)
            vegetation = {**dict(public_trees.features), **(vegetation or {})} or None
            warnings.append("%d public tree(s) added as context." % len(public_trees.features))
            failed = len(public_trees.failed_tiles)
            if row.sdk_type in own_layers.THERMAL:
                say("reading public ground materials (about a minute)")
                public_ground = client.ground_materials.get_area(
                    frame.polygon, analysis_type=row.sdk_type, timeout=GROUND_READ_TIMEOUT_S
                )
                materials = own_layers.merge_layers(dict(public_ground.layers), materials)
                failed += len(public_ground.failed_tiles)
                warnings.append(
                    "%d public ground-material area(s) added as context (%s)."
                    % (public_ground.total_features, ", ".join(sorted(public_ground.layers)) or "none")
                )
            else:
                warnings.append("Public ground materials are not read: only utci and tcs use them.")
            if failed:
                warnings.append(
                    "Warning: some public trees or ground materials could not be read (%d failed tile(s))."
                    % failed
                )
        if surface == "ground":
            covered = grid_check.covered_share(buildings, frame.size_m)
            if covered >= COVERED_WARN:
                warnings.append(
                    "Warning: %.0f %% of the area is under buildings, and the ground under a "
                    "building gets no value. Is the ground modelled as a floor, a mass or an "
                    "import (ground sheets, roads)? Leave those elements out of the selection, "
                    "or model the ground as a Toposolid." % (100.0 * covered)
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
            vegetation=vegetation,
            ground_materials=materials,
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
            # The public buildings of ``context``, for a host that draws them (Rhino).
            "context_m": (
                _context_soups(frame, buildings, z_offset) if fetch_context and return_context else {}
            ),
            # The trees and ground materials sent (own and public), for a host that draws them.
            "trees_m": own_layers.display_trees(frame, vegetation) if return_context else [],
            "ground_m": own_layers.display_ground(frame, materials) if return_context else {},
            "layers_z": z_offset,
        }
        if preview_only:
            out["status"] = "Preview only: %s. Add the word run to the command to run it." % cost
            return out

        def progress(state: Any) -> None:
            say("server %d/%d jobs" % (state.succeeded, state.total))

        say("running: %s" % cost)
        run = client.run_area_and_wait(
            payload,
            frame.polygon,
            buildings=buildings,
            vegetation=vegetation,
            ground_materials=materials,
            on_progress=progress,
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
                frame, run, z_offset, box_m=frame.size_m
            )
            gone = out["result"].pop("left_out")
            if gone["outside"]:
                warnings.append(
                    "Facade cells not drawn: %d triangle(s) on public buildings outside the area."
                    % gone["outside"]
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
