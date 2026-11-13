"""The help text of the ``command`` node. No Revit code here."""

from __future__ import annotations

from typing import List

from . import colors, settings
from .command import (
    DEFAULT_HOURS,
    DEFAULT_MONTHS,
    DEFAULT_WIND_DIRECTION,
    DEFAULT_WIND_SPEED,
    WHOLE_YEAR_HOURS,
    WHOLE_YEAR_MONTHS,
)


def help_lines() -> List[str]:
    """The Watch text for ``help``: every word, with examples."""
    ground = ", ".join(settings.valid_labels("ground"))
    facades = ", ".join(settings.valid_labels("facades"))
    pwc, tcs = settings.ANALYSES["pwc"].variants, settings.ANALYSES["tcs"].variants
    return [
        "Select the buildings in Revit, type a command, press Run. Words in any order, any case.",
        "select: pick the buildings in Revit now (click them, then Finish); the next commands use them. "
        "select link: pick elements inside a linked model. Or select in Revit before you press Run.",
        "Without the word run, it is a free preview of the cost.",
        "Analysis: ground %s; facades %s." % (ground, facades),
        "  pwc + a criterion: %s (default %s)." % (", ".join(pwc), pwc[0]),
        "  tcs + a subtype: %s (default %s)." % (", ".join(tcs), tcs[0]),
        "Target: ground, facades or both (default: ground where the analysis runs, else facades; "
        "both is two runs and two costs).",
        "What gets a result: the selection (default; the rest of the model and its links only "
        "shade). model: every building of the model and its links, no selection needed. "
        "alone: the selection, and nothing else shades (faster). Pick an element inside a link with Tab.",
        "context: add the public buildings around the site; the result covers them too.",
        "margin 100: metres of ground around the selection (default 30 for the ground, 5 for facades; "
        "with context about 250, as much as the same cost gives).",
        "months 6-8 or jun-aug, hours 9-17 (default %s and %s; pwc %s and %s)."
        % (DEFAULT_MONTHS, DEFAULT_HOURS, WHOLE_YEAR_MONTHS, WHOLE_YEAR_HOURS),
        "wind 5 270 or wind 5 W: wind analysis only, m/s and the direction it comes from "
        "(default %g m/s from %g deg)." % (DEFAULT_WIND_SPEED, DEFAULT_WIND_DIRECTION),
        "surfaces facades, roofs or all (facades only; default all).",
        "legend platform, trimmed or exact (default %s); gradient: smooth colours for wind and utci."
        % colors.DEFAULT_RANGE_MODE,
        "lat 48.2085 lon 16.3721: another location (default: the Revit project, Manage > Location).",
        "Every result stays in the model. A new result hides the earlier results of its target in "
        "the active view: show them again in Visibility/Graphics (VG) > Filters.",
        "run: run it and pay tokens.",
        "Other actions: show-last (draw the saved result again, free; takes legend, gradient), "
        "export-obj [all] [model] (OBJ file for the platform, free), clear (delete every Infrared "
        "result, legend view and view filter of the model), set-key (the API key dialog), help.",
        "Examples: svf | pwc run | wind 5 270 run | utci months jun-aug hours 12-15 run | "
        "solar both context run | daylight facades model run | show-last legend exact | export-obj | clear",
    ]
