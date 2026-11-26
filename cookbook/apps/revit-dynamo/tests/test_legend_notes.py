"""The line that says when the platform scale shows a result in one colour."""

from __future__ import annotations

import numpy as np
from test_colors import VC

from ir_dynamo import colors, legend_notes

# The tester's UTCI run (2026-11-24): 20.9 .. 27.7 degC on the fixed -40 .. 46 scale.
SUMMER = np.linspace(20.9, 27.7, 2000)


def _notes(warnings):
    return [w for w in warnings if "in one colour of the platform scale" in w]


def test_utci_in_one_platform_colour_gets_a_line(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: (-40.0, 46.0))
    _, warnings = colors.make_legend("thermal-comfort-index", 20.9, 27.7, VC, SUMMER, "platform")
    note = _notes(warnings)
    assert len(note) == 1
    assert note[0].startswith("Warning: 93 % of the values (20.9 .. 27.7)")
    assert "scale (-40 .. 46)" in note[0] and "show-last legend trimmed" in note[0]


def test_no_line_in_a_measured_range_or_when_the_colours_spread(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: (-40.0, 46.0))
    _, warnings = colors.make_legend("thermal-comfort-index", 20.9, 27.7, VC, SUMMER, "trimmed")
    assert not _notes(warnings)
    wide = np.linspace(-30.0, 40.0, 2000)  # a year: every colour has its share
    _, warnings = colors.make_legend("thermal-comfort-index", -30.0, 40.0, VC, wide, "platform")
    assert not _notes(warnings)


def test_no_line_without_a_fixed_range() -> None:
    legend, _ = colors.make_legend("sky-view-factors", 0.0, 100.0, VC, np.full(100, 99.0), "exact")
    assert legend_notes.one_colour_note(legend, np.full(100, 99.0), None) == []
    assert legend_notes.one_colour_note(legend, [np.nan], (0.0, 100.0)) == []
