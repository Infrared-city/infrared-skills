"""The coloured-triangle maths of ir_revit.result_mesh (no Revit needed)."""

from __future__ import annotations

import numpy as np

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


def test_coloured_triangles_repeat_the_ground_colour_per_cell() -> None:
    result = {
        "kind": "points",
        "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        "values": [0.0, 100.0],
        "cell_m": 1.0,
        "legend_min": 0.0,
        "legend_max": 100.0,
    }
    tri, bins = rm.coloured_triangles(result, [0, 9])
    assert tri.shape == (4, 3, 3)
    assert bins.tolist() == [0, 0, 9, 9]


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def test_cells_of_one_colour_join_into_regions_without_holes() -> None:
    # A 3 x 3 block of colour 0 with colour 1 in the middle, 2 m cells.
    points = [[2.0 * i + 1.0, 2.0 * j + 1.0, 0.0] for j in range(3) for i in range(3)]
    colour = [1 if (i, j) == (1, 1) else 0 for j in range(3) for i in range(3)]
    regions = rm.ground_regions(points, 2.0, colour)
    assert sorted(k for k, _ in regions) == [0, 0, 1]
    assert all(len(loops) == 1 for _, loops in regions)  # one ring per face, no holes
    ring = [loops[0] for k, loops in regions if k == 0]
    assert len(ring) == 2  # the ring around the hole is cut into two pieces
    assert all(_signed_area(r) > 0 for r in ring)  # anticlockwise: face normal up
    assert sum(_signed_area(r) for r in ring) == 32.0  # 36 m2 less the 4 m2 hole
    (centre,) = [loops[0] for k, loops in regions if k == 1]
    assert len(centre) == 4  # no corners on the straight edges
    assert sorted(map(tuple, centre[:, :2].tolist())) == [(2.0, 2.0), (2.0, 4.0), (4.0, 2.0), (4.0, 4.0)]
    assert np.allclose(ring[0][:, 2], rm.GROUND_LIFT_M)


def test_regions_only_on_a_flat_ground() -> None:
    assert rm.ground_regions([[0.0, 0.0, 0.0], [1.0, 0.0, 0.5]], 1.0, [0, 0]) is None
    result = {"kind": "points", "points": [[0.0, 0.0, 0.0]], "cell_m": 1.0, "corner_z": [[0, 0, 0, 0]]}
    assert rm.coloured_regions(result, [0]) is None
    assert rm.coloured_regions({"kind": "triangles"}, [0]) is None


def test_cells_that_touch_at_a_corner_are_two_regions() -> None:
    regions = rm.ground_regions([[0.5, 0.5, 0.0], [1.5, 1.5, 0.0]], 1.0, [0, 0])
    assert len(regions) == 2 and all(len(loops) == 1 and len(loops[0]) == 4 for _, loops in regions)
