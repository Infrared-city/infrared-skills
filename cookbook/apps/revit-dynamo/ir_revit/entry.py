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
import time
import traceback
from typing import Any, Dict, List, Optional

from ir_dynamo import settings, targets

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


_START = [0.0]


def _progress(text: str) -> None:
    """One live line in ``LOG_FILE`` with the seconds since the run started.

    The Watch node shows text only at the end; this shows where a slow run is.
    """
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(
                "  ... %s +%.1f s: %s\n"
                % (datetime.datetime.now().strftime("%H:%M:%S"), time.time() - _START[0], text)
            )
    except OSError:
        pass


def run(*args: Any, **kwargs: Any) -> List[str]:
    """See ``_run``. Writes the returned lines (or the traceback) to ``LOG_FILE``."""
    _START[0] = time.time()
    _progress("run started")
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
    target: str,
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
    target : str
        ``"ground"``, ``"facades"`` or ``"both"`` (also ``"all"``). "both" is two
        runs and two costs. An analysis that exists on one target only runs there.
    elements : Any
        The output of "Select Model Elements".
    analysis, months, hours : str
        See ``ir_dynamo.settings`` (labels) and ``ir_dynamo.run.run_analysis``.
        ``analysis = "show-last"`` draws the saved results again, free.
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
        Facade part only: ``"facades"``, ``"roofs"`` or ``"all"``.

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
        to_run, skipped = targets.plan_runs(target, analysis)
        env.setup()
        doc = DocumentManager.Instance.CurrentDBDocument
        site = revit_location.read_location(
            doc, _optional_float(lat, "lat"), _optional_float(lon, "lon")
        )
        _progress("reading geometry from Revit")
        buildings, terrain, notes = revit_geometry.collect_scene(
            doc, elements, site.true_north_rad
        )
        _progress(
            "geometry read: %d building(s) with %d triangles, %d terrain element(s)"
            % (len(buildings), sum(len(v) for v in buildings.values()) // 9, len(terrain))
        )
        if not buildings:
            return [
                "No building geometry found. Select walls, floors, roofs or masses "
                "(and the terrain, if you like)."
            ] + notes
        lines = [
            "Terrain: %d element(s)." % len(terrain),
            "Location: lon %.5f, lat %.5f (%s), true north %.1f deg."
            % (site.lon, site.lat, site.source, math.degrees(site.true_north_rad)),
        ] + skipped
    except (ValueError, RuntimeError) as error:
        return ["Error: %s" % error]
    outs: Dict[str, Dict[str, Any]] = {}
    for surface in to_run:
        _progress("%s: preparing and sending" % surface)
        try:
            outs[surface] = run_analysis(
                surface,
                analysis,
                buildings,
                site.lon,
                site.lat,
                preview_only=bool(preview_only),
                months=months,
                hours=hours,
                fetch_context=bool(fetch_context),
                terrain_m=terrain,
                wind_speed=float(wind_speed),
                wind_direction=int(round(float(wind_direction))),
                surfaces=surfaces,
                on_status=lambda text, s=surface: _progress("%s: %s" % (s, text)),
            )
            _progress("%s: done" % surface)
        except (ValueError, RuntimeError) as error:
            # A failed second target must not hide a first one that was paid for.
            lines.append("Error on %s: %s" % (surface, error))
    lines += notes
    if len(outs) > 1:
        verb = "Preview" if preview_only else "Cost"
        lines.append("%s of both targets: %s." % (verb, targets.combined_cost(outs)))
    entries = []
    for surface, out in outs.items():
        lines += ["[%s] %s" % (surface, out["status"])] + [
            "[%s] %s" % (surface, w) for w in out["warnings"]
        ]
        if out["ran"]:
            entries.append(
                {
                    "target": surface,
                    "result": out["result"],
                    "title": out["title"],
                    "unit": out["unit"],
                    "analysis_type": out["analysis_type"],
                    "true_north_rad": site.true_north_rad,
                }
            )
    if entries:
        _save_last(entries)  # paid results are kept: "show-last" draws them again for free
        lines += [_show(entry) for entry in entries]
    return lines


def _save_last(entries: List[Dict[str, Any]]) -> None:
    """Write the entries; entries of a target that did not run now are kept."""
    try:
        old = None
        if os.path.isfile(LAST_RESULT_FILE):
            with open(LAST_RESULT_FILE, "r", encoding="utf-8") as handle:
                old = json.load(handle)
        with open(LAST_RESULT_FILE, "w", encoding="utf-8") as handle:
            json.dump(targets.merge_entries(old, entries), handle)
    except (OSError, TypeError, ValueError):
        pass


def _show(entry: Dict[str, Any]) -> str:
    _progress("%s: drawing %d values in Revit" % (entry["target"], len(entry["result"]["values"])))
    return revit_display.show(
        entry["result"],
        entry["title"],
        entry["unit"],
        entry["true_north_rad"],
        entry["target"],
        # Files saved before the colour registry have no analysis_type: use the title.
        entry.get("analysis_type") or settings.sdk_type_of_title(entry.get("title", "")),
    )


def _show_last() -> List[str]:
    """Draw the saved results again, without a new run (analysis = "show-last")."""
    if not os.path.isfile(LAST_RESULT_FILE):
        return ["There is no saved result yet. Run an analysis first."]
    with open(LAST_RESULT_FILE, "r", encoding="utf-8") as handle:
        entries = targets.load_entries(json.load(handle))
    if not entries:
        return ["The saved result file has no result. Run an analysis first."]
    return ["Showing the last saved result(s) (no new run)."] + [_show(e) for e in entries]
