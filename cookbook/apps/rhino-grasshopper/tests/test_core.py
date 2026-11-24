"""The site maths and the lines of a preview, without Rhino and without the API."""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pytest
from boxes import box_soup

from ir_dynamo import command
from ir_rhino import core
from ir_rhino.site import Site, model_to_site_m, north_rad, site_m_to_model


def test_north_on_plus_y_is_no_turn_and_east_is_a_quarter() -> None:
    assert north_rad(0.0, 1.0) == pytest.approx(0.0)
    # True north along the model +x: the model turns a quarter counter-clockwise.
    assert north_rad(1.0, 0.0) == pytest.approx(math.pi / 2)
    assert north_rad(0.0, 0.0) == 0.0


def test_model_and_site_frames_go_both_ways() -> None:
    # A model in millimetres, the EarthAnchorPoint at (1000, 2000, 0), true north along +x.
    site = Site(16.37, 48.2, north_rad(1.0, 0.0), (1000.0, 2000.0, 0.0), 0.001, "rhino")
    model = [1000.0 + 5000.0, 2000.0, 3000.0]  # 5 m along the model +x, which is north
    out = model_to_site_m(model, site)
    assert out == pytest.approx([0.0, 5.0, 3.0])
    assert site_m_to_model(out, site) == pytest.approx(model)


def _fake_run(seen: List[Dict[str, Any]]) -> Any:
    def run(surface: str, analysis: str, buildings: Any, lon: float, lat: float, **kw: Any) -> Dict[str, Any]:
        seen.append({"surface": surface, "analysis": analysis, "lon": lon, **kw})
        return {
            "status": "Preview only: 1 tile(s), 1 job(s), about 10 tokens. Add the word run to the command to run it.",
            "warnings": ["Area: 80 x 80 m (the selection and a margin of 30 m)."],
            "cost": "1 tile(s)",
            "tokens": 10,
            "ran": False,
        }

    return run


def test_a_preview_gives_the_revit_lines() -> None:
    seen: List[Dict[str, Any]] = []
    cmd = command.parse("svf both")
    site = Site(16.37, 48.2)
    own = {"b1": box_soup(-10, -10, 0, 20, 20, 15)}
    lines, outs = core.analyse(cmd, own, site, run=_fake_run(seen))
    assert [s["surface"] for s in seen] == ["ground", "facades"]
    assert all(s["preview_only"] for s in seen) and seen[0]["lon"] == 16.37
    assert lines[0].startswith("Location: lon 16.37000, lat 48.20000 (rhino)")
    assert any(line.startswith("Preview of both targets:") for line in lines)
    out = core.finish(cmd, lines)
    assert out[0] == "Command: svf both preview"
    assert out[-1] == "To run it (paid): svf both run"


def test_an_error_on_one_target_is_a_line() -> None:
    def fail(*args: Any, **kw: Any) -> Dict[str, Any]:
        raise ValueError("No building has a usable triangle above the ground.")

    cmd = command.parse("svf run")
    lines, outs = core.analyse(cmd, {"b": box_soup(0, 0, -20, 1, 1, 1)}, Site(16.37, 48.2), run=fail)
    assert outs == {} and lines[-1] == "Error on ground: No building has a usable triangle above the ground."
    assert np.isfinite(len(lines))


def test_margin_is_not_set_in_rhino() -> None:
    seen: List[Dict[str, Any]] = []
    cmd = command.parse("svf margin 50")
    lines, outs = core.analyse(cmd, {"b1": box_soup(-10, -10, 0, 20, 20, 15)}, Site(16.37, 48.2), run=_fake_run(seen))
    assert "buffer_m" not in seen[0]
    assert "Warning: margin is not in the Rhino version; the default area is used." in lines


def test_trees_and_ground_go_to_every_target() -> None:
    seen: List[Dict[str, Any]] = []
    trees = [(1.0, 2.0, None, None)]
    ground = {"water": [[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]]}
    core.analyse(command.parse("svf both"), {"b1": box_soup(-10, -10, 0, 20, 20, 15)}, Site(16.37, 48.2),
                 trees_m=trees, ground_m=ground, run=_fake_run(seen))
    assert [s["trees_m"] for s in seen] == [trees, trees]
    assert all(s["ground_m"] == ground for s in seen)


def test_without_a_legend_word_the_range_is_the_sdk_default() -> None:
    from ir_rhino import shapes

    assert shapes.with_look(command.parse("utci run"), "utci run").legend == "exact"
    assert shapes.with_look(command.parse("utci legend platform"), "utci legend platform").legend == "platform"
    assert shapes.with_look(command.parse("utci trimmed"), "utci trimmed").legend == "trimmed"
    # A new legend or gradient keeps the same result: no new run.
    a = shapes.with_look(command.parse("utci run"), "utci run")
    b = shapes.with_look(command.parse("utci gradient legend trimmed run"), "utci gradient legend trimmed run")
    assert shapes.without_look(a) == shapes.without_look(b) and a != b
    assert shapes.without_look(a) != shapes.without_look(command.parse("utci months jul run"))
