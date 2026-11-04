"""The OBJ export for the platform upload (ir_dynamo.obj_export)."""

from __future__ import annotations

import datetime

import numpy as np
import pytest
from boxes import box_soup

from ir_dynamo import obj_export as ox


def flat_ground(z: float = 0.0, half: float = 100.0):
    a, b = -half, half
    v = [(a, a, z), (b, a, z), (b, b, z), (a, b, z)]
    return [c for tri in ((0, 1, 2), (0, 2, 3)) for i in tri for c in v[i]]


def parse(text: str):
    names, verts, faces = [], [], []
    for line in text.splitlines():
        head, _, rest = line.partition(" ")
        if head == "o":
            names.append(rest)
        elif head == "v":
            verts.append([float(x) for x in rest.split()])
        elif head == "f":
            faces.append([int(x) for x in rest.split()])
    return names, np.array(verts), np.array(faces)


def test_box_is_welded_named_and_y_up() -> None:
    scene = ox.prepare_scene({"12": box_soup(0, 0, 0, 10, 20, 30)})
    text, counts = ox.obj_text(scene, header=["unit: metres"])
    names, verts, faces = parse(text)
    assert text.startswith("# unit: metres\n")
    assert names == ["building_12"]
    assert counts == {"objects": 1, "vertices": 8, "faces": 12}
    assert faces.min() == 1 and faces.max() == 8
    # y is up: 0..30 m. The origin is the middle of the box in x and north.
    assert verts[:, 1].min() == pytest.approx(0.0) and verts[:, 1].max() == pytest.approx(30.0)
    assert verts[:, 0].min() == pytest.approx(-5.0) and verts[:, 0].max() == pytest.approx(5.0)
    # z is south: north 0..20 around the middle 10 gives z -10..10.
    assert verts[:, 2].min() == pytest.approx(-10.0) and verts[:, 2].max() == pytest.approx(10.0)
    assert "usemtl" not in text


def test_north_is_minus_z() -> None:
    scene = ox.prepare_scene({"a": box_soup(0, 0, 0, 1, 1, 3), "b": box_soup(0, 50, 0, 1, 1, 3)})
    _, verts, _ = parse(ox.obj_text(scene)[0])
    north_box = verts[8:]  # the second object
    assert north_box[:, 2].max() < verts[:8, 2].min()


def test_basement_is_cut_and_terrain_sets_the_ground() -> None:
    house = box_soup(0, 0, -6, 10, 10, 9) + box_soup(0, 0, 3, 10, 10, 12)
    scene = ox.prepare_scene({"h": house}, {"t": flat_ground(3.0)})
    assert scene.origin[2] == pytest.approx(3.0)
    assert any("below the ground" in w for w in scene.warnings)
    text, counts = ox.obj_text(scene)
    names, verts, _ = parse(text)
    assert names == ["building_h", "ground_t"]
    assert verts[:8, 1].min() >= -1e-9  # nothing of the building below the ground
    assert counts["objects"] == 2


def test_no_terrain_ground_is_elevation_0_with_a_warning() -> None:
    scene = ox.prepare_scene({"h": box_soup(0, 0, -3, 5, 5, 5) + box_soup(0, 0, 2, 5, 5, 5)})
    assert scene.origin[2] == 0.0
    assert any("No terrain" in w for w in scene.warnings)


def test_all_buried_is_an_error() -> None:
    with pytest.raises(ValueError, match="below the ground"):
        ox.prepare_scene({"b": box_soup(0, 0, -10, 5, 5, 3)})


def test_names_and_path_are_file_safe() -> None:
    scene = ox.prepare_scene({"Wall 1/2": box_soup(0, 0, 0, 1, 1, 3)})
    assert parse(ox.obj_text(scene)[0])[0] == ["building_Wall_1_2"]
    when = datetime.datetime(2026, 11, 4, 9, 5)
    path = ox.export_path("out", r"C:\p\My Model (v2).rvt", when)
    assert path.replace("\\", "/") == "out/My_Model_v2-20261104-0905.obj"
    assert ox.export_path("out", "", when).endswith("revit-20261104-0905.obj")


def test_size_line_warns_above_40_mb() -> None:
    assert "limit 40 MB" in ox.size_line(1024)
    assert "above the platform limit" in ox.size_line(41 * 1024 * 1024)
