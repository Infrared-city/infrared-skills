"""ir_dynamo.cell_colors: each cell takes the colour the SDK renderer gives it.

No network: the registry config is passed as ``visual_configurations``.
"""

from __future__ import annotations

import numpy as np
import pytest
from infrared_sdk.layers.image_local import render_grid_image_local

from ir_dynamo import cell_colors as cc
from ir_dynamo import colors

WIND = [[0, 0, 143], [0, 60, 255], [0, 175, 255], [0, 255, 220], [60, 255, 135],
        [143, 255, 50], [235, 255, 50], [255, 170, 0], [255, 60, 0], [175, 0, 0]]
VC = {
    "wind-speed": {"colors": WIND, "steps": [0, 20], "colorInterpolation": "binned",
                   "legendType": "equal_ranges", "resultSubdivisionFactor": 5,
                   "barsSubdivisionFactor": 1, "legendSubdivisionFactor": 1,
                   "legendMaxHandling": "open", "legendMinHandling": "closed"},
    "solar-radiation": {"colors": [[75, 107, 169], [170, 200, 247], [245, 239, 103],
                                   [239, 156, 21], [234, 38, 0]],
                        "colorInterpolation": "binned", "legendType": "equal_ranges",
                        "resultSubdivisionFactor": 3, "barsSubdivisionFactor": 2,
                        "legendSubdivisionFactor": 2, "legendMaxHandling": "closed",
                        "legendMinHandling": "closed"},
}


@pytest.fixture(autouse=True)
def _wind_is_fixed(monkeypatch) -> None:
    fixed = {"wind-speed": (0.0, 20.0)}
    monkeypatch.setattr(colors, "registry_fixed_range", lambda a, v=None: fixed.get(a))


def _colours(analysis, values, mode, **kw):
    legend, _ = colors.make_legend(analysis, None, None, VC, values, mode)
    palette, index, notes = cc.cell_colors(
        analysis, values, float(np.min(values)), float(np.max(values)), mode, legend,
        visual_configurations=VC, **kw
    )
    assert notes == []
    return np.asarray(palette)[index]


def test_a_cell_gets_the_pixel_the_sdk_draws_for_the_matrix() -> None:
    grid = np.random.default_rng(3).random((7, 11)) * 400.0
    grid[2, 3] = np.nan
    row, col = np.nonzero(np.isfinite(grid))
    rgb = _colours("solar-radiation", grid[row, col], "exact", grid_shape=grid.shape,
                   cells=np.c_[row, col])
    sdk = colors.decode_png(render_grid_image_local(
        grid=[[None if np.isnan(x) else x for x in r] for r in grid.tolist()],
        analysis_type="solar-radiation", visual_configurations=VC, max_long_axis_px=0))
    assert np.array_equal(rgb, sdk[row, col, :3])  # row 0 = top image row = grid row 0


def test_the_layout_does_not_change_a_colour() -> None:
    grid = np.linspace(0.0, 400.0, 6 * 9).reshape(6, 9)
    row, col = np.nonzero(np.isfinite(grid))
    in_matrix = _colours("solar-radiation", grid[row, col], "exact", grid_shape=grid.shape,
                         cells=np.c_[row, col])
    in_square = _colours("solar-radiation", grid[row, col], "exact")
    assert np.array_equal(in_matrix, in_square)


def test_platform_wind_is_blue_and_trimmed_wind_uses_the_whole_scale() -> None:
    values = np.concatenate([np.linspace(3.0, 6.0, 500), [0.0, 9.0]])
    platform = {tuple(c) for c in _colours("wind-speed", values, "platform")}
    assert platform <= {tuple(c) for c in WIND[:5]}  # 0..20 m/s: only the low colours
    trimmed = {tuple(c) for c in _colours("wind-speed", values, "trimmed")}
    assert trimmed == {tuple(c) for c in WIND}


def test_offline_falls_back_to_the_legend_colours() -> None:
    legend = colors.fallback_legend("x", 0.0, 1.0)
    palette, index, notes = cc.cell_colors("no-such", [0.0, 1.0], 0.0, 1.0, "exact", legend,
                                           visual_configurations=VC)
    assert len(palette) == 2 and index.tolist() == [0, 1] and "not used" in notes[0]
