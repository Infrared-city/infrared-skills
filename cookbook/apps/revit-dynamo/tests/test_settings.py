from __future__ import annotations

import pytest
from ir_dynamo import settings as s


def test_find_analysis_aliases_and_case() -> None:
    assert s.find_analysis(" Sun Hours ", "ground").key == "sun-hours"
    assert s.find_analysis("SVF", "facades").sdk_type == "sky-view-factors"
    assert s.find_analysis("daylight", "facades").sdk_type == "daylight-availability"


def test_surface_rules() -> None:
    with pytest.raises(ValueError, match="does not run on facades"):
        s.find_analysis("wind", "facades")
    with pytest.raises(ValueError, match="does not run on ground"):
        s.find_analysis("daylight", "ground")
    with pytest.raises(ValueError, match="Use one of"):
        s.find_analysis("nope", "ground")
    with pytest.raises(ValueError, match="surface must be"):
        s.find_analysis("svf", "roof")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("6", (6, 6)),
        ("6-8", (6, 8)),
        ("Jun", (6, 6)),
        ("jun-aug", (6, 8)),
        ("Dec-Feb", (12, 2)),
        ("6..8", (6, 8)),
        (" 6 - 8 ", (6, 8)),
        ("june to august", (6, 8)),
    ],
)
def test_months(text: str, expected: tuple) -> None:
    assert s.parse_months(text) == expected


@pytest.mark.parametrize("text", ["", "13", "foo", "1-2-3", "0"])
def test_bad_months(text: str) -> None:
    with pytest.raises(ValueError):
        s.parse_months(text)


def test_hours() -> None:
    assert s.parse_hours("9 - 17") == (9, 17)
    for bad in ["9", "17-9", "9-24", "a-b"]:
        with pytest.raises(ValueError):
            s.parse_hours(bad)


def test_period_uses_the_last_day_of_the_month() -> None:
    p = s.parse_period("2", "8-18")
    assert p == {
        "start_month": 2,
        "start_day": 1,
        "start_hour": 8,
        "end_month": 2,
        "end_day": 28,
        "end_hour": 18,
    }
    assert s.parse_period("Jun-Aug", "9-17")["end_day"] == 31
