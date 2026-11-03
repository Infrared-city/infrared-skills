"""What a script run does on each target: parsing, planning, cost text, saved results.

One script covers the ground grid, the facades and roofs, or both. One SDK request
computes only one of them, so "both" is two runs and two costs. No Revit code here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import settings

SURFACES = ("ground", "facades")
BOTH_WORDS = ("both", "all")
VALID_TARGETS = ("ground", "facades", "both", "all")


def parse_target(text: Any) -> List[str]:
    """``"ground"``, ``"facades"``, ``"both"`` or ``"all"`` to the surfaces to run.

    Raises
    ------
    ValueError
        With the valid values, for any other text.
    """
    word = str(text).strip().lower()
    if word in SURFACES:
        return [word]
    if word in BOTH_WORDS:
        return list(SURFACES)
    raise ValueError(
        "target %r is not valid. Use one of: %s." % (text, ", ".join(VALID_TARGETS))
    )


def all_labels() -> List[str]:
    """Every label that runs on at least one target."""
    return list(settings.ANALYSES)


def plan_runs(target: Any, label: str) -> Tuple[List[str], List[str]]:
    """Which surfaces run for ``label``, and the Watch lines for the skipped ones.

    One target: the analysis must run there, else ``ValueError`` (the same error as
    before, with the valid labels of that target). ``"both"``: a surface where the
    analysis does not exist is skipped with a line; an unknown label is an error.

    Returns
    -------
    (list of str, list of str)
        ``(surfaces_to_run, skipped_lines)``.
    """
    surfaces = parse_target(target)
    if len(surfaces) == 1:
        settings.find_analysis(label, surfaces[0])
        return surfaces, []
    run = [s for s in surfaces if _runs_on(label, s)]
    if not run:
        raise ValueError(
            "Analysis %r is unknown. Use one of: %s; or show-last to draw the last "
            "result again (free)." % (label, ", ".join(all_labels()))
        )
    skipped = [
        "Skipped %s: the analysis %r does not run on %s (it runs on %s only)."
        % (s, label, s, run[0])
        for s in surfaces
        if s not in run
    ]
    return run, skipped


def _runs_on(label: str, surface: str) -> bool:
    try:
        settings.find_analysis(label, surface)
    except ValueError:
        return False
    return True


def combined_cost(outs: Dict[str, Dict[str, Any]]) -> str:
    """One line for the previews or runs of several targets, with the summed tokens.

    ``outs`` maps a surface to the dict of ``run_analysis`` (needs ``cost`` and
    ``tokens``).
    """
    parts = ["%s: %s" % (surface, out["cost"]) for surface, out in outs.items()]
    total = sum(int(out["tokens"]) for out in outs.values())
    if len(outs) == 1:
        return parts[0]
    return "%s. Total: about %d tokens" % ("; ".join(parts), total)


def _surface_of(result: Dict[str, Any]) -> str:
    return "ground" if result.get("kind") == "points" else "facades"


def load_entries(data: Any) -> List[Dict[str, Any]]:
    """The saved entries of a last-result file, old or new format.

    New: ``{"entries": [{"target", "result", "title", "unit", "true_north_rad"}]}``.
    Old: one ``{"result", "title", "unit", "true_north_rad"}`` (no ``target``; it is
    read from the result kind).
    """
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return [dict(e) for e in data["entries"]]
    if isinstance(data, dict) and "result" in data:
        entry = dict(data)
        entry["target"] = entry.get("target") or _surface_of(data["result"])
        return [entry]
    return []


def merge_entries(old: Any, new: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The file content after a run: the new entries replace the old ones of the same
    target. An entry of another target stays only if it is from the same Revit
    document (its shape is still in that model); a result of another model is
    dropped, so "show-last" never draws it here."""
    fresh = {e["target"] for e in new}
    documents = {e.get("document") for e in new}
    kept = [
        e
        for e in load_entries(old)
        if e["target"] not in fresh and e.get("document") in documents
    ]
    ordered = sorted(kept + list(new), key=lambda e: SURFACES.index(e["target"]))
    return {"entries": ordered}
