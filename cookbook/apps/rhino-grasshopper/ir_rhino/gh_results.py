"""The background work of the Grasshopper component, and the meshes of its outputs.

``thread`` starts the paid run (``work``) or the free preview (``preview_work``)
with the import paths of the solve. They keep plain data (numpy, no Rhino
objects); the meshes are made once, on the UI thread, by ``meshes`` and
``layer_meshes``.
"""

from __future__ import annotations

import datetime
import threading
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ir_dynamo import summary

from . import core, layer_shapes, rhino_doc, shapes
from .site import Site, site_m_to_model

MESH_VERSION = 5  # 2: one memory copy per colour instead of one call per vertex; 3: trees and ground;
# 4: the public buildings grey; 5: lit by face direction


def thread(target: Any, *args: Any) -> None:
    """Start ``target(*args)`` in a background thread with the import paths of this solve.

    The Rhino 9 Script component puts ``sys.path`` back when its solve ends. A
    module that the SDK imports later in the thread (pyarrow for the ground
    materials, live run 2026-11-20) was then not found. So the thread puts the
    paths of this solve back first, and the geodata modules are imported here,
    on the solve, when the libs folder is surely on the path.
    """
    import sys

    paths = list(sys.path)
    try:  # the Overture reads of context (ground materials); absent without the geodata extra
        from infrared_sdk._internal.geodata import optional_deps

        optional_deps.require_overture_imports()
    except Exception:
        pass

    def run() -> None:
        for path in reversed(paths):
            if path not in sys.path:
                sys.path.insert(0, path)
        target(*args)

    threading.Thread(target=run, daemon=True).start()


def expire_later(component: Any) -> None:
    """Solve the component again on the UI thread (from the background thread)."""
    import Grasshopper  # type: ignore
    import Rhino  # type: ignore
    import System  # type: ignore

    def again() -> None:
        doc = component.OnPingDocument()
        if doc is not None:
            doc.ScheduleSolution(
                10, Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(lambda d: component.ExpireSolution(False))
            )

    Rhino.RhinoApp.InvokeOnUiThread(System.Action(again))


def work(state: Dict[str, Any], cmd: Any, buildings_m: dict, own: Dict[str, Any], site: Site, key: str,
          component: Any) -> None:
    """The paid run, in a background thread. Keeps plain data only: no Rhino objects."""
    kept: Dict[str, Any] = {"key": key, "text": cmd.text, "base": shapes.without_look(cmd), "results": [],
                            "tris": [], "values": [], "legend": [], "context": None}
    try:
        lines, outs = core.analyse(
            cmd, buildings_m, site, say=lambda text: state.__setitem__("progress", text), **own
        )
        kept["context"] = context_model(outs, site)
        kept["layers"] = layers_model(outs, site)
        for surface, out in outs.items():
            if out.get("ran"):
                kept["results"].append((surface, out["result"], out["analysis_type"], out["unit"]))
                lines += summary.value_lines(out["result"], surface, out["unit"])
        lines += colour(kept, cmd, site)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H.%M")
        kept["lines"] = core.finish(cmd, lines) + ["Run: %s" % stamp]
    except Exception:
        kept["lines"] = ["Command: %s" % cmd.text, "Error: the run failed.", traceback.format_exc()]
    state["result"] = kept
    state["running"] = False
    expire_later(component)


def context_model(outs: Dict[str, Dict[str, Any]], site: Site) -> Optional[np.ndarray]:
    context = next((o["context_m"] for o in outs.values() if o.get("context_m")), {})
    if not context:
        return None
    flat = np.concatenate([np.asarray(v, dtype=np.float64) for v in context.values()])
    return site_m_to_model(flat, site).reshape(-1, 3, 3)


def colour(kept: Dict[str, Any], cmd: Any, site: Site) -> List[str]:
    """Colour the kept results with the legend of ``cmd``; the meshes are made again. Free:
    a new legend or gradient on a kept result needs no run. Returns the colour notes."""
    kept["tris"], kept["values"], kept["legend"], notes = [], [], [], []
    for surface, result, analysis_type, unit in kept["results"]:
        tri_m, rgb, legend, more = shapes.coloured(result, analysis_type, cmd.legend, cmd.gradient)
        kept["tris"].append((site_m_to_model(tri_m.reshape(-1), site).reshape(-1, 3, 3), rgb))
        kept["values"] += [float(v) for v in result["values"]]
        kept["legend"] += ["[%s]" % surface] + summary.legend_count_lines(legend, result["values"], unit, cmd.legend)
        notes += more
    kept["text"] = cmd.text
    kept.pop("mesh_version", None)
    return notes


