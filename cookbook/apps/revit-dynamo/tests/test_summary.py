"""The result and legend lines of ir_dynamo.summary (no network, no Revit)."""

from __future__ import annotations

import numpy as np

from ir_dynamo import summary
from ir_dynamo.colors import Bin, Legend


def _legend() -> Legend:
    ramp = np.linspace(0.0, 10.0, 11)
    bins = [Bin((0, 0, 255), 0.0, 4.0), Bin((255, 0, 0), 5.0, 10.0)]
    return Legend("wind-speed", bins, ramp, (ramp >= 5.0).astype(int), "registry")


def test_value_lines_give_count_min_max_and_the_sdk_range() -> None:
    result = {"values": [1.0, 2.0, 3.0, float("nan")], "legend_min": 1.0, "legend_max": 3.0}
    text = "\n".join(summary.value_lines(result, "ground", "m/s"))
    assert "4 value(s), 1 without a number" in text
    assert "min 1, max 3, mean 2, median 2" in text
    assert "legend_min .. legend_max (SDK): 1 .. 3" in text


def test_legend_lines_count_each_bin_and_the_values_outside() -> None:
    lines = summary.legend_count_lines(_legend(), [-1.0, 1.0, 2.0, 7.0, 12.0], "m/s", "trimmed")
    assert lines[0] == "Legend range used (trimmed): 0 .. 10 m/s"
    assert "1 value(s) below and 1 above" in lines[1]
    assert lines[2] == "  bin 01  rgb(0, 0, 255)  0 .. 4 m/s: 3 (60.0 %)"
    assert lines[3].endswith(": 2 (40.0 %)")


def test_selection_line_counts_categories_largest_first() -> None:
    line = summary.selection_line(
        "Selection", ["Walls, Wall", "Floors, Floor", "Walls, Wall", "Toposolid, Toposolid"], top=2
    )
    assert line == "Selection: 4 element(s): 2 Walls, 1 Floors, 1 more category"
    assert summary.selection_line("Terrain input", []) == "Terrain input: 0 element(s)"


def test_id_list_line_and_share_line() -> None:
    assert summary.id_list_line("x", []) == ""
    assert summary.id_list_line("are gone", ["a", "b"]) == "2 are gone (ids a, b)."
    line = summary.share_line("Triangles", {"Walls": 75, "Floors": 25, "Roofs": 0}, top=2)
    assert line == "Triangles: Walls 75 (75 %), Floors 25 (25 %), 1 more."
    assert summary.share_line("T", {}) == "T: none."
