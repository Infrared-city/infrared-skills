from __future__ import annotations

import pytest

from ir_dynamo import command as c
from ir_dynamo import command_help as h


def test_one_word_is_a_free_preview_with_the_defaults() -> None:
    cmd = c.parse("svf")
    assert cmd.action == "analysis" and cmd.analysis == "svf" and cmd.target == "ground"
    assert not cmd.paid
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
        "clear",
    ],
)
def test_text_reads_back_to_the_same_command(line: str) -> None:
    cmd = c.parse(line)
    assert c.parse(cmd.text) == cmd


def test_other_actions() -> None:
    assert c.parse("show-last").action == "show-last"
    assert c.parse("last exact").legend == "exact"
    assert c.parse("export").action == "export-obj" and not c.parse("export").export_all
    assert c.parse("export-obj all").export_all
    assert c.parse("set-key").action == "set-key"
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


def test_scope_and_margin() -> None:
    cmd = c.parse("daylight facades model margin 100m run")
    assert (cmd.scope, cmd.margin, cmd.paid) == ("model", "100", True)
    assert cmd.text == "daylight facades months 6-8 hours 8-18 model margin 100 run"
    assert c.parse(cmd.text) == cmd
    assert c.parse("svf alone").scope == "alone" and c.parse("svf").scope == ""
    assert c.parse("export-obj model").scope == "model"


def test_keep_is_read_and_not_used_and_clear_is_an_action() -> None:
    # Every result stays now. A command with the old word keep must still run.
    assert c.parse("daylight facades keep run") == c.parse("daylight facades run")
    assert c.parse("show-last keep").text == "show-last"
    assert c.parse("clear").action == "clear" and c.parse("clear").text == "clear"
    with pytest.raises(ValueError, match="clear takes nothing else"):
        c.parse("clear ground")
    with pytest.raises(ValueError, match="cannot run together"):
        c.parse("clear svf")


@pytest.mark.parametrize(
    "line, message",
    [
        ("svf model alone", "given twice"),
        ("svf margin", "needs a value"),
        ("svf margin 5000", "0 to 2000"),
        ("export-obj alone", "takes model, not alone"),
        ("show-last model", "show-last takes legend, gradient; remove"),
    ],
)
def test_scope_and_margin_errors(line: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        c.parse(line)


def test_help_names_every_analysis() -> None:
    text = "\n".join(h.help_lines())
    for key in ("svf", "solar", "sun-hours", "daylight", "wind", "pwc", "tcs", "utci", "lawson-lddc"):
        assert key in text


def test_select_picks_in_revit() -> None:
    assert c.parse("select").action == "select" and c.parse("select").scope == ""
    assert c.parse("select link").scope == "link" and c.parse("pick linked").text == "select link"
    with pytest.raises(ValueError, match="select takes link, not model"):
        c.parse("select model")
    with pytest.raises(ValueError, match="link goes with select"):
        c.parse("svf link")
    with pytest.raises(ValueError, match="cannot run together"):
        c.parse("select svf")