def context_mesh(tri: Optional[np.ndarray]) -> Any:
    """The public buildings as one grey mesh, each face lit by its direction.

    With colours of its own the Grasshopper preview shows it grey, not in the red of an
    unselected component that hid the ground result under it. Vertex colours are drawn
    without light, so the grey of each face carries the 3D form (``layer_shapes.lit_grey``).
    """
    if tri is None or not len(tri):
        return None
    return rhino_doc._mesh(tri, layer_shapes.lit_grey(tri, rhino_doc.CONTEXT_GREY))


def layers_model(outs: Dict[str, Dict[str, Any]], site: Site) -> Optional[Dict[str, Any]]:
    """The trees and ground materials sent, in model units (plain numpy, no Rhino)."""
    out = next((o for o in outs.values() if "trees_m" in o), None)
    if out is None:
        return None
    z = float(out.get("layers_z", 0.0))
    trees = np.asarray(out["trees_m"], dtype=np.float64).reshape(-1, 4)
    model_trees = np.zeros((len(trees), 5))
    if len(trees):
        xyz = np.column_stack([trees[:, :2], np.full(len(trees), z)])
        model_trees[:, :3] = site_m_to_model(xyz.reshape(-1), site).reshape(-1, 3)
        model_trees[:, 3:] = trees[:, 2:] / site.unit_m
    ground: Dict[str, List[List[np.ndarray]]] = {}
    for material, polygons in (out.get("ground_m") or {}).items():
        ground[material] = []
        for polygon in polygons:
            rings = []
            for ring in polygon:
                xy = np.asarray(ring, dtype=np.float64).reshape(-1, 2)
                xyz = np.column_stack([xy, np.full(len(xy), z - 0.10)])  # under the ground result (0.05 m above)
                rings.append(site_m_to_model(xyz.reshape(-1), site).reshape(-1, 3))
            ground[material].append(rings)
    return {"trees": model_trees, "ground": ground, "unit": 1.0 / site.unit_m}


def layer_meshes(holder: Optional[Dict[str, Any]]) -> Tuple[Any, List[Any]]:
    """``(trees mesh, [ground mesh per material])`` of a kept result or preview, made once."""
    layers = (holder or {}).get("layers")
    if not layers:
        return None, []
    if "trees_mesh" not in holder:
        tri, rgb = layer_shapes.tree_triangles(layers["trees"], layers["unit"])
        holder["trees_mesh"] = rhino_doc._mesh(tri, rgb) if len(tri) else None
        holder["ground_meshes"] = rhino_doc.ground_meshes(
            layers["ground"], layer_shapes.MATERIAL_RGB, rhino_doc.active_doc().ModelAbsoluteTolerance,
            lift=0.01 * layers["unit"],  # 1 cm per material
        )
    return holder["trees_mesh"], holder["ground_meshes"]


def layer_lines(holder: Optional[Dict[str, Any]]) -> List[str]:
    layers = (holder or {}).get("layers")
    if not layers:
        return []
    order = sorted(layers["ground"])
    counts = ", ".join("%s %d" % (m, len(layers["ground"][m])) for m in order)
    colours = ", ".join("%s %s" % (m, layer_shapes.MATERIAL_RGB.get(m)) for m in order)
    return ["Drawn: %d tree(s) on the output vegetation; ground materials on the output materials, "
            "one mesh each in this order: %s." % (len(layers["trees"]), counts or "none")] + (
        ["Ground colours (RGB): %s." % colours] if colours else [])


def preview_work(state: Dict[str, Any], cmd: Any, buildings_m: dict, own: Dict[str, Any], site: Site, key: str,
                  component: Any) -> None:
    """The free preview, in a background thread: reading the context can take a minute."""
    try:
        lines, outs = core.analyse(
            cmd, buildings_m, site, say=lambda text: state.__setitem__("progress", text), **own
        )
        preview = {"lines": core.finish(cmd, lines), "context": context_model(outs, site),
                   "layers": layers_model(outs, site),
                   "tokens": sum(int(o.get("tokens", 0)) for o in outs.values())}
    except Exception:
        preview = {"lines": ["Command: %s" % cmd.text, "Error: the preview failed.", traceback.format_exc()],
                   "context": None, "layers": None, "tokens": 0}
    state["preview"] = preview
    state["preview_key"] = key
    state["running"] = False
    expire_later(component)


def meshes(kept: Optional[Dict[str, Any]]) -> Tuple[List[Any], Any]:
    """Rhino meshes of a kept result, made once on the UI thread."""
    if not kept:
        return [], None
    if kept.get("mesh_version") != MESH_VERSION:  # a new way to make meshes: made again, free
        import time

        kept["mesh_version"] = MESH_VERSION

        started = time.time()
        kept["meshes"] = [rhino_doc._mesh(tri, rgb) for tri, rgb in kept["tris"]]
        kept["context_mesh"] = context_mesh(kept.get("context"))
        kept.setdefault("lines", []).append(
            "Meshes made in %.1f s (%d triangles)." % (time.time() - started, sum(len(t) for t, _ in kept["tris"]))
        )
    return kept["meshes"], kept["context_mesh"]
