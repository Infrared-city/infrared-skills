"""The analyses a script offers, and the parsers for its text inputs.

One table (``ANALYSES``) holds a row for each analysis: its label, the SDK
analysis type, the unit, and where it can run (ground grid, facades).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

MONTHS = [m.lower() for m in calendar.month_abbr[1:]]
_RANGE = re.compile(r"\s*(?:-|\.\.|to)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Analysis:
    """One row of the analysis table.

    Attributes
    ----------
    key : str
        Short label the user types (``"svf"``).
    title : str
        Name for the status text.
    sdk_type : str
        The SDK ``analysis_type`` string.
    unit : str
        Unit of the values, as the public colour registry names it.
    ground, facades : bool
        Whether the analysis runs on the ground grid / on walls and roofs.
    needs_period : bool
        Whether it reads the months and hours input.
    needs_weather : bool
        Whether it reads a weather file (public station catalog).
    needs_wind : bool
        Whether it reads one wind speed and direction.
    no_terrain : bool
        A wind model: the SDK refuses terrain, each building is lowered to its base.
    variants : tuple of str
        The criteria (PWC) or subtypes (TCS) the user can add to the label,
        the default first. Empty for the other analyses.
    variant : str
        The chosen one (``find_analysis`` fills it in).
    whole_year : bool
        The analysis is normally read over a whole year (PWC).
    """

    key: str
    title: str
    sdk_type: str
    unit: str
    ground: bool
    facades: bool
    needs_period: bool = False
    needs_weather: bool = False
    needs_wind: bool = False
    no_terrain: bool = False
    variants: Tuple[str, ...] = ()
    variant: str = ""
    whole_year: bool = False

    @property
    def label(self) -> str:
        """The key and the variant, for example ``"pwc lawson-lddc"``."""
        return "%s %s" % (self.key, self.variant) if self.variant else self.key

    @property
    def full_title(self) -> str:
        """The title with the variant, for example ``"Pedestrian wind comfort (lawson-lddc)"``."""
        return "%s (%s)" % (self.title, self.variant) if self.variant else self.title


# The SDK PwcCriteria and TcsSubtype values; the default first.
PWC_CRITERIA = (
    "lawson-lddc", "lawson-2001", "lawson-1970", "davenport",
    "nen-8100-comfort", "nen-8100-safety", "vdi-3787",
)  # fmt: skip
TCS_SUBTYPES = ("thermal-comfort", "heat-stress", "cold-stress")
VARIANT_ALIASES = {
    "lddc": "lawson-lddc",
    "lawson": "lawson-lddc",
    "vdi": "vdi-3787",
    "nen": "nen-8100-comfort",
    "comfort": "thermal-comfort",
    "heat": "heat-stress",
    "cold": "cold-stress",
}

ANALYSES: Dict[str, Analysis] = {
    a.key: a
    for a in [
        Analysis("svf", "Sky view factor", "sky-view-factors", "%", True, True),
        Analysis(
            "solar",
            "Solar radiation",
            "solar-radiation",
            "kWh/m2",
            True,
            True,
            needs_period=True,
            needs_weather=True,
        ),
        Analysis(
            "sun-hours",
            "Direct sun hours",
            "direct-sun-hours",
            "h",
            True,
            True,
            needs_period=True,
        ),
        Analysis(
            "daylight",
            "Daylight availability",
            "daylight-availability",
            "%",
            False,
            True,
            needs_period=True,
        ),
        Analysis(
            "wind",
            "Wind speed",
            "wind-speed",
            "m/s",
            True,
            False,
            needs_wind=True,
            no_terrain=True,
        ),
        Analysis(
            "pwc",
            "Pedestrian wind comfort",
            "pedestrian-wind-comfort",
            "class",
            True,
            False,
            needs_period=True,
            needs_weather=True,
            no_terrain=True,
            variants=PWC_CRITERIA,
            whole_year=True,
        ),
        Analysis(
            "tcs",
            "Thermal comfort statistics",
            "thermal-comfort-statistics",
            "% of time",
            True,
            False,
            needs_period=True,
            needs_weather=True,
            variants=TCS_SUBTYPES,
        ),
        Analysis(
            "utci",
            "Thermal comfort (UTCI)",
            "thermal-comfort-index",
            "degC",
            True,
            False,
            needs_period=True,
            needs_weather=True,
        ),
    ]
}

ALIASES = {
    "sky view": "svf",
    "sky-view": "svf",
    "sky-view-factor": "svf",
    "sky-view-factors": "svf",
    "solar-radiation": "solar",
    "radiation": "solar",
    "sun": "sun-hours",
    "sunhours": "sun-hours",
    "sun hours": "sun-hours",
    "direct-sun-hours": "sun-hours",
    "daylight-availability": "daylight",
    "wind-speed": "wind",
    "thermal-comfort-index": "utci",
    "thermal-comfort": "utci",
    "pedestrian-wind-comfort": "pwc",
    "wind-comfort": "pwc",
    "wind comfort": "pwc",
    "thermal-comfort-statistics": "tcs",
    "comfort-statistics": "tcs",
}


def sdk_type_of_title(title: str) -> str:
    """The SDK analysis type of an analysis title (old saved results have a title only).

    Returns ``""`` when no row has that title.
    """
    return next((a.sdk_type for a in ANALYSES.values() if a.title == title), "")


def valid_labels(surface: str) -> List[str]:
    """The labels that run on ``surface`` (``"ground"`` or ``"facades"``)."""
    return [k for k, a in ANALYSES.items() if getattr(a, surface)]


def _split_variant(text: str) -> Tuple[str, str]:
    """``"pwc lawson-2001"`` -> ``("pwc", "lawson-2001")``; no known variant word -> ``(text, "")``."""
    words = text.split(" ")
    if len(words) < 2:
        return text, ""
    base = " ".join(words[:-1])
    row = ANALYSES.get(ALIASES.get(base, base))
    if row is None or not row.variants:
        return text, ""
    word = words[-1].replace("_", "-")
    word = VARIANT_ALIASES.get(word, word)
    if word not in row.variants:
        raise ValueError(
            "%s: %r is not known. Use one of: %s."
            % (row.title, words[-1], ", ".join(row.variants))
        )
    return base, word


def find_analysis(label: str, surface: str) -> Analysis:
    """Look up an analysis by label and check that it runs on ``surface``.

    Parameters
    ----------
    label : str
        The user's label, any case. Aliases are allowed (``"sun hours"``).
        PWC and TCS take a criterion or subtype as the last word
        (``"pwc lawson-2001"``, ``"tcs heat-stress"``); without it, the first
        of ``Analysis.variants``.
    surface : str
        ``"ground"`` or ``"facades"``.

    Returns
    -------
    Analysis
        The row, with ``variant`` filled in for PWC and TCS.

    Raises
    ------
    ValueError
        With the list of valid labels, when the label is unknown or the
        analysis does not run on that surface, or with the valid criteria
        or subtypes, when the last word is not one of them.
    """
    if surface not in ("ground", "facades"):
        raise ValueError("surface must be 'ground' or 'facades', not %r" % (surface,))
    key = re.sub(r"\s+", " ", str(label).strip().lower())
    key, variant = _split_variant(key)
    key = ALIASES.get(key, key)
    row = ANALYSES.get(key)
    if row is None or not getattr(row, surface):
        raise ValueError(
            "Analysis %r does not run on %s. Use one of: %s."
            % (label, surface, ", ".join(valid_labels(surface)))
        )
    if row.variants:
        row = replace(row, variant=variant or row.variants[0])
    return row


def window_note(row: Analysis, months: str, hours: str) -> List[str]:
    """A line when an analysis that is read over a whole year (PWC) gets a shorter window."""
    if not row.whole_year:
        return []
    period = parse_period(months, hours)
    whole = (period["start_month"], period["end_month"], period["start_hour"], period["end_hour"])
    if whole == (1, 12, 0, 23):
        return []
    return [
        "%s is normally read over a whole year. This run uses months %s and hours %s; "
        "set months to 1-12 and hours to 0-23 for the usual result." % (row.title, months, hours)
    ]


def _month(token: str) -> int:
    token = token.strip().lower()
    if token.isdigit():
        number = int(token)
    elif token[:3] in MONTHS:
        number = MONTHS.index(token[:3]) + 1
    else:
        raise ValueError("%r is not a month. Use 1-12 or Jan-Dec." % (token,))
    if not 1 <= number <= 12:
        raise ValueError("Month %d is not in 1-12." % number)
    return number


def parse_months(text: str) -> Tuple[int, int]:
    """Parse ``"6"``, ``"6-8"``, ``"Jun"``, ``"jun-aug"``, ``"Dec-Feb"``.

    Returns ``(start_month, end_month)``. ``Dec-Feb`` wraps over the year.
    """
    parts = [p for p in _RANGE.split(str(text).strip()) if p]
    if not parts or len(parts) > 2:
        raise ValueError(
            "Months %r: write one month or a range, like 6-8 or Jun-Aug." % (text,)
        )
    return _month(parts[0]), _month(parts[-1])


def parse_hours(text: str) -> Tuple[int, int]:
    """Parse ``"9-17"``, ``"9 - 17"`` or one hour ``"13"`` (= ``(13, 13)``).

    Returns ``(start_hour, end_hour)``, 0-23.
    """
    parts = [p for p in _RANGE.split(str(text).strip()) if p]
    if len(parts) not in (1, 2) or not all(p.isdigit() for p in parts):
        raise ValueError("Hours %r: write a range like 9-17, or one hour like 13." % (text,))
    start, end = int(parts[0]), int(parts[-1])
    if not (0 <= start <= 23 and 0 <= end <= 23) or start > end:
        raise ValueError("Hours %r: use 0-23 and start before end." % (text,))
    return start, end


def parse_period(months: str, hours: str) -> Dict[str, int]:
    """Months and hours text to the keyword arguments of ``TimePeriod``.

    The window starts on day 1 of the first month and ends on the last day of
    the last month.
    """
    start_month, end_month = parse_months(months)
    start_hour, end_hour = parse_hours(hours)
    last_day = calendar.monthrange(2023, end_month)[1]
    return {
        "start_month": start_month,
        "start_day": 1,
        "start_hour": start_hour,
        "end_month": end_month,
        "end_day": last_day,
        "end_hour": end_hour,
    }
