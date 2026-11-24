"""The one function to call in Rhino: a command line in, the lines of the log out.

    from ir_rhino import entry
    print("\\n".join(entry.run("svf run")))

The Rhino 9 AI panel calls it through ``run_python``; the ScriptEditor the same
way. Each call is one press of Run: ``run`` in the command pays tokens.
Order: the command -> the objects -> the site -> ``ir_dynamo`` (preview or run)
-> a coloured mesh on the layer ``Infrared``.
"""

from __future__ import annotations

import datetime
import os
import time
import traceback
from typing import Any, Iterable, List, Optional

from ir_dynamo import command as command_line
from ir_dynamo import command_help, summary

from . import core, rhino_doc, shapes
from .site import model_to_site_m, site_m_to_model

LOG_FILE = os.path.join(os.path.expanduser("~"), ".infrared", "rhino-runs.log")
NOT_YET = ("show-last", "export-obj", "clear", "select", "set-key")
_START = [0.0]


def _write(text: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass  # a log that cannot be written must not stop the run


def _progress(text: str) -> None:
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    _write("  ... %s +%.1f s: %s\n" % (stamp, time.time() - _START[0], text))


def run(command: Any = "", objects: Optional[Iterable[Any]] = None, doc: Any = None) -> List[str]:
    """Run one command line on ``objects`` (default: the selected objects).

    Errors you can fix are lines, not exceptions. The lines (or the traceback)
    also go to ``~/.infrared/rhino-runs.log``.
    """
    _START[0] = time.time()
    _progress("run started")
    try:
        lines = _run(command, objects, doc)
    except Exception:
        _write("=== %s\nUnexpected error:\n%s\n" % (datetime.datetime.now().isoformat(timespec="seconds"),
                                                   traceback.format_exc()))
        raise
    _write("=== %s\n%s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), "\n".join(lines)))
    return lines


def _run(command: Any, objects: Optional[Iterable[Any]], doc: Any) -> List[str]:
    text = str(command or "").strip()
    if not text:
        return ["The command is empty. For example: svf"] + command_help.help_lines()
    try:
        cmd = command_line.parse(text)
    except ValueError as error:
        return ["Command error: %s" % error, "Command: %s" % text]
    if cmd.action == "help":
        return command_help.help_lines()
    cmd = shapes.with_look(cmd, text)
    if cmd.action in NOT_YET:
        return ["Command: %s" % cmd.text, "%s is not in the Rhino version yet." % cmd.action]
    _progress("command: %s" % cmd.text)
    try:
        lines = _analysis(cmd, objects, doc or rhino_doc.active_doc())
    except (ValueError, RuntimeError, OSError) as error:
        lines = ["Error: %s" % error]
    return core.finish(cmd, lines)


def _analysis(cmd: Any, objects: Optional[Iterable[Any]], doc: Any) -> List[str]:
    from ir_dynamo import env

    env.setup()
    lat = float(cmd.lat) if cmd.lat else None
    lon = float(cmd.lon) if cmd.lon else None
    site = rhino_doc.read_site(doc, lat, lon)
    buildings, notes = rhino_doc.collect(doc, objects, cmd.scope)
    if not buildings:
        return notes + [
            "No building geometry found. Select the buildings (solids, polysurfaces, meshes) "
            "and run again, or add the word model to analyse every object."
        ]

    def to_site(soups: dict) -> dict:
        return {k: model_to_site_m(v, site).tolist() for k, v in soups.items()}

    _progress("geometry read: %d building object(s)" % len(buildings))
    lines, outs = core.analyse(cmd, to_site(buildings), site, say=_progress)
    lines += notes
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H.%M")
    context = next((o["context_m"] for o in outs.values() if o.get("context_m")), {})
    if context:  # drawn in the free preview too: the user sees the city before paying
        _progress("drawing %d public buildings" % len(context))
        model = {k: site_m_to_model(v, site).tolist() for k, v in context.items()}
        context_id, count = rhino_doc.add_context(doc, model, "%s (%s)" % (cmd.text, stamp))
        lines.append("Drew %d public building(s) of context in grey on the layer %s::%s (object %s)."
                     % (count, rhino_doc.LAYER, rhino_doc.CONTEXT_LAYER, context_id))
    for surface, out in outs.items():
        if not out.get("ran"):
            continue
        _progress("%s: drawing %d values" % (surface, len(out["result"]["values"])))
        tri_m, rgb, legend, colour_notes = shapes.coloured(out["result"], out["analysis_type"], cmd.legend, cmd.gradient)
        tri_model = site_m_to_model(tri_m.reshape(-1), site).reshape(-1, 3, 3)
        try:
            new_id = rhino_doc.add_result(doc, tri_model, rgb, surface, "%s (%s)" % (cmd.text, stamp))
        except RuntimeError as error:  # keep the paid lines and the other target
            lines.append("Error on %s: %s" % (surface, error))
            continue
        lines.append("Drew %s on %s: %d triangles, layer %s, object %s. Use a Shaded or Rendered view."
                     % (out["title"], surface, len(tri_model), rhino_doc.LAYER, new_id))
        lines += colour_notes
        lines += summary.value_lines(out["result"], surface, out["unit"])
        lines += summary.legend_count_lines(legend, out["result"]["values"], out["unit"], cmd.legend)
    return lines
