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


def test_box_is_welded_named_and_z_up() -> None:
    scene = ox.prepare_scene({"12": box_soup(0, 0, 0, 10, 20, 30)})
    text, counts = ox.obj_text(scene, header=["unit: metres"])
    names, verts, faces = parse(text)
    assert text.startswith("# unit: metres\n")
    assert names == ["building_12"]
    assert counts == {"objects": 1, "vertices": 8, "faces": 12}
    assert faces.min() == 1 and faces.max() == 8
    # z is up: 0..30 m. The origin is the middle of the box in x and north.
    assert verts[:, 2].min() == pytest.approx(0.0) and verts[:, 2].max() == pytest.approx(30.0)
    assert verts[:, 0].min() == pytest.approx(-5.0) and verts[:, 0].max() == pytest.approx(5.0)
    # y is north: 0..20 around the middle 10 gives -10..10.
    assert verts[:, 1].min() == pytest.approx(-10.0) and verts[:, 1].max() == pytest.approx(10.0)
    assert "usemtl" not in text


def test_north_is_plus_y() -> None:
    scene = ox.prepare_scene({"a": box_soup(0, 0, 0, 1, 1, 3), "b": box_soup(0, 50, 0, 1, 1, 3)})
    _, verts, _ = parse(ox.obj_text(scene)[0])
    north_box = verts[8:]  # the second object
    assert north_box[:, 1].min() > verts[:8, 1].max()


def test_basement_is_cut_and_terrain_sets_the_ground() -> None:
    house = box_soup(0, 0, -6, 10, 10, 9) + box_soup(0, 0, 3, 10, 10, 12)
    scene = ox.prepare_scene({"h": house}, {"t": flat_ground(3.0)})
    assert scene.origin[2] == pytest.approx(3.0)
    assert any("below the ground" in w for w in scene.warnings)
    text, counts = ox.obj_text(scene)
    names, verts, _ = parse(text)
    assert names == ["building_h", "ground_t"]
    assert verts[:8, 2].min() >= -1e-9  # nothing of the building below the ground
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


def test_parse_export_labels() -> None:
    assert ox.parse_export("export-obj") is False
    assert ox.parse_export(" Export OBJ ") is False
    assert ox.parse_export("export-obj all") is True
    assert ox.parse_export("export_obj_all") is True
    assert ox.parse_export("solar") is None
    assert ox.parse_export("all") is None


def test_building_categories_by_builtin_or_english_name() -> None:
    for builtin in ("OST_Walls", "OST_StructuralColumns", "OST_StructuralFraming",
                    "OST_CurtainWallPanels", "OST_CurtainWallMullions", "OST_Roofs"):
        assert ox.is_building(builtin, "Wände")
    assert ox.is_building("", "Curtain Panels") and ox.is_building("", "windows")
    for builtin, name in (("OST_Doors", "Doors"), ("OST_Stairs", "Stairs"),
                          ("OST_LightingFixtures", "Lighting Fixtures"),
                          ("OST_GenericModel", "Generic Models"), ("", "")):
        assert not ox.is_building(builtin, name) and ox.not_building(builtin, name)


def test_many_buried_elements_give_one_line() -> None:
    soups = {str(i): box_soup(0, 0, -10, 1, 1, 3) for i in range(9)}
    soups["up"] = box_soup(0, 0, 0, 1, 1, 3)
    scene = ox.prepare_scene(soups)
    lines = [w for w in scene.warnings if "entirely below" in w]
    assert lines == [
        "9 element(s) are entirely below the ground and are not exported "
        "(ids 0, 1, 2, 3, 4 and 4 more)."
    ]


def test_vertices_are_written_in_millimetres() -> None:
    text = ox.obj_text(ox.prepare_scene({"a": box_soup(0, 0, 0, 1.23456, 1, 3)}))[0]
    assert "v -0.617 -0.500 0.000" in text


def test_a_wall_through_the_ground_is_cut_at_the_ground() -> None:
    wall = box_soup(0, 0, -5, 10, 0.3, 15)  # a basement wall, -5 .. 10 m
    scene = ox.prepare_scene({"w": wall})
    _, verts, _ = parse(ox.obj_text(scene)[0])
    assert verts[:, 2].min() == pytest.approx(0.0, abs=1e-3)
    assert verts[:, 2].max() == pytest.approx(10.0)
    assert any("cut at the ground" in w for w in scene.warnings)


def test_cut_follows_a_sloped_terrain() -> None:
    def ramp(h=50.0, slope=0.1):
        v = [(-h, -h, slope * -h), (h, -h, slope * -h), (h, h, slope * h), (-h, h, slope * h)]
        return [c for t in ((0, 1, 2), (0, 2, 3)) for i in t for c in v[i]]
    scene = ox.prepare_scene({"b": box_soup(-5, -5, -10, 10, 10, 30)}, {"t": ramp()})
    tri = scene.buildings["b"].reshape(-1, 3)
    ground = 0.1 * tri[:, 1]  # the ramp rises to the north
    assert np.all(tri[:, 2] >= ground - 0.011)  # GROUND_TOL_M
    assert tri[:, 2].min() < 0.0  # the low (south) side goes below elevation 0
