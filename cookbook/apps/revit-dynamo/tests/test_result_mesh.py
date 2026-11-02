"""The coloured-triangle maths of ir_revit.result_mesh (no Revit needed)."""

from __future__ import annotations

import numpy as np

from ir_revit import result_mesh as rm


def test_bins_cover_the_range_and_clip_outside_values() -> None:
    values = np.array([-5.0, 0.0, 9.99, 10.0, 50.0, 100.0, 200.0])
    assert rm.bin_index(values, 0.0, 100.0).tolist() == [0, 0, 0, 1, 5, 9, 9]


def test_flat_range_goes_to_the_first_bin() -> None:
    assert rm.bin_index(np.array([3.0, 3.0]), 3.0, 3.0).tolist() == [0, 0]


def test_bin_colors_run_from_the_first_to_the_last_stop() -> None:
    colors = rm.bin_colors()
    assert len(colors) == rm.BINS
    assert colors[0] == rm.GRADIENT[0] and colors[-1] == rm.GRADIENT[-1]


def test_ground_cell_becomes_two_triangles_covering_the_cell() -> None:
    tri = rm.ground_triangles([[10.0, 20.0, 0.0]], cell_m=2.0)
    assert tri.shape == (2, 3, 3)
    assert tri[:, :, 0].min() == 9.0 and tri[:, :, 0].max() == 11.0
    assert tri[:, :, 1].min() == 19.0 and tri[:, :, 1].max() == 21.0
    assert np.allclose(tri[:, :, 2], rm.GROUND_LIFT_M)


def test_facade_triangles_move_away_from_the_centre() -> None:
    # Two walls of a 10 m box, facing +x and -x, both wound "inward".
    east = [10, 0, 0, 10, 0, 5, 10, 5, 0]
    west = [0, 0, 0, 0, 5, 0, 0, 0, 5]
    moved = rm.facade_triangles(east + west)
    assert np.allclose(moved[0, :, 0], 10.0 + rm.FACADE_OFFSET_M)
    assert np.allclose(moved[1, :, 0], -rm.FACADE_OFFSET_M)


def test_coloured_triangles_repeat_the_ground_bin_per_cell() -> None:
    result = {
        "kind": "points",
        "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        "values": [0.0, 100.0],
        "cell_m": 1.0,
        "legend_min": 0.0,
        "legend_max": 100.0,
    }
    tri, bins = rm.coloured_triangles(result)
    assert tri.shape == (4, 3, 3)
    assert bins.tolist() == [0, 0, 9, 9]
