"""One text line that sets every input of a run: the ``command`` node.

``parse("pwc ground months 6-8 run")`` gives a ``Command``. A word that is not in
the line takes its default (``Command`` fields), not the value of an input node:
the line alone says what runs. Without the word ``run`` it is a free preview.
``Command.text`` writes the line back with every value that matters filled in;
``command_help.from_inputs`` writes the line of the input nodes. No Revit code here.

Words (any order, any case; see ``help_lines``)::

    svf | solar | sun-hours | daylight | wind | pwc | tcs | utci   the analysis
    pwc lawson-2001, tcs heat-stress                            PWC criterion, TCS subtype
    show-last | export-obj [all] | set-key | help               the other actions
    ground | facades | both                                     the target
    months 6-8   hours 9-17   surfaces roofs   legend exact     values
    wind 5 270 (or wind 5 W, speed 5, direction 270)            wind analysis only
    gradient   context   lat 48.2 lon 16.37   run               the rest
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from . import colors, settings, targets

HELP_WORDS = ("help", "?")
SET_KEY_WORDS = ("set-key", "set-api-key", "api-key", "key")
SHOW_LAST_WORDS = ("show-last", "show-latest", "last")
EXPORT_WORDS = ("export-obj", "export", "obj")
TARGET_WORDS = {"ground": "ground", "facades": "facades", "facade": "facades", "both": "both"}
SURFACE_VALUES = ("facades", "roofs", "all")
VALUE_WORDS = {  # the word -> the field its next word sets
    "months": "months",
    "month": "months",
    "hours": "hours",
    "hour": "hours",
    "legend": "legend",
    "surfaces": "surfaces",
    "lat": "lat",
    "lon": "lon",
    "speed": "wind_speed",
    "direction": "wind_direction",
    "dir": "wind_direction",
}
COMPASS = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}
DEFAULT_MONTHS, DEFAULT_HOURS = "6-8", "8-18"
WHOLE_YEAR_MONTHS, WHOLE_YEAR_HOURS = "1-12", "0-23"
DEFAULT_WIND_SPEED, DEFAULT_WIND_DIRECTION = 5.0, 270.0
ANALYSIS_WORDS = dict(
    {k: k for k in settings.ANALYSES},
    **{a: k for a, k in settings.ALIASES.items() if " " not in a},
)
# The fields each action other than an analysis takes; any other word is an error.
ACTION_FIELDS = {
    "show-last": ("legend", "gradient"),
    "export-obj": ("all", "lat", "lon"),
    "set-key": (),
    "help": (),
}


@dataclass(frozen=True)
class Command:
    """What one command line runs. The fields are the inputs of ``entry._run``."""

    action: str  # "analysis", "show-last", "export-obj", "set-key" or "help"
    analysis: str = ""  # the label with its variant, for example "pwc lawson-lddc"
    target: str = ""  # "ground", "facades" or "both"
    months: str = DEFAULT_MONTHS
    hours: str = DEFAULT_HOURS
    wind_speed: float = DEFAULT_WIND_SPEED
    wind_direction: float = DEFAULT_WIND_DIRECTION
    surfaces: str = "all"
    legend: str = colors.DEFAULT_RANGE_MODE
    gradient: bool = False
    fetch_context: bool = False
    lat: str = ""
    lon: str = ""
    export_all: bool = False
    paid: bool = False

    @property
    def text(self) -> str:
        """The command line with every value that matters; ``parse(text)`` gives it back."""
        if self.action in ("help", "set-key"):
            return self.action
        if self.action == "show-last":
            return " ".join(["show-last"] + self._look())
        if self.action == "export-obj":
            return " ".join(["export-obj"] + (["all"] if self.export_all else []) + self._place())
        row = _row(self.analysis)
        words = [self.analysis]
        if row.needs_wind:  # "wind 5 270": the analysis word with its speed and direction
            words += [_num(self.wind_speed), _num(self.wind_direction)]
        words.append(self.target)
        if row.needs_period:
            words += ["months", self.months, "hours", self.hours]
        if self.surfaces != "all":
            words += ["surfaces", self.surfaces]
        words += self._look() + (["context"] if self.fetch_context else []) + self._place()
        return " ".join(words + ["run" if self.paid else "preview"])

    def _look(self) -> List[str]:
        out = [] if self.legend == colors.DEFAULT_RANGE_MODE else ["legend", self.legend]
        return out + (["gradient"] if self.gradient else [])

    def _place(self) -> List[str]:
        return ["lat", self.lat, "lon", self.lon] if self.lat else []

    def inputs(self) -> Dict[str, Any]:
        """The keyword arguments of ``entry._run`` (all but ``elements`` and ``terrain``)."""
        analysis = {
            "analysis": self.analysis,
            "show-last": "show-last",
            "export-obj": "export-obj all" if self.export_all else "export-obj",
        }.get(self.action, "")
        return {
            "target": self.target or "ground",
            "analysis": analysis,
            "months": self.months,
            "hours": self.hours,
            "preview_only": not self.paid,
            "fetch_context": self.fetch_context,
            "lat": self.lat,
            "lon": self.lon,
            "set_api_key": self.action == "set-key",
            "wind_speed": self.wind_speed,
            "wind_direction": self.wind_direction,
            "surfaces": self.surfaces,
            "legend": self.legend,
            "gradient": self.gradient,
        }

    def paid_text(self) -> str:
        """The same line with ``run``: what to type to run it for tokens."""
        return replace(self, paid=True).text


def _num(x: float) -> str:
    return "%g" % x


def _row(label: str) -> settings.Analysis:
    return settings.ANALYSES[label.split(" ")[0]]


def _speed(word: str) -> Optional[float]:
    """``"5"``, ``"5.5"``, ``"5m/s"`` -> the number; anything else -> None."""
    word = word[:-3] if word.endswith("m/s") else word
    try:
        return float(word.replace(",", "."))
    except ValueError:
        return None


def _direction(word: str) -> Optional[float]:
    """``"270"``, ``"270deg"``, ``"w"``, ``"nw"`` -> degrees (the wind comes from there)."""
    if word in COMPASS:
        return float(COMPASS[word])
    for tail in ("deg", "°"):
        word = word[: -len(tail)] if word.endswith(tail) else word
    try:
        return float(word)
    except ValueError:
        return None


def vocabulary() -> List[str]:
    """Every word a command knows (for the "did you mean" hint)."""
    variants = {v for a in settings.ANALYSES.values() for v in a.variants}
    return sorted(
        set(ANALYSIS_WORDS)
        | variants
        | set(settings.VARIANT_ALIASES)
        | set(HELP_WORDS + SET_KEY_WORDS + SHOW_LAST_WORDS + EXPORT_WORDS)
        | set(TARGET_WORDS)
        | set(VALUE_WORDS)
        | set(colors.RANGE_MODES)
        | {"wind", "gradient", "context", "run", "preview", "all"}
    )


def _unknown(word: str) -> ValueError:
    close = difflib.get_close_matches(word, vocabulary(), n=1, cutoff=0.6)
    hint = " Did you mean %r?" % close[0] if close else ""
    return ValueError("Unknown word %r.%s Type help to see every word." % (word, hint))


def parse(line: Any) -> Command:
    """Read one command line.

    Raises
    ------
    ValueError
        With the word that is wrong and what to write instead.
    """
    words = [w for w in re.split(r"[\s,;]+", str(line or "").strip().lower()) if w]
    if not words:
        raise ValueError("The command is empty. Type help to see every word.")
    if any(w in HELP_WORDS for w in words):
        return Command("help")
    found: Dict[str, Any] = {}

    def put(field: str, value: Any, word: str) -> None:
        if field in found and found[field] != value:
            raise ValueError(
                "%s is given twice (%r and %r). Keep one." % (field.replace("_", " "), found[field], value)
            )
        found[field] = value

    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if word in VALUE_WORDS:
            if i >= len(words):
                raise ValueError("%r needs a value after it, for example %s." % (word, _EXAMPLES[VALUE_WORDS[word]]))
            put(VALUE_WORDS[word], words[i], word)
            i += 1
        elif word in SET_KEY_WORDS:
            put("action", "set-key", word)
        elif word in SHOW_LAST_WORDS:
            put("action", "show-last", word)
        elif word in EXPORT_WORDS:
            put("action", "export-obj", word)
        elif word in TARGET_WORDS:
            put("target", TARGET_WORDS[word], word)
        elif word in colors.RANGE_MODES:
            put("legend", word, word)
        elif word in ("gradient", "context", "all"):
            put(word, True, word)
        elif word in ("run", "preview"):
            put("cost", word, word)
        elif word in ("wind", "wind-speed") and i < len(words) and _speed(words[i]) is not None:
            # "wind 5 270": the wind analysis, unless another analysis is named
            # ("pwc wind 5 270": then it is an error in _resolve, not a second analysis).
            put("wind_speed", words[i], word)
            i += 1
            if i < len(words) and _direction(words[i]) is not None:
                put("wind_direction", words[i], word)
                i += 1
        elif word in ANALYSIS_WORDS:
            put("analysis", ANALYSIS_WORDS[word], word)
        elif word in settings.VARIANT_ALIASES or any(word in a.variants for a in settings.ANALYSES.values()):
            put("variant", word, word)
        else:
            raise _unknown(word)
    return _resolve(found)


_EXAMPLES = {
    "months": "months 6-8 or months jun-aug",
    "hours": "hours 9-17",
    "legend": "legend exact (platform, trimmed or exact)",
    "surfaces": "surfaces roofs (facades, roofs or all)",
    "lat": "lat 48.2085",
    "lon": "lon 16.3721",
    "wind_speed": "speed 5",
    "wind_direction": "direction 270 or direction W",
}


def _resolve(found: Dict[str, Any]) -> Command:
    """The words found -> a checked ``Command`` with the defaults filled in."""
    action = found.pop("action", None)
    if not action and "analysis" not in found and "wind_speed" in found:
        found["analysis"] = "wind"  # "wind 5 270" alone
    if action and "analysis" in found:
        raise ValueError("%s and %s cannot run together. Keep one." % (action, found["analysis"]))
    if action is None and "analysis" not in found:
        raise ValueError(
            "Say what to run: one of %s, or show-last, export-obj, set-key. Type help to see every word."
            % ", ".join(settings.ANALYSES)
        )
    if action:
        return _other_action(action, found)
    if found.pop("all", False):
        raise ValueError("'all' alone is not clear: write both (ground and facades) or surfaces all.")
    row = settings.ANALYSES[found.pop("analysis")]
    label = row.key
    variant = found.pop("variant", "")
    if variant:
        if not row.variants:
            raise ValueError("%r is not used by %s." % (variant, row.title))
        label = "%s %s" % (row.key, variant)
    if row.variants:  # fills in the default variant, checks the given one
        label = settings.find_analysis(label, "ground" if row.ground else "facades").label
    target = found.pop("target", "ground" if row.ground else "facades")
    targets.plan_runs(target, label)  # the analysis must run on the target
    whole = row.whole_year
    months = found.pop("months", WHOLE_YEAR_MONTHS if whole else DEFAULT_MONTHS)
    hours = found.pop("hours", WHOLE_YEAR_HOURS if whole else DEFAULT_HOURS)
    settings.parse_months(months)
    settings.parse_hours(hours)
    speed, direction = found.pop("wind_speed", None), found.pop("wind_direction", None)
    if (speed is not None or direction is not None) and not row.needs_wind:
        raise ValueError(
            "A wind speed and direction are used by the wind analysis only; %s reads "
            "the weather file of the site. Remove them." % row.title
        )
    surfaces = found.pop("surfaces", "all")
    if surfaces not in SURFACE_VALUES:
        raise ValueError("surfaces must be one of %s, not %r." % (", ".join(SURFACE_VALUES), surfaces))
    if surfaces != "all" and target == "ground":
        raise ValueError("surfaces (%s) is for facades only; the target is ground." % surfaces)
    command = Command(
        "analysis",
        analysis=label,
        target=target,
        months=months,
        hours=hours,
        wind_speed=_checked_speed(speed),
        wind_direction=_checked_direction(direction),
        surfaces=surfaces,
        fetch_context=bool(found.pop("context", False)),
        paid=found.pop("cost", "preview") == "run",
        **_look_and_place(found),
    )
    return command


def _look_and_place(found: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "legend" in found:
        out["legend"] = colors.parse_range_mode(found.pop("legend"))
    if found.pop("gradient", False):
        out["gradient"] = True
    lat, lon = found.pop("lat", None), found.pop("lon", None)
    if (lat is None) != (lon is None):
        raise ValueError("Give both lat and lon, or neither (then the Revit project location is used).")
    if lat is not None:
        out["lat"], out["lon"] = _coordinate(lat, "lat", 90.0), _coordinate(lon, "lon", 180.0)
    return out


def _coordinate(text: str, name: str, limit: float) -> str:
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        raise ValueError("%s %r is not a number. Write it like %s." % (name, text, _EXAMPLES[name]))
    if not -limit <= value <= limit:
        raise ValueError("%s %s is out of range (-%g to %g)." % (name, text, limit, limit))
    return _num(value)


def _checked_speed(text: Optional[str]) -> float:
    if text is None:
        return DEFAULT_WIND_SPEED
    value = _speed(text)
    if value is None or not 0.0 < value <= 60.0:
        raise ValueError("Wind speed %r: write metres per second, more than 0, for example wind 5 270." % text)
    return value


def _checked_direction(text: Optional[str]) -> float:
    if text is None:
        return DEFAULT_WIND_DIRECTION
    value = _direction(text)
    if value is None or not 0.0 <= value <= 360.0:
        raise ValueError(
            "Wind direction %r: write degrees 0-360 the wind comes from (270 = from the west), "
            "or N, NE, E, SE, S, SW, W, NW." % text
        )
    return value % 360.0


def _other_action(action: str, found: Dict[str, Any]) -> Command:
    allowed = ACTION_FIELDS[action]
    extra = [k for k in found if k not in allowed]
    if extra:
        takes = ", ".join(allowed) if allowed else "nothing else"
        raise ValueError(
            "%s takes %s; remove: %s." % (action, takes, ", ".join(k.replace("_", " ") for k in extra))
        )
    export_all = bool(found.pop("all", False))
    return Command(action, export_all=export_all, **_look_and_place(found))
