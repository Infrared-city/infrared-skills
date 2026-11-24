"""Preview or run one command on plain data, and the lines of the log. No Rhino import.

``analyse`` is the Rhino twin of ``ir_revit.entry._analysis``: the same calls to
``ir_dynamo.run.run_analysis`` and the same lines, so a Revit user and a Rhino
user read the same text. ``finish`` puts the warnings first, as in Revit.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from ir_dynamo import summary, targets

from .site import Site

Soups = Dict[str, List[float]]
MARGIN_HINT = "; set it with the word margin"  # the Revit hint of the Area line: no margin in Rhino


def analyse(
    cmd: Any,
    buildings_m: Soups,
    site: Site,
    *,
    terrain_m: Optional[Soups] = None,
    trees_m: Optional[List[Any]] = None,
    ground_m: Optional[Dict[str, List[Any]]] = None,
    run: Optional[Callable[..., Dict[str, Any]]] = None,
    say: Optional[Callable[[str], None]] = None,
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Preview (or, with ``cmd.paid``, run) ``cmd`` for each target it has.

    ``trees_m``, ``ground_m``: own trees and ground materials in site metres
    (``ir_dynamo.own_layers``); they go to every target.

    Returns the lines and ``{target: out of run_analysis}``. A failed second
    target is a line: it must not hide a first one that was paid for.
    """
    if run is None:
        from ir_dynamo.run import run_analysis as run
    say = say or (lambda text: None)
    to_run, skipped = targets.plan_runs(cmd.target, cmd.analysis)
    lines = [
        "Location: lon %.5f, lat %.5f (%s), true north %.1f deg from the model +y."
        % (site.lon, site.lat, site.source, 0.0 - math.degrees(site.north_rad)),  # 0.0 - : no "-0.0"
        "Geometry: %d building object(s), %d terrain." % (len(buildings_m), len(terrain_m or {})),
    ] + skipped
    if cmd.margin:  # the area is always the default of the run (30 m ground, 5 m facades, more with context)
        lines.append("Warning: margin is not in the Rhino version; the default area is used.")
    outs: Dict[str, Dict[str, Any]] = {}
    for surface in to_run:
        say("%s: preparing and sending" % surface)
        try:
            outs[surface] = run(
                surface,
                cmd.analysis,
                buildings_m,
                site.lon,
                site.lat,
                preview_only=not cmd.paid,
                months=cmd.months,
                hours=cmd.hours,
                fetch_context=cmd.fetch_context,
                terrain_m=terrain_m or None,
                trees_m=trees_m or None,
                ground_m=ground_m or None,
                wind_speed=float(cmd.wind_speed),
                wind_direction=int(round(float(cmd.wind_direction))),
                surfaces=cmd.surfaces,
                on_status=lambda text, s=surface: say("%s: %s" % (s, text)),
                return_context=True,  # Rhino draws the public buildings of context
            )
        except (ValueError, RuntimeError) as error:
            lines.append("Error on %s: %s" % (surface, error))
    if len(outs) > 1:
        lines.append(
            "%s of both targets: %s." % ("Cost" if cmd.paid else "Preview", targets.combined_cost(outs))
        )
    for surface, out in outs.items():
        lines += ["[%s] %s" % (surface, out["status"])]
        lines += ["[%s] %s" % (surface, w.replace(MARGIN_HINT, "")) for w in out["warnings"]]
    return lines, outs


def finish(cmd: Any, lines: List[str]) -> List[str]:
    """The command first, then the warnings, then the rest; the paid line after a preview."""
    if any("Preview only:" in line for line in lines):
        lines = lines + ["To run it (paid): %s" % cmd.paid_text()]
    return ["Command: %s" % cmd.text] + summary.warnings_first(lines)
