"""The one function a Dynamo node calls: Revit elements in, a status text out.

Order: key dialog (optional) -> project location -> geometry -> ``ir_dynamo``
(preview or run) -> show the result in the active view.
All rules live in ``ir_dynamo`` and in the three ``revit_*`` modules. This file
only joins them.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import traceback
from typing import Any, Dict, List, Optional

from . import revit_apikey, revit_display, revit_geometry, revit_location

# Dynamo keeps the Watch text nowhere. Each run writes its lines here, so the
# user (or a helper) can read the last run. The API key is never in these lines.
LOG_FILE = os.path.join(os.path.expanduser("~"), ".infrared", "revit-dynamo-runs.log")
LAST_RESULT_FILE = os.path.join(
    os.path.expanduser("~"), ".infrared", "revit-dynamo-last-result.json"
)
SHOW_LAST = "show-last"


def _log(lines: List[str]) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write("=== %s\n%s\n" % (stamp, "\n".join(lines)))
    except OSError:
        pass  # a log that cannot be written must not stop the run


def run(*args: Any, **kwargs: Any) -> List[str]:
    """See ``_run``. Writes the returned lines (or the traceback) to ``LOG_FILE``."""
    try:
        lines = _run(*args, **kwargs)
    except Exception:
        _log(["Unexpected error:", traceback.format_exc()])
        raise
    _log(lines)
    return lines


def _optional_float(value: Any, name: str) -> Optional[float]:
    """Dynamo gives an empty string for "not set". Return None for that."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        raise ValueError("%s must be a number, for example 48.208." % name)


def _run(
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
    if str(analysis).strip().lower() == SHOW_LAST:
        return _show_last()
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
        shown = {
            "result": out["result"],
            "title": out["title"],
            "unit": out["unit"],
            "true_north_rad": site.true_north_rad,
        }
        _save_last(shown)  # a paid result is kept: "show-last" draws it again for free
        lines.append(_show(shown))
    return lines


def _save_last(shown: Dict[str, Any]) -> None:
    try:
        with open(LAST_RESULT_FILE, "w", encoding="utf-8") as handle:
            json.dump(shown, handle)
    except (OSError, TypeError, ValueError):
        pass


def _show(shown: Dict[str, Any]) -> str:
    return revit_display.show(
        shown["result"], shown["title"], shown["unit"], shown["true_north_rad"]
    )


def _show_last() -> List[str]:
    """Draw the last paid result again, without a new run (analysis = "show-last")."""
    if not os.path.isfile(LAST_RESULT_FILE):
        return ["There is no saved result yet. Run an analysis first."]
    with open(LAST_RESULT_FILE, "r", encoding="utf-8") as handle:
        shown = json.load(handle)
    return ["Showing the last saved result (no new run).", _show(shown)]
