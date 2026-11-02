"""The analyses a script offers, and the parsers for its text inputs.

One table (``ANALYSES``) holds a row for each analysis: its label, the SDK
analysis type, the unit, and where it can run (ground grid, facades).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
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
            "wind", "Wind speed", "wind-speed", "m/s", True, False, needs_wind=True
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
}


def valid_labels(surface: str) -> List[str]:
    """The labels that run on ``surface`` (``"ground"`` or ``"facades"``)."""
    return [k for k, a in ANALYSES.items() if getattr(a, surface)]


def find_analysis(label: str, surface: str) -> Analysis:
    """Look up an analysis by label and check that it runs on ``surface``.

    Parameters
    ----------
    label : str
        The user's label, any case. Aliases are allowed (``"sun hours"``).
    surface : str
        ``"ground"`` or ``"facades"``.

    Raises
    ------
    ValueError
        With the list of valid labels, when the label is unknown or the
        analysis does not run on that surface.
    """
    if surface not in ("ground", "facades"):
        raise ValueError("surface must be 'ground' or 'facades', not %r" % (surface,))
    key = re.sub(r"\s+", " ", str(label).strip().lower())
    key = ALIASES.get(key, key)
    row = ANALYSES.get(key)
    if row is None or not getattr(row, surface):
        raise ValueError(
            "Analysis %r does not run on %s. Use one of: %s."
            % (label, surface, ", ".join(valid_labels(surface)))
        )
    return row


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
    """Parse ``"9-17"`` or ``"9 - 17"``. Returns ``(start_hour, end_hour)``, 0-23."""
    parts = [p for p in _RANGE.split(str(text).strip()) if p]
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("Hours %r: write a range like 9-17." % (text,))
    start, end = int(parts[0]), int(parts[1])
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
