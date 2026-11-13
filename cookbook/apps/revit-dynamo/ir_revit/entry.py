"""The one function the Dynamo node calls: a command line in, a status text out.

Order: the command (``ir_dynamo.command``) -> the Revit selection -> project
location -> geometry -> ``ir_dynamo`` (preview or run) -> the result in the model.
All rules live in ``ir_dynamo`` and in the ``revit_*`` modules. This file only
joins them.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import time
import traceback
from typing import Any, Dict, List, Optional

from ir_dynamo import command as command_line
from ir_dynamo import command_help, payloads, settings, summary, targets

from . import (
    revit_apikey,
    revit_display,
    revit_export,
    revit_geometry,
    revit_location,
    revit_results,
    revit_scene,
    revit_selection,
)

# Dynamo keeps the Watch text nowhere. Each run writes its lines here, so the
# user (or a helper) can read the last run. The API key is never in these lines.
LOG_FILE = os.path.join(os.path.expanduser("~"), ".infrared", "revit-dynamo-runs.log")
LAST_RESULT_FILE = os.path.join(
    os.path.expanduser("~"), ".infrared", "revit-dynamo-last-result.json"
)


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


def run(command: Any = "", elements: Any = None, **old: Any) -> List[str]:
    """Run one command line. Writes the returned lines (or the traceback) to ``LOG_FILE``.

    Parameters
    ----------
    command : str
        The text of the ``command`` node, for example ``"svf both context run"``.
        See ``ir_dynamo.command``. Empty: the help text.
    elements : Any, optional
        Elements to analyse (Dynamo wrappers or Revit API elements), for a graph
        that has its own selection node. Leave it out: the script reads the
        selection of Revit.
    **old
        The inputs of the graph before 2026-11-12 (``target``, ``analysis``, ...).
        They are not used; a line says so.

    Returns
    -------
    list of str
        Lines for the Watch node, the warnings first. Errors you can fix are
        lines, not exceptions.
    """
    _START[0] = time.time()
    live = _live_command()
    if live is not None and live.strip() != str(command or "").strip():
        # Dynamo runs a marked node with the earlier text first (see dynamo_rerun).
        _progress("skipped: Dynamo gave the earlier text %r, the command node has %r" % (command, live))
        _mark_for_rerun()
        return [
            "Dynamo ran the script with the earlier command text; nothing was done.",
            "The new command runs next. If it does not, press Run again.",
        ]
    _progress("run started")
    try:
        lines = _run(command, elements)
        if old:
            lines.append(
                "This graph is an older version: its input nodes (%s) are not used any "
                "more. Open the new IR_Analysis.dyn; it has the command node only."
                % ", ".join(sorted(old))
            )
    except Exception:
        _log(["Unexpected error:", traceback.format_exc()])
        raise
    finally:
        if live is not None:  # without the text of the node, a marked node could run an old command
            _progress(_mark_for_rerun())
    _log(lines)
    return lines


def _live_command() -> Optional[str]:
    """The text in the command node now; None outside Dynamo. See ``dynamo_rerun``."""
    try:
        from . import dynamo_rerun

        return dynamo_rerun.live_command()
    except Exception:
        return None


def _mark_for_rerun() -> str:
    """Dynamo runs a node again only when an input changed; see ``dynamo_rerun``."""
    try:
        from . import dynamo_rerun

        return dynamo_rerun.mark()
    except Exception as error:  # not in Dynamo (the tests), or another Dynamo
        return "rerun: not set (%s)" % type(error).__name__


NO_GEOMETRY = (
    "No building geometry found. Select walls, floors, roofs or masses in Revit and "
    "press Run again (or run the command select and click them), or add the word model "
    "to analyse every building of the model."
)


def _run(command: Any, elements: Any = None) -> List[str]:
    text = str(command or "").strip()
    if not text:
        return ["The command is empty. Type one in the command node, for example: svf"] + (
            command_help.help_lines()
        )
    try:
        cmd = command_line.parse(text)
    except ValueError as error:
        return ["Command error: %s" % error, "Command: %s" % text]
    if cmd.action == "help":
        return command_help.help_lines()
    _progress("command: %s" % cmd.text)
    if cmd.action == "set-key":
        saved = revit_apikey.ask_and_save()
        return ["API key saved. Type a command and run again." if saved else "No key saved."]
    try:
        if cmd.action == "select":
            lines = revit_selection.pick(_document(), in_link=cmd.scope == "link", progress=_progress)
        elif cmd.action == "show-last":
            lines = _show_last(cmd)
        elif cmd.action == "export-obj":
            lines = _export(cmd, elements)
        elif cmd.action == "clear":
            lines = _clear()
        else:
            lines = _analysis(cmd, elements)
    except (ValueError, RuntimeError, OSError) as error:
        lines = ["Error: %s" % error]
    lines = "\n".join(lines).split("\n")  # a drawn result is one text of many lines
    if any("Preview only:" in line for line in lines):
        lines.append("To run it (paid): %s" % cmd.paid_text())
    return ["Command: %s" % cmd.text] + summary.warnings_first(lines)


def _document() -> Any:
    from RevitServices.Persistence import DocumentManager  # type: ignore

    return DocumentManager.Instance.CurrentDBDocument


def _clear() -> List[str]:
    """Delete every result, legend view and result filter of the model (``clear``)."""
    from RevitServices.Transactions import TransactionManager  # type: ignore

    doc = _document()
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        return revit_results.clear(doc)
    finally:
        TransactionManager.Instance.TransactionTaskDone()


def _picks(doc: Any, elements: Any, need: bool) -> Any:
    """The elements to analyse: the ``elements`` input when it has any, else the Revit selection."""
    given = [revit_geometry.unwrap(e) for e in revit_geometry.flatten(elements)]
    if given:
        return given, [], []
    return revit_selection.read(doc, need)


def _site(doc: Any, cmd: Any) -> Any:
    lat = float(cmd.lat) if cmd.lat else None
    lon = float(cmd.lon) if cmd.lon else None
    return revit_location.read_location(doc, lat, lon)


def _export(cmd: Any, elements: Any) -> List[str]:
    doc = _document()
    host, linked, notes = _picks(doc, elements, need=cmd.scope != "model")
    if cmd.scope == "model":
        host = list(revit_scene.building_elements(doc))
        linked = []
        notes = [
            "Model: the %d building element(s) of the open model and those of its loaded "
            "links are exported." % len(host)
        ]
    label = "export-obj all" if cmd.export_all else "export-obj"
    lat = float(cmd.lat) if cmd.lat else None
    lon = float(cmd.lon) if cmd.lon else None
    lines = revit_export.export_obj(
        doc, host, None, lat, lon, _progress, label, linked=linked, every_link=cmd.scope == "model"
    )
    return lines + notes


def _analysis(cmd: Any, elements: Any) -> List[str]:
    """Preview or run one analysis on the selection (or the model), and draw the result."""
    from ir_dynamo import env
    from ir_dynamo.run import run_analysis

    to_run, skipped = targets.plan_runs(cmd.target, cmd.analysis)
    env.setup()
    doc = _document()
    site = _site(doc, cmd)
    host, linked, picked_notes = _picks(doc, elements, need=cmd.scope != "model")
    _progress("reading geometry from Revit")
    buildings, shade, terrain_m, notes = revit_scene.collect(
        doc, host, linked, site.true_north_rad, cmd.scope, _progress
    )
    _progress(
        "geometry read: %d result element(s) with %d triangles, %d shade element(s), %d terrain element(s)"
        % (len(buildings), sum(len(v) for v in buildings.values()) // 9, len(shade), len(terrain_m))
    )
    if not buildings:
        only_result = any("Infrared result shape(s) in the selection" in n for n in notes)
        hint = (
            ["Warning: the selection holds only an Infrared result shape, not a building. "
             "Select the building under it: hide the shape, or press Tab at the building."]
            if only_result
            else []
        )
        return hint + [NO_GEOMETRY] + picked_notes + notes
    location = "Location: lon %.5f, lat %.5f (%s), true north %.1f deg." % (
        site.lon, site.lat, site.source, math.degrees(site.true_north_rad),
    )  # fmt: skip
    lines = payloads.default_location_note(site.lat, site.lon, site.source)
    lines += [location, "Terrain: %d element(s) with geometry." % len(terrain_m)] + skipped
    outs: Dict[str, Dict[str, Any]] = {}
    for surface in to_run:
        _progress("%s: preparing and sending" % surface)
        try:
            outs[surface] = run_analysis(
                surface,
                cmd.analysis,
                buildings,
                site.lon,
                site.lat,
                preview_only=not cmd.paid,
                months=cmd.months,
                hours=cmd.hours,
                buffer_m=float(cmd.margin) if cmd.margin else None,
                fetch_context=cmd.fetch_context,
                terrain_m=terrain_m,
                shade_m=shade,
                wind_speed=float(cmd.wind_speed),
                wind_direction=int(round(float(cmd.wind_direction))),
                surfaces=cmd.surfaces,
                on_status=lambda text, s=surface: _progress("%s: %s" % (s, text)),
            )
            _progress("%s: done" % surface)
        except (ValueError, RuntimeError) as error:
            # A failed second target must not hide a first one that was paid for.
            lines.append("Error on %s: %s" % (surface, error))
    lines += picked_notes + notes
    if len(outs) > 1:
        lines.append("%s of both targets: %s." % ("Cost" if cmd.paid else "Preview", targets.combined_cost(outs)))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H.%M")
    entries = []
    for surface, out in outs.items():
        lines += ["[%s] %s" % (surface, out["status"])] + [
            "[%s] %s" % (surface, w) for w in out["warnings"]
        ]
        if out["ran"]:
            weather = [w for w in out["warnings"] if w.startswith("Weather:")]
            entries.append(
                {
                    "target": surface,
                    "result": out["result"],
                    "title": out["title"],
                    "unit": out["unit"],
                    "analysis_type": out["analysis_type"],
                    "true_north_rad": site.true_north_rad,
                    "document": doc.PathName or doc.Title,
                    # For the legend view and the Comments of the shape.
                    "info": ["Command: %s" % cmd.text, location] + weather + ["Run: %s" % stamp],
                    "label": "%s (%s)" % (cmd.text, stamp),
                }
            )
    if entries:
        _save_last(entries)  # paid results are kept: "show-last" draws them again for free
        lines += [_show(entry, cmd.legend, cmd.gradient) for entry in entries]
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


def _show(entry: Dict[str, Any], range_mode: str, gradient: bool) -> str:
    _progress("%s: drawing %d values in Revit" % (entry["target"], len(entry["result"]["values"])))
    return revit_display.show(
        entry["result"],
        entry["title"],
        entry["unit"],
        entry["true_north_rad"],
        entry["target"],
        # Files saved before the colour registry have no analysis_type: use the title.
        entry.get("analysis_type") or settings.sdk_type_of_title(entry.get("title", "")),
        range_mode,
        gradient,
        info=entry.get("info") or [],
        label=entry.get("label") or "",
    )


def _show_last(cmd: Any) -> List[str]:
    """Draw the saved results again, without a new run (``show-last``)."""
    if not os.path.isfile(LAST_RESULT_FILE):
        return ["There is no saved result yet. Run an analysis first."]
    with open(LAST_RESULT_FILE, "r", encoding="utf-8") as handle:
        entries = targets.load_entries(json.load(handle))
    if not entries:
        return ["The saved result file has no result. Run an analysis first."]
    return ["Showing the last saved result(s) (no new run)."] + [
        _show(e, cmd.legend, cmd.gradient) for e in entries
    ]
