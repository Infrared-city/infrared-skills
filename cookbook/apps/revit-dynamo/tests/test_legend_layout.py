"""ir_dynamo.legend_layout: the swatches and texts of the Revit legend view."""

from __future__ import annotations

import numpy as np

from ir_dynamo import legend_layout as ll
from ir_dynamo.colors import Bin, Legend


def _legend() -> Legend:
    bins = [Bin((0, 0, 143), 0.0, 2.0), Bin((60, 255, 135), 2.0, 4.0), Bin((175, 0, 0), 4.0, 6.0)]
    return Legend("wind-speed", bins, np.linspace(0, 6, 7), np.array([0, 0, 0, 1, 1, 2, 2]), "registry")


def test_highest_value_is_on_top_and_each_bin_has_a_swatch_and_a_range() -> None:
    swatches, texts = ll.legend_layout(_legend(), "Wind speed", "m/s", "ground", ["note"])
    assert texts[0].text == "Wind speed (m/s), ground"
    assert [s.rgb for s in swatches] == [(175, 0, 0), (60, 255, 135), (0, 0, 143)]
    assert [t.text for t in texts[1:4]] == ["4 to 6 m/s", "2 to 4 m/s", "0 to 2 m/s"]
    assert swatches[0].y > swatches[1].y > swatches[2].y  # top to bottom
    assert texts[-1].text == "note" and texts[-1].y < swatches[-1].y


def test_rows_do_not_overlap() -> None:
    swatches, _ = ll.legend_layout(_legend(), "t", "u", "ground")
    for upper, lower in zip(swatches, swatches[1:]):
        assert lower.y + lower.h <= upper.y


def test_range_texts_round_the_sampled_edges() -> None:
    # Bins from sampled colours: each ends a little before the next one starts.
    bins = [Bin((0, 0, 143), 0.0, 1.996), Bin((0, 60, 255), 2.035, 3.992), Bin((0, 175, 255), 4.031, 6.0)]
    assert ll.range_texts(bins, "m/s") == ["0 to 2 m/s", "2 to 4 m/s", "4 to 6 m/s"]
    svf = [Bin((0, 0, 0), 0.0, 0.098), Bin((1, 1, 1), 0.102, 0.2)]
    assert ll.range_texts(svf, "") == ["0 to 0.1", "0.1 to 0.2"]
    solar = [Bin((0, 0, 0), 0.0002, 34.81), Bin((1, 1, 1), 35.49, 69.61)]
    assert ll.range_texts(solar, "kWh/m2") == ["0 to 35 kWh/m2", "35 to 70 kWh/m2"]
