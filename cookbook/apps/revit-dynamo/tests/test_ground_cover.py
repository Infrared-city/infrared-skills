"""The parts of the selection that lie flat on the ground (ir_dynamo.ground_cover)."""

from __future__ import annotations

import numpy as np
from boxes import box_soup

from ir_dynamo import ground_cover, terrain


def _tri(soup):
    return terrain.triangles(soup)


def test_each_closed_box_is_one_part() -> None:
    tri = np.concatenate([_tri(box_soup(0, 0, 0, 1, 1, 1)), _tri(box_soup(5, 0, 0, 1, 1, 1))])
    label = ground_cover.parts(tri)
    assert len(set(label[:12].tolist())) == 1 and len(set(label[12:].tolist())) == 1
    assert label[0] != label[12]


def test_touching_boxes_are_one_part_and_a_long_chain_ends() -> None:
    # 200 boxes in a row, each sharing a corner with the next: one part.
    tri = np.concatenate([_tri(box_soup(float(i), 0, 0, 1, 1, 1)) for i in range(200)])
    assert len(set(ground_cover.parts(tri).tolist())) == 1


def test_flat_parts_go_and_the_result_is_drawn_on_top() -> None:
    soups = {"b1": box_soup(-10, -10, 0, 20, 20, 15), "road": box_soup(-40, -40, 0, 80, 6, 0.3)}
    out, draw_z, draw_sampler, lines = ground_cover.leave_out(soups, None, 0.0)
    assert list(out) == ["b1"] and out["b1"] is soups["b1"]
    assert draw_z == 0.3 and draw_sampler is None  # no terrain: the top of the highest flat part
    assert lines[1] == "  1 whole element(s) (ids road)."


def test_on_terrain_the_result_follows_the_terrain_and_the_flat_parts() -> None:
    plane = np.array(
        [[-100, -100, 0, 100, -100, 0, 100, 100, 0], [-100, -100, 0, 100, 100, 0, -100, 100, 0]], float
    )
    sampler = terrain.Sampler(plane.reshape(-1, 3, 3))
    soups = {"b1": box_soup(-10, -10, 0, 20, 20, 15), "road": box_soup(-40, -40, 0, 80, 6, 0.3)}
    _, draw_z, draw_sampler, _ = ground_cover.leave_out(soups, sampler, 0.0)
    z = draw_sampler.z_at(np.array([[0.0, -37.0], [0.0, 50.0]]))
    assert draw_z == 0.0 and np.allclose(z, [0.3, 0.0])  # on the road, else on the terrain


def test_a_sloping_terrain_decides_what_is_flat() -> None:
    # Terrain rises 0 -> 20 m over x 0..100; a sheet 0.3 m above it is flat, a tower is not.
    ramp = np.array([[0, -50, 0, 100, -50, 20, 100, 50, 20], [0, -50, 0, 100, 50, 20, 0, 50, 0]], float)
    sampler = terrain.Sampler(ramp.reshape(-1, 3, 3))
    sheet = [10, 0, 2.3, 60, 0, 12.3, 60, 10, 12.3]
    soups = {"sheet": sheet, "tower": box_soup(80, 0, 16, 5, 5, 10)}
    out, _, _, _ = ground_cover.leave_out(soups, sampler, 0.0)
    assert list(out) == ["tower"]
