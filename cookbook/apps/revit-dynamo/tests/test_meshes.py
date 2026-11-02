from __future__ import annotations

import pytest
from boxes import box_soup

from ir_dynamo import frame, meshes


def test_box_is_welded_and_moved_to_the_sdk_frame() -> None:
    soups = {"b": box_soup(-10, -10, 3, 20, 20, 15)}
    f = frame.make_frame(16.371, 48.208, meshes.soup_bbox(soups), 5.0)
    buildings, z_offset, warnings = meshes.build_buildings(f, soups, 3.0)
    mesh = buildings["b"]
    assert z_offset == 3.0 and warnings == []
    assert len(mesh["coordinates"]) == 8 * 3  # 36 corners welded to 8 vertices
    assert len(mesh["indices"]) == 12 * 3
    xs = mesh["coordinates"][0::3]
    zs = mesh["coordinates"][2::3]
    assert min(xs) == pytest.approx(5.0, abs=1e-3)  # 5 m buffer
    assert min(zs) == pytest.approx(0.0) and max(zs) == pytest.approx(15.0)


def test_bad_input() -> None:
    with pytest.raises(ValueError, match="9 numbers"):
        meshes.soup_bbox({"b": [0.0, 1.0]})
    with pytest.raises(ValueError, match="No buildings"):
        meshes.soup_bbox({})
    with pytest.raises(ValueError, match="not a number"):
        meshes.soup_bbox({"b": [float("nan")] * 9})


def test_degenerate_building_is_skipped_with_a_warning() -> None:
    soups = {"ok": box_soup(0, 0, 0, 10, 10, 10), "flat": [0, 0, 0, 0, 0, 0, 1, 1, 1]}
    f = frame.make_frame(16.371, 48.208, meshes.soup_bbox(soups), 5.0)
    buildings, _, warnings = meshes.build_buildings(f, soups)
    assert list(buildings) == ["ok"] and "flat" in warnings[0]


def test_context_overlapping_a_selected_building_is_dropped() -> None:
    sel = {"a": {"coordinates": [0, 0, 0, 10, 10, 5], "indices": [0, 1, 0]}}
    near = {"coordinates": [5, 5, 0, 8, 8, 9], "indices": [0, 1, 0]}
    far = {"coordinates": [50, 50, 0, 60, 60, 9], "indices": [0, 1, 0]}
    merged, added = meshes.merge_context(sel, {"n": near, "f": far})
    assert added == 1 and set(merged) == {"a", "ctx-f"}


def test_context_accepts_sdk_dotbim_mesh_objects() -> None:
    from infrared_sdk.buildings.types import DotBimMesh

    sel = {"a": {"coordinates": [0, 0, 0, 10, 10, 5], "indices": [0, 1, 0]}}
    far = DotBimMesh(mesh_id=7, coordinates=[50, 50, 0, 60, 60, 9], indices=[0, 1, 0])
    merged, added = meshes.merge_context(sel, {"7": far})
    assert added == 1
    assert merged["ctx-7"] == {
        "coordinates": [50, 50, 0, 60, 60, 9],
        "indices": [0, 1, 0],
    }
