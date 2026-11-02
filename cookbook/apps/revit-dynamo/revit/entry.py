"""The one function a Dynamo node calls: Revit elements in, a status text out.

Order: key dialog (optional) -> project location -> geometry -> ``ir_dynamo``
(preview or run) -> show the result in the active view.
All rules live in ``ir_dynamo`` and in the three ``revit_*`` modules. This file
only joins them.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

from . import revit_apikey, revit_display, revit_geometry, revit_location


def _optional_float(value: Any, name: str) -> Optional[float]:
    """Dynamo gives an empty string for "not set". Return None for that."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        raise ValueError("%s must be a number, for example 48.208." % name)


def run(
    surface: str,
    elements: Any,
    analysis: str,
    months: str,
    hours: str,
    preview_only: bool,
    fetch_context: bool,
    lat: Any,
    lon: Any,
    set_api_key: bool,
    wind_speed: float = 5.0,
    wind_direction: float = 270,
    surfaces: str = "all",
) -> List[str]:
    """Preview or run one analysis on the selected elements.

    Parameters
    ----------
    surface : str
        ``"ground"`` or ``"facades"``.
    elements : Any
        The output of "Select Model Elements".
    analysis, months, hours : str
        See ``ir_dynamo.settings`` (labels) and ``ir_dynamo.run.run_analysis``.
    preview_only : bool
        True: free preview, no tokens.
    fetch_context : bool
        Add public buildings around the selection.
    lat, lon : Any
        Degrees as text or number. Empty: use the location of the Revit project.
    set_api_key : bool
        True: only open the key dialog and stop.
    wind_speed, wind_direction : float
        Ground wind only.
    surfaces : str
        Facades only: ``"facades"``, ``"roofs"`` or ``"all"``.

    Returns
    -------
    list of str
        Lines for a Watch node. Errors you can fix are lines, not exceptions.
    """
    from ir_dynamo import env
    from ir_dynamo.run import run_analysis
    from RevitServices.Persistence import DocumentManager  # type: ignore

    if set_api_key:
        if revit_apikey.ask_and_save():
            return ["API key saved. Set set_api_key to False and run again."]
        return ["No key saved."]
    try:
        env.setup()
        doc = DocumentManager.Instance.CurrentDBDocument
        site = revit_location.read_location(
            doc, _optional_float(lat, "lat"), _optional_float(lon, "lon")
        )
        buildings, notes = revit_geometry.collect_buildings(
            elements, site.true_north_rad
        )
        if not buildings:
            return ["No geometry found. Select walls, floors, roofs or masses."] + notes
        lines = [
            "Location: lon %.5f, lat %.5f (%s), true north %.1f deg."
            % (site.lon, site.lat, site.source, math.degrees(site.true_north_rad))
        ]
        out = run_analysis(
            surface,
            analysis,
            buildings,
            site.lon,
            site.lat,
            preview_only=bool(preview_only),
            months=months,
            hours=hours,
            fetch_context=bool(fetch_context),
            wind_speed=float(wind_speed),
            wind_direction=int(round(float(wind_direction))),
            surfaces=surfaces,
        )
    except (ValueError, RuntimeError) as error:
        return ["Error: %s" % error]
    lines += [out["status"]] + notes + list(out["warnings"])
    if out["ran"]:
        lines.append(
            revit_display.show(
                out["result"], out["title"], out["unit"], site.true_north_rad
            )
        )
    return lines
