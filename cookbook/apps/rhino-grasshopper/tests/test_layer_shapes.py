"""The picture of the trees: a trunk and a crown of the size sent to the SDK."""

from __future__ import annotations

import numpy as np

from ir_rhino import layer_shapes


def test_a_tree_has_its_height_and_crown() -> None:
    tri, rgb = layer_shapes.tree_triangles(np.array([[10.0, 20.0, 1.0, 12.0, 8.0]]), unit=1.0)
    xyz = tri.reshape(-1, 3)
    assert xyz[:, 2].min() == 1.0 and xyz[:, 2].max() == 13.0  # base z + height
    assert np.isclose(xyz[:, 0].max() - xyz[:, 0].min(), 8.0)  # the crown diameter
    assert len(tri) == len(rgb) == 4 * 2 + 2 * layer_shapes.SIDES
    assert set(map(tuple, rgb)) == {layer_shapes.TRUNK_RGB, layer_shapes.CROWN_RGB}


def test_no_trees_no_triangles() -> None:
    tri, rgb = layer_shapes.tree_triangles(np.zeros((0, 5)), unit=1.0)
    assert tri.shape == (0, 3, 3) and rgb.shape == (0, 3)


def test_a_roof_is_lighter_than_a_wall_turned_from_the_light() -> None:
    roof = [[0, 0, 5], [1, 0, 5], [0, 1, 5]]
    north_wall = [[0, 1, 0], [1, 1, 0], [0, 1, 1]]  # faces north, the light comes from the south-west
    rgb = layer_shapes.lit_grey(np.array([roof, north_wall], dtype=float), (200, 200, 200))
    assert rgb[0, 0] > rgb[1, 0] and rgb.max() <= 200 and rgb.min() >= 110
