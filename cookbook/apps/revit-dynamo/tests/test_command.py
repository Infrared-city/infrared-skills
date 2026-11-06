from __future__ import annotations

import pytest

from ir_dynamo import command as c
from ir_dynamo import command_help as h


def test_one_word_is_a_free_preview_with_the_defaults() -> None:
    cmd = c.parse("svf")
    assert cmd.action == "analysis" and cmd.analysis == "svf" and cmd.target == "ground"
    assert not cmd.paid and cmd.inputs()["preview_only"] is True
    assert cmd.text == "svf ground preview"


def test_pwc_fills_in_the_criterion_and_the_whole_year() -> None:
    cmd = c.parse("PWC")
    assert cmd.text == "pwc lawson-lddc ground months 1-12 hours 0-23 preview"
    assert c.parse("pwc lawson-2001 run").analysis == "pwc lawson-2001"
    assert c.parse("tcs heat").analysis == "tcs heat-stress"


def test_wind_takes_speed_and_direction() -> None:
    cmd = c.parse("wind 20 270")
    assert (cmd.wind_speed, cmd.wind_direction) == (20.0, 270.0)
    assert c.parse("wind 5 nw").wind_direction == 315.0
    assert c.parse("speed 4 direction e wind").wind_direction == 90.0
    assert c.parse("wind 3m/s").wind_speed == 3.0
    assert c.parse("wind").text == "wind 5 270 ground preview"


def test_daylight_runs_on_the_ground_by_default() -> None:
    assert c.parse("daylight").target == "ground"
    assert c.parse("daylight facades").text == "daylight facades months 6-8 hours 8-18 preview"


def test_any_order_and_every_value() -> None:
    cmd = c.parse("run, context legend exact gradient months jun-aug hours 12-15 ground UTCI")
    assert cmd.paid and cmd.fetch_context and cmd.gradient and cmd.legend == "exact"
    assert (cmd.months, cmd.hours) == ("jun-aug", "12-15")
    cmd = c.parse("solar facades surfaces roofs lat 48.2085 lon 16.3721")
    assert cmd.surfaces == "roofs" and (cmd.lat, cmd.lon) == ("48.2085", "16.3721")


@pytest.mark.parametrize(
    "line",
    [
        "pwc",
        "wind 7 90 context run",
        "utci both months 6-8 hours 12-15 legend trimmed gradient",
        "solar facades surfaces roofs lat 48.2 lon 16.37 run",
        "tcs cold-stress",
        "show-last legend exact gradient",
        "export-obj all lat 1 lon 2",
        "set-key",
    ],
)
def test_text_reads_back_to_the_same_command(line: str) -> None:
    cmd = c.parse(line)
    assert c.parse(cmd.text) == cmd


def test_other_actions() -> None:
    assert c.parse("show-last").inputs()["analysis"] == "show-last"
    assert c.parse("last exact").legend == "exact"
    assert c.parse("export").inputs()["analysis"] == "export-obj"
    assert c.parse("export-obj all").inputs()["analysis"] == "export-obj all"
    assert c.parse("set-key").inputs()["set_api_key"] is True
    assert c.parse("pwc help").action == "help"


@pytest.mark.parametrize(
    "line,message",
    [
        ("", "empty"),
        ("facdes svf", "Did you mean 'facades'"),
        ("months 6-8", "Say what to run"),
        ("svf solar", "given twice"),
        ("show-last svf", "cannot run together"),
        ("show-last months 6-8", "show-last takes legend, gradient"),
        ("pwc wind 5 270", "wind analysis only"),
        ("wind facades", "does not run on facades"),
        ("svf surfaces roofs", "facades only"),
        ("svf lat 48", "both lat and lon"),
        ("svf months 13", "not in 1-12"),
        ("svf hours 18-8", "start before end"),
        ("wind 0", "more than 0"),
        ("speed 5 direction xyz wind", "degrees 0-360"),
        ("svf all", "both"),
        ("svf lawson-2001", "not used by"),
        ("pwc heat-stress", "not known"),
        ("svf months", "needs a value"),
        ("svf run preview", "given twice"),
    ],
)
def test_errors_say_what_to_write(line: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        c.parse(line)


def _nodes(**over: object) -> dict:
    base = dict(
        target="both", analysis="svf", months="6-8", hours="8-18", preview_only=True,
        fetch_context=False, lat="", lon="", set_api_key=False, wind_speed=5.0,
        wind_direction=270.0, surfaces="all", legend="platform", gradient=False,
    )  # fmt: skip
    base.update(over)
    return base


def test_the_input_nodes_give_their_command() -> None:
    assert h.from_inputs(**_nodes()) == "svf both preview"
    assert h.from_inputs(**_nodes(analysis="Sun Hours", target="all", preview_only=False)) == (
        "sun-hours both months 6-8 hours 8-18 run"
    )
    assert h.from_inputs(**_nodes(analysis="wind", target="ground", wind_speed=20.0)) == (
        "wind 20 270 ground preview"
    )
    assert h.from_inputs(**_nodes(analysis="show-last", legend="exact")) == "show-last legend exact"
    assert h.from_inputs(**_nodes(analysis="export-obj all")) == "export-obj all"
    assert h.from_inputs(**_nodes(set_api_key=True)) == "set-key"


def test_the_command_of_the_nodes_does_what_the_nodes_do() -> None:
    nodes = _nodes(analysis="pwc", target="ground", months="1-12", hours="0-23", legend="trimmed")
    inputs = c.parse(h.from_inputs(**nodes)).inputs()
    assert inputs["analysis"] == "pwc lawson-lddc" and inputs["legend"] == "trimmed"
    assert (inputs["months"], inputs["hours"], inputs["preview_only"]) == ("1-12", "0-23", True)


def test_bad_input_nodes_give_no_command() -> None:
    assert h.from_inputs(**_nodes(analysis="nope")) is None


def test_help_names_every_analysis() -> None:
    text = "\n".join(h.help_lines())
    for key in ("svf", "solar", "sun-hours", "daylight", "wind", "pwc", "tcs", "utci", "lawson-lddc"):
        assert key in text
