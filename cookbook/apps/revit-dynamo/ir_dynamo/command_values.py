"""The number words of a command: wind speed and direction, coordinates, the margin."""

from __future__ import annotations

from typing import Optional

COMPASS = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}
DEFAULT_WIND_SPEED, DEFAULT_WIND_DIRECTION = 5.0, 270.0
MAX_MARGIN_M = 2000.0

EXAMPLES = {
    "months": "months 6-8 or months jun-aug",
    "hours": "hours 9-17",
    "legend": "legend exact (platform, trimmed or exact)",
    "surfaces": "surfaces roofs (facades, roofs or all)",
    "lat": "lat 48.2085",
    "lon": "lon 16.3721",
    "wind_speed": "speed 5",
    "margin": "margin 100 (metres around the selection)",
    "wind_direction": "direction 270 or direction W",
}


def num(x: float) -> str:
    return "%g" % x


def speed(word: str) -> Optional[float]:
    """``"5"``, ``"5.5"``, ``"5m/s"`` -> the number; anything else -> None."""
    word = word[:-3] if word.endswith("m/s") else word
    try:
        return float(word.replace(",", "."))
    except ValueError:
        return None


def direction(word: str) -> Optional[float]:
    """``"270"``, ``"270deg"``, ``"w"``, ``"nw"`` -> degrees (the wind comes from there)."""
    if word in COMPASS:
        return float(COMPASS[word])
    for tail in ("deg", "°"):
        word = word[: -len(tail)] if word.endswith(tail) else word
    try:
        return float(word)
    except ValueError:
        return None


def coordinate(text: str, name: str, limit: float) -> str:
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        raise ValueError("%s %r is not a number. Write it like %s." % (name, text, EXAMPLES[name]))
    if not -limit <= value <= limit:
        raise ValueError("%s %s is out of range (-%g to %g)." % (name, text, limit, limit))
    return num(value)


def checked_speed(text: Optional[str]) -> float:
    if text is None:
        return DEFAULT_WIND_SPEED
    value = speed(text)
    if value is None or not 0.0 < value <= 60.0:
        raise ValueError("Wind speed %r: write metres per second, more than 0, for example wind 5 270." % text)
    return value


def checked_direction(text: Optional[str]) -> float:
    if text is None:
        return DEFAULT_WIND_DIRECTION
    value = direction(text)
    if value is None or not 0.0 <= value <= 360.0:
        raise ValueError(
            "Wind direction %r: write degrees 0-360 the wind comes from (270 = from the west), "
            "or N, NE, E, SE, S, SW, W, NW." % text
        )
    return value % 360.0


def checked_margin(text: Optional[str]) -> str:
    """``"100"`` or ``"100m"`` -> ``"100"``; empty for no word."""
    if text is None:
        return ""
    word = text[:-1] if text.endswith("m") else text
    try:
        value = float(word.replace(",", "."))
    except ValueError:
        value = -1.0
    if not 0.0 <= value <= MAX_MARGIN_M:
        raise ValueError(
            "margin %r: write metres around the selection, 0 to %g, for example margin 100."
            % (text, MAX_MARGIN_M)
        )
    return num(value)
