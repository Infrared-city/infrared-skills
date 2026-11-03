"""ir_dynamo.grid_check: which cell shift puts the no-data cells under the buildings."""

from __future__ import annotations

import numpy as np

from ir_dynamo import grid_check


def _roof(x0, y0, x1, y1, z=10.0) -> dict:
    xyz = [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z]
    return {"coordinates": xyz, "indices": [0, 1, 2, 0, 2, 3]}


def test_building_points_are_inside_the_roof_and_skip_the_ground_slab() -> None:
    pts = grid_check.building_points({"a": _roof(5, 5, 15, 10), "slab": _roof(0, 0, 50, 50, 0.0)})
    assert len(pts) > 8 * 20 / 2  # a 0.5 m lattice over the 10 x 5 m roof, plus 8
    assert pts[:, 0].min() > 5 and pts[:, 0].max() < 15 and pts[:, 1].min() > 5 and pts[:, 1].max() < 10


def test_a_simple_box_roof_tells_the_shifts_apart() -> None:
    no_data = np.zeros((30, 30), dtype=bool)
    no_data[5:10, 5:15] = True
    pts = grid_check.building_points({"box": _roof(5, 5, 15, 10)})  # 2 big triangles only
    found, _ = grid_check.scores(no_data, (0.0, 0.0), (1.0, 1.0), pts)
    assert found[(0, 0)] == 1.0 and all(v < 0.95 for k, v in found.items() if k != (0, 0))


def _fine_roof(x0, y0, x1, y1, z=10.0) -> dict:
    """A roof tessellated into 1 m squares, like a real model's roof."""
    xyz, idx = [], []
    for x in range(x0, x1):
        for y in range(y0, y1):
            n = len(xyz) // 3
            xyz += [x, y, z, x + 1, y, z, x + 1, y + 1, z, x, y + 1, z]
            idx += [n, n + 1, n + 2, n, n + 2, n + 3]
    return {"coordinates": xyz, "indices": idx}


def test_the_sdk_rule_wins_when_the_hole_sits_where_the_rule_says() -> None:
    no_data = np.zeros((30, 30), dtype=bool)
    no_data[5:10, 5:15] = True  # rows = y 5..10, cols = x 5..15 under the SDK rule
    pts = grid_check.building_points({"a": _fine_roof(5, 5, 15, 10)})
    found, counted = grid_check.scores(no_data, (0.0, 0.0), (1.0, 1.0), pts)
    assert found[(0, 0)] == 1.0 and counted > 0
    assert all(v < 1.0 for k, v in found.items() if k != (0, 0))
    shifted = np.roll(np.roll(no_data, 1, axis=0), 1, axis=1)  # the hole one cell NE
    found, _ = grid_check.scores(shifted, (0.0, 0.0), (1.0, 1.0), pts)
    assert max(found, key=found.get) == (-1, -1)
