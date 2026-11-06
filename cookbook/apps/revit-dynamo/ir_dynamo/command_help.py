"""The help text of the ``command`` node, and the command line of the input nodes.

``from_inputs`` lets a run with the input nodes show the command that does the
same, so the user (and the skill) learn the words. No Revit code here.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from . import colors, obj_export, settings, targets
from .command import (
    DEFAULT_HOURS,
    DEFAULT_MONTHS,
    DEFAULT_WIND_DIRECTION,
    DEFAULT_WIND_SPEED,
    SHOW_LAST_WORDS,
    WHOLE_YEAR_HOURS,
    WHOLE_YEAR_MONTHS,
    _num,
    parse,
)


def from_inputs(
    target: Any,
    analysis: Any,
    months: Any,
    hours: Any,
    preview_only: Any,
    fetch_context: Any,
    lat: Any,
    lon: Any,
    set_api_key: Any,
    wind_speed: Any = DEFAULT_WIND_SPEED,
    wind_direction: Any = DEFAULT_WIND_DIRECTION,
    surfaces: Any = "all",
    legend: Any = "",
    gradient: Any = False,
) -> Optional[str]:
    """The command line that does what the input nodes do; None when they are not valid."""
    try:
        if set_api_key:
            return "set-key"
        label = re.sub(r"\s+", " ", str(analysis or "").strip().lower())
        look = ([] if not str(legend or "").strip() else ["legend", str(legend).strip()]) + (
            ["gradient"] if gradient else []
        )
        place = ["lat", str(lat).strip(), "lon", str(lon).strip()] if str(lat or "").strip() else []
        if label in SHOW_LAST_WORDS or label == "show last":
            return parse(" ".join(["show-last"] + look)).text
        keep_all = obj_export.parse_export(label)
        if keep_all is not None:
            return parse(" ".join(["export-obj"] + (["all"] if keep_all else []) + place)).text
        surface = targets.plan_runs(target, label)[0][0]
        row = settings.find_analysis(label, surface)
        word = str(target).strip().lower()
        words = [row.label, "both" if word in targets.BOTH_WORDS else word]
        if row.needs_period:
            words += ["months", str(months).replace(" ", ""), "hours", str(hours).replace(" ", "")]
        if row.needs_wind:
            words += ["wind", _num(float(wind_speed)), _num(float(wind_direction))]
        if words[1] != "ground" and str(surfaces or "all").strip().lower() != "all":
            words += ["surfaces", str(surfaces).strip().lower()]
        words += look + (["context"] if fetch_context else []) + place
        return parse(" ".join(words + ["preview" if preview_only else "run"])).text
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def help_lines() -> List[str]:
    """The Watch text for ``help``: every word, with examples."""
    ground = ", ".join(settings.valid_labels("ground"))
    facades = ", ".join(settings.valid_labels("facades"))
    pwc, tcs = settings.ANALYSES["pwc"].variants, settings.ANALYSES["tcs"].variants
    return [
        "Command words (any order, any case). Without the word run, it is a free preview.",
        "Analysis: ground %s; facades %s." % (ground, facades),
        "  pwc + a criterion: %s (default %s)." % (", ".join(pwc), pwc[0]),
        "  tcs + a subtype: %s (default %s)." % (", ".join(tcs), tcs[0]),
        "Other actions: show-last (draw the saved result again, free; takes legend and gradient), "
        "export-obj [all] (OBJ file for the platform, free), set-key (the API key dialog), help.",
        "Target: ground, facades or both (default: ground where the analysis runs, else facades; "
        "both is two runs and two costs).",
        "months 6-8 or jun-aug, hours 9-17 (default %s and %s; pwc %s and %s)."
        % (DEFAULT_MONTHS, DEFAULT_HOURS, WHOLE_YEAR_MONTHS, WHOLE_YEAR_HOURS),
        "wind 5 270 or wind 5 W: wind analysis only, m/s and the direction it comes from "
        "(default %g m/s from %g deg)." % (DEFAULT_WIND_SPEED, DEFAULT_WIND_DIRECTION),
        "surfaces facades, roofs or all (facades only; default all).",
        "legend platform, trimmed or exact (default %s); gradient: smooth colours for wind and utci."
        % colors.DEFAULT_RANGE_MODE,
        "context: add the public buildings around the site. lat 48.2085 lon 16.3721: another "
        "location (default: the Revit project).",
        "run: run it and pay tokens. Without it: a free preview of the cost.",
        "Examples: pwc | wind 5 270 run | utci facades months jun-aug hours 12-15 | "
        "solar both context run | show-last legend exact | export-obj",
        "Leave the command empty to use the input nodes instead.",
    ]
