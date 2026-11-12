"""The ``command`` node in ``ir_revit.entry._run``; the run itself is replaced."""

from __future__ import annotations

from typing import Any, List

import pytest

from ir_revit import entry

PREVIEW = "[ground] Preview only: 12 tokens. Add the word run to the command to run it."


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> List[Any]:
    seen: List[Any] = []

    def fake(cmd: Any, elements: Any) -> List[str]:
        seen.append((cmd, elements))
        return ["Location: here.", "[ground] Warning: no terrain.", PREVIEW]

    monkeypatch.setattr(entry, "_analysis", fake)
    # Not the user's real ~/.infrared log: a test run wrote a line there (2026-11-06).
    monkeypatch.setattr(entry, "LOG_FILE", str(tmp_path / "runs.log"))
    return seen


def test_the_command_is_the_only_input(calls: List[Any]) -> None:
    lines = entry.run(command="pwc")
    cmd, elements = calls[-1]
    assert cmd.analysis == "pwc lawson-lddc" and cmd.target == "ground" and not cmd.paid
    assert elements is None  # the selection of Revit is read later
    assert lines[0] == "Command: pwc lawson-lddc ground months 1-12 hours 0-23 preview"
    assert lines[-1] == "To run it (paid): pwc lawson-lddc ground months 1-12 hours 0-23 run"


def test_warnings_come_first(calls: List[Any]) -> None:
    lines = entry.run(command="svf")
    assert lines[1:4] == ["Warnings (1):", "  [ground] Warning: no terrain.", "---"]
    assert lines[4] == "Location: here."


def test_an_empty_command_gives_the_help(calls: List[Any]) -> None:
    lines = entry.run(command="  ")
    assert not calls
    assert lines[0].startswith("The command is empty") and any("Analysis:" in x for x in lines)


def test_a_bad_command_runs_nothing(calls: List[Any]) -> None:
    lines = entry.run(command="pwc wnd")
    assert not calls
    assert lines[0].startswith("Command error: Unknown word 'wnd'. Did you mean 'wind'?")


def test_help_runs_nothing(calls: List[Any]) -> None:
    assert entry.run(command="help")[0].startswith("Select the buildings in Revit")
    assert not calls


def test_an_old_graph_gets_a_line(calls: List[Any]) -> None:
    lines = entry.run(command="svf", elements=["wall"], target="both", months="6-8")
    assert calls[-1][1] == ["wall"]
    assert "older version" in lines[-1] and "months, target" in lines[-1]


def test_an_error_you_can_fix_is_a_line(monkeypatch: pytest.MonkeyPatch, calls: List[Any]) -> None:
    def fail(cmd: Any, elements: Any) -> List[str]:
        raise ValueError("Give both lat and lon, or neither.")

    monkeypatch.setattr(entry, "_analysis", fail)
    lines = entry.run(command="svf")
    assert lines[1:3] == ["Warnings (1):", "  Error: Give both lat and lon, or neither."]
