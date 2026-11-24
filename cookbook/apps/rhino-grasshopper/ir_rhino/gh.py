"""The Grasshopper component: geometry and a command in; mesh, context, values, legend, log out.

The ``.gh`` file holds one Python 3 Script component that calls::

    mesh, context, values, legend, log = gh.solve(ghenv, geometry, command, trees, ground, material)

Inputs: ``geometry`` (List Access, Breps or Meshes: the SDK ``buildings``), ``command``
(Item Access, text). The surroundings come from ``context`` (the public buildings). Optional (List Access): ``trees`` (points, circles or
solids), ``ground`` (closed curves, surfaces or meshes) and ``material`` (one of
asphalt, concrete, soil, vegetation, water; one for all or one per ground item),
see ``own_inputs``. Outputs: ``mesh``, ``context``, ``values``, ``legend``, ``log``,
``vegetation`` (the trees sent, one mesh) and ``materials`` (the ground materials sent,
one coloured mesh per material).

The rules that keep a paid run from running twice are in ``decide`` (pure, tested):

* a free preview runs when the geometry or the command changes;
* a paid run starts only when the command text CHANGES to one with ``run``. A
  change of the geometry, a slider, or opening the file never starts one; the
  first solve after the file opens has no earlier text, so it never runs;
* the run and the preview work in a background thread (network and numpy
  only). When one is done, the component is solved again and shows it. A
  command typed meanwhile is read then (a solve that waits does not count as seen).
"""

from __future__ import annotations

import datetime
import hashlib
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ir_dynamo import command as command_line
from ir_dynamo import command_help, summary

from . import gh_results, own_inputs, rhino_doc, shapes
from .site import Site, model_to_site_m

STATE_KEY = "infrared-gh-v1"  # change it when the kept state changes shape


def decide(seen: Optional[str], text: str, paid: bool, running: bool) -> str:
    """What one solve does: "wait", "preview", "run", "show" or "blocked".

    ``seen``: the command text of the last solve of this component, None for the
    first solve since the file opened (or since the component was placed).
    """
    if running:
        return "wait"
    if not paid:
        return "preview"
    if seen is None:
        return "blocked"  # a file saved with "run" in its command must not pay on opening
    if seen != text:
        return "run"
    return "show"


def _state(component: Any) -> Dict[str, Any]:
    import scriptcontext as sc  # type: ignore

    key = "%s:%s" % (STATE_KEY, component.InstanceGuid)
    if key not in sc.sticky:
        sc.sticky[key] = {}
    return sc.sticky[key]


