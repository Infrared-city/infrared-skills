from __future__ import annotations

from types import SimpleNamespace

import pytest
from boxes import box_soup

from ir_dynamo import run

SOUPS = {"b1": box_soup(-10, -10, 0, 20, 20, 15)}


class FakeClient:
    """Stands in for InfraredClient: records calls, spends nothing."""

    def __init__(self) -> None:
        self.calls = []

    def preview_area(self, polygon, **kw):
        self.calls.append(("preview", kw["analysis_type"]))
        return SimpleNamespace(
            tile_count=1, would_bill_jobs=1, estimated_cost_tokens=10, sensor_count=None
        )

    def run_area_and_wait(self, *args, **kwargs):
        self.calls.append(("run",))
        raise AssertionError("a preview must not run")


def test_preview_only_never_runs() -> None:
    client = FakeClient()
    out = run.run_analysis("ground", "svf", SOUPS, 16.371, 48.208, client=client)
    assert out["ran"] is False and out["result"] is None
    assert out["tokens"] == 10
    assert "10 tokens" in out["cost"] and "Preview only" in out["status"]
    assert client.calls == [("preview", "sky-view-factors")]


def test_user_errors_are_value_errors() -> None:
    args = (SOUPS, 16.371, 48.208)
    with pytest.raises(ValueError):
        run.run_analysis("facades", "wind", *args, client=FakeClient())
    with pytest.raises(ValueError):
        run.run_analysis("ground", "sun-hours", *args, months="x", client=FakeClient())
    with pytest.raises(ValueError):
        run.run_analysis("ground", "svf", {}, 16.371, 48.208, client=FakeClient())


def test_payloads_for_every_analysis_that_needs_no_weather() -> None:
    client = FakeClient()
    cases = [
        ("ground", "sun-hours"),
        ("ground", "wind"),
        ("facades", "svf"),
        ("facades", "sun-hours"),
        ("facades", "daylight"),
    ]
    for surface, label in cases:
        out = run.run_analysis(surface, label, SOUPS, 16.371, 48.208, client=client)
        assert out["ran"] is False
