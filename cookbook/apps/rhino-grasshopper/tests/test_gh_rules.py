"""When the Grasshopper component pays: only when the command text changes to a run."""

from __future__ import annotations

from ir_rhino.gh import decide


def test_a_preview_is_free_and_runs_on_every_change() -> None:
    assert decide(None, "svf", paid=False, running=False) == "preview"
    assert decide("svf", "svf", paid=False, running=False) == "preview"


def test_a_file_opened_with_run_does_not_pay() -> None:
    assert decide(None, "svf run", paid=True, running=False) == "blocked"


def test_typing_run_pays_once() -> None:
    assert decide("svf", "svf run", paid=True, running=False) == "run"
    # The next solves (a slider, new geometry) keep the text: the kept result is shown.
    assert decide("svf run", "svf run", paid=True, running=False) == "show"


def test_nothing_starts_while_a_run_is_going() -> None:
    assert decide("svf", "wind run", paid=True, running=True) == "wait"
    assert decide("svf run", "svf", paid=False, running=True) == "wait"
