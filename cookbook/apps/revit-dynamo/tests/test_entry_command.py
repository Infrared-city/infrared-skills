"""The ``command`` node in ``ir_revit.entry._run``; the run itself is replaced."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ir_revit import entry

PREVIEW = "[ground] Preview only: 12 tokens. Set preview_only to False to run."
NODES = dict(
    target="both", elements=["wall"], analysis="svf", months="6-8", hours="8-18",
    preview_only=False, fetch_context=False, lat="", lon="", set_api_key=False,
    wind_speed=5.0, wind_direction=270.0, surfaces="all", legend="platform", gradient=False,
)  # fmt: skip


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> List[Dict[str, Any]]:
    seen: List[Dict[str, Any]] = []

    def fake(*args: Any, **kwargs: Any) -> List[str]:
        seen.append(dict(zip(entry._INPUT_NAMES, args), **kwargs))
        return [PREVIEW]

    monkeypatch.setattr(entry, "_run_inputs", fake)
    # Not the user's real ~/.infrared log: a test run wrote a line there (2026-11-06).
    monkeypatch.setattr(entry, "LOG_FILE", str(tmp_path / "runs.log"))
    return seen


def test_the_command_replaces_the_input_nodes(calls: List[Dict[str, Any]]) -> None:
    lines = entry._run(command="pwc", **NODES)
    run = calls[-1]
    assert run["analysis"] == "pwc lawson-lddc" and run["target"] == "ground"
    assert run["preview_only"] is True  # the node said False; the command has no "run"
    assert run["elements"] == ["wall"]
    assert lines[0] == "Command: pwc lawson-lddc ground months 1-12 hours 0-23 preview"
    assert "Add the word run" in lines[2]
    assert lines[-1] == "To run it (paid): pwc lawson-lddc ground months 1-12 hours 0-23 run"


def test_empty_command_uses_the_nodes_and_shows_their_command(calls: List[Dict[str, Any]]) -> None:
    lines = entry._run(command="  ", **NODES)
    assert calls[-1]["analysis"] == "svf" and calls[-1]["preview_only"] is False
    assert lines == [PREVIEW, "Same as the command: svf both run"]


def test_positional_nodes_still_work(calls: List[Dict[str, Any]]) -> None:
    lines = entry._run("ground", ["wall"], "wind", "6-8", "8-18", True, False, "", "", False, 20, 270)
    assert calls[-1]["wind_speed"] == 20
    assert lines[-1] == "Same as the command: wind 20 270 ground preview"


def test_a_bad_command_runs_nothing(calls: List[Dict[str, Any]]) -> None:
    lines = entry._run(command="pwc wnd", **NODES)
    assert not calls
    assert lines[0].startswith("Command error: Unknown word 'wnd'. Did you mean 'wind'?")


def test_help_runs_nothing(calls: List[Dict[str, Any]]) -> None:
    assert entry._run(command="help", **NODES)[0].startswith("Command words")
    assert not calls