def _items(value: Any) -> List[Any]:
    """An input as a list: Item Access gives one object, List Access a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "Count") and hasattr(value, "__iter__") and not hasattr(value, "ObjectType"):
        return list(value)  # a .NET list
    return [value]


def _unwrap(item: Any) -> Any:
    """The Rhino geometry inside a Grasshopper wrapper (GH_Brep, GH_Mesh, ...)."""
    for name in ("ScriptVariable",):
        if hasattr(item, name) and not hasattr(item, "ObjectType"):
            try:
                return getattr(item, name)()
            except Exception:
                pass
    if hasattr(item, "Value") and not hasattr(item, "ObjectType"):
        return item.Value
    return item


def _by_id(item: Any, doc: Any) -> Any:
    """The geometry of an id. The script component gives referenced geometry as an id
    in its own document (``ghdoc``), not in the Rhino document: ``coercegeometry``
    looks in the current script document, then the Rhino document is tried."""
    import System  # type: ignore

    try:
        import rhinoscriptsyntax as rs  # type: ignore

        found = rs.coercegeometry(item, False)
        if found is not None:
            return found
    except Exception:
        pass
    obj = doc.Objects.FindId(System.Guid(str(item)))
    return obj.Geometry if obj is not None else None


def describe(value: Any) -> str:
    """What an input holds, for an error line: count and type names."""
    items = _items(value)
    names = sorted({type(_unwrap(i)).__name__ for i in items if i is not None})
    return "%d item(s)%s" % (len(items), (": " + ", ".join(names)) if names else "")


def _geometries(items: Any, doc: Any) -> List[Any]:
    """The Rhino geometry of each input item (None where an id finds nothing)."""
    import System  # type: ignore

    out = []
    for item in _items(items):
        item = _unwrap(item) if item is not None else None
        if isinstance(item, System.Guid) or type(item).__name__ in ("Guid", "UUID"):
            item = _by_id(item, doc)
        out.append(item)
    return out


def _soups(items: Any, doc: Any, prefix: str) -> Tuple[Dict[str, List[float]], int]:
    """Flat triangles in model units per item, and the number of items left out."""
    import System  # type: ignore

    out: Dict[str, List[float]] = {}
    skipped = 0
    for k, item in enumerate(_items(items)):
        if item is None:
            continue
        item = _unwrap(item)
        geometry = item
        if isinstance(item, System.Guid) or type(item).__name__ in ("Guid", "UUID"):
            geometry = _by_id(item, doc)
        soup = rhino_doc.triangles(geometry) if geometry is not None else None
        if soup:
            out["%s-%d" % (prefix, k)] = soup
        else:
            skipped += 1
    return out, skipped


def _key(buildings: Dict[str, List[float]], site: Site, text: str, own: Any = None) -> str:
    digest = hashlib.sha1(text.encode("utf-8"))
    digest.update(repr(own).encode("utf-8"))  # trees and ground: plain tuples and dicts
    digest.update(repr((site.lon, site.lat, site.north_rad, site.base, site.unit_m)).encode("utf-8"))
    for name in sorted(buildings):
        digest.update(name.encode("utf-8"))
        digest.update(np.asarray(buildings[name], dtype=np.float64).round(4).tobytes())
    return digest.hexdigest()


def _message(component: Any, text: str, lines: List[str]) -> None:
    import Grasshopper  # type: ignore

    component.Message = text
    level = Grasshopper.Kernel.GH_RuntimeMessageLevel
    for line in lines:
        if line.startswith("Command error") or line.startswith("  Error") or line.startswith("Error"):
            component.AddRuntimeMessage(level.Error, line.strip())
        elif summary.is_warning(line) and not line.startswith("Warnings ("):
            component.AddRuntimeMessage(level.Warning, line.strip())


def _log(lines: List[str]) -> None:
    """The lines of one solve, in the log of the Rhino function (``[gh]`` in front)."""
    from . import entry

    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    entry._write("=== %s [gh]\n%s\n" % (stamp, "\n".join(str(x) for x in lines)))


def solve(ghenv: Any, geometry: Any, command: Any, trees: Any = None, ground: Any = None,
          material: Any = None) -> Tuple[Any, ...]:
    """One solve: ``(mesh, context, values, legend, log, vegetation, materials)``. Logged."""
    try:
        out = _solve(ghenv, geometry, command, trees, ground, material)
    except Exception:
        _log(["Unexpected error:", traceback.format_exc()])
        raise
    out = tuple(out) + (None, [])[len(out) - 5:]  # the early returns have no trees and ground
    _log(out[4] + ["(mesh: %s, context: %s, values: %d, trees: %s, materials: %d)" % (
        "yes" if out[0] else "no", "yes" if out[1] is not None else "no", len(out[2]),
        "yes" if out[5] is not None else "no", len(out[6]))])
    # A component of the earlier code has 5 outputs and unpacks 5 values: give it those, so it
    # keeps working (without trees and ground) until its code is updated.
    if "vegetation" not in [p.Name for p in ghenv.Component.Params.Output]:
        return out[:5]
    return out


def _solve(ghenv: Any, geometry: Any, command: Any, trees: Any = None, ground: Any = None,
           material: Any = None) -> Tuple[Any, ...]:
    component = ghenv.Component
    state = _state(component)
    text = str(command or "").strip()
    seen = state.get("seen")  # set only by a solve that reaches decide, see below
    kept = state.get("result")
    if not text:
        _message(component, "", [])
        return None, None, [], [], ["The command is empty. For example: svf"] + command_help.help_lines()
    try:
        cmd = command_line.parse(text)
    except ValueError as error:
        lines = ["Command error: %s" % error]
        _message(component, "error", lines)
        return None, None, [], [], lines
    if cmd.action == "help":
        return None, None, [], [], command_help.help_lines()
    if cmd.action != "analysis":
        return None, None, [], [], ["%s is not in the Grasshopper version yet." % cmd.action]
    cmd = shapes.with_look(cmd, text)

    from ir_dynamo import env

    env.setup()
    doc = rhino_doc.active_doc()
    try:
        site = rhino_doc.read_site(doc, float(cmd.lat) if cmd.lat else None, float(cmd.lon) if cmd.lon else None)
    except ValueError as error:
        lines = ["Command: %s" % cmd.text, "Error: %s" % error]
        _message(component, "no location", lines)
        return None, None, [], [], lines
    buildings, skipped = _soups(geometry, doc, "gh")
    if not buildings:
        lines = ["Command: %s" % cmd.text,
                 "Error: connect solids or meshes to the input geometry (it holds %s)." % describe(geometry)]
        _message(component, "no geometry", lines)
        return None, None, [], [], lines
    try:
        tree_list, trees_skipped = own_inputs.trees(_geometries(trees, doc), site)
        ground_m, ground_skipped = own_inputs.ground(
            _geometries(ground, doc), [_unwrap(m) for m in _items(material)], site, doc.ModelAbsoluteTolerance
        )
    except ValueError as error:
        lines = ["Command: %s" % cmd.text, "Error: %s" % error]
        _message(component, "ground error", lines)
        return None, None, [], [], lines
    own = {"trees_m": tree_list, "ground_m": ground_m}
    buildings_m = {k: model_to_site_m(v, site).tolist() for k, v in buildings.items()}
    key = _key(buildings_m, site, shapes.without_look(cmd).text, own)  # the legend changes no result
    notes = ["Left out %d input(s) of geometry: not a solid or mesh." % skipped] if skipped else []
    if trees_skipped:
        notes.append("Left out %d input(s) of trees: not a point, circle, solid or mesh." % trees_skipped)
    if ground_skipped:
        notes.append("Left out %d input(s) of ground: no closed outline that is not vertical." % ground_skipped)

    # A solve stopped by an error above (no geometry, no location), or one that waits for a
    # run or a preview, does not count as seen: "run" typed before the geometry is connected,
    # or during a preview, then runs when the component can.
    action = decide(seen, text, cmd.paid, bool(state.get("running")))
    if action != "wait":
        state["seen"] = text
    if action == "run" and kept and kept.get("base") == shapes.without_look(cmd) and kept.get("key") == key:
        # Only the legend or the gradient changed: colour the kept result again, free.
        notes += gh_results.colour(kept, cmd, site) + ["Coloured again with legend %s%s: free, no run." % (
            cmd.legend, " gradient" if cmd.gradient else "")]
        action = "show"
    if action == "wait":
        meshes, context = gh_results.meshes(kept)
        trees_mesh, ground = gh_results.layer_meshes(kept)
        lines = ["Running: %s. %s" % (state.get("running_text", ""), state.get("progress", "")),
                 "The result comes here when it is done; Rhino stays usable."]
        _message(component, "running...", [])
        return (meshes, context, (kept or {}).get("values", []), (kept or {}).get("legend", []), lines,
                trees_mesh, ground)
    if action == "run":
        state.update(running=True, running_text=cmd.text, progress="starting")
        gh_results.thread(gh_results.work, state, cmd, buildings_m, own, site, key, component)
        _message(component, "running...", [])
        meshes, context = gh_results.meshes(kept)
        trees_mesh, ground = gh_results.layer_meshes(kept)
        return meshes, context, [], [], ["Command: %s" % cmd.text, "Running in the background..."], trees_mesh, ground
    if action in ("show", "blocked"):
        lines = list((kept or {}).get("lines") or ["Command: %s" % cmd.text])
        if action == "blocked":
            lines.append("Not run: the file was opened with run in the command. To run it (paid), "
                         "edit the command, for example remove run and type it again.")
        elif not kept or kept.get("text") != cmd.text:  # kept: the normalised text
            lines.append("Not run: this command has no result yet. To run it (paid), edit the command, "
                         "for example remove run and type it again.")
        elif kept.get("key") != key:
            lines.append("Warning: the geometry or the location changed after this run; the result is of "
                         "the earlier one. To run again (paid), edit the command.")
        meshes, context = gh_results.meshes(kept)
        trees_mesh, ground = gh_results.layer_meshes(kept)
        _message(component, "done" if kept else "not run", lines)
        return (meshes, context, (kept or {}).get("values", []), (kept or {}).get("legend", []),
                lines + gh_results.layer_lines(kept) + notes, trees_mesh, ground)

    # preview: free, once per geometry and command, in the background
    if state.get("preview_key") != key:
        state.update(running=True, running_text="%s (free preview)" % cmd.text, progress="starting")
        gh_results.thread(gh_results.preview_work, state, cmd, buildings_m, own, site, key, component)
        _message(component, "preview...", [])
        return None, None, [], [], ["Command: %s" % cmd.text, "Free preview in the background..."], None, []
    preview = state["preview"]
    if "context_mesh" not in preview:
        preview["context_mesh"] = gh_results.context_mesh(preview["context"])
    trees_mesh, ground = gh_results.layer_meshes(preview)
    _message(component, "preview: %d tokens" % preview["tokens"], preview["lines"])
    return (None, preview["context_mesh"], [], [], preview["lines"] + gh_results.layer_lines(preview) + notes,
            trees_mesh, ground)
