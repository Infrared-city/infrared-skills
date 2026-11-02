"""The coloured-triangle maths of ir_revit.result_mesh (no Revit needed)."""

from __future__ import annotations

import numpy as np

from ir_dynamo.colors import Legend
from ir_revit import result_mesh as rm


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
    ramp = np.linspace(0.0, 100.0, 101)
    legend = Legend("x", [], ramp, np.minimum(np.arange(101) // 10, 9), "registry")
    result = {
        "kind": "points",
        "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        "values": [0.0, 100.0],
        "cell_m": 1.0,
        "legend_min": 0.0,
        "legend_max": 100.0,
    }
    tri, bins = rm.coloured_triangles(result, legend)
    assert tri.shape == (4, 3, 3)
    assert bins.tolist() == [0, 0, 9, 9]
