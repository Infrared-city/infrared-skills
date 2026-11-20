"""Own trees and ground materials as the GeoJSON layers of the SDK."""

from __future__ import annotations

import pytest

from ir_dynamo import frame as frame_mod
from ir_dynamo import own_layers

LON, LAT = 16.3721, 48.2085


def _frame() -> frame_mod.SiteFrame:
    return frame_mod.make_frame(LON, LAT, (-10.0, -10.0, 10.0, 10.0), 30.0)


def test_a_tree_is_a_point_with_a_size() -> None:
    out = own_layers.trees_geojson(_frame(), [(0.0, 0.0, None, None), (100.0, 0.0, 12.0, 8.0)])
    first, second = out["tree-0"], out["tree-1"]
    assert first["geometry"]["coordinates"] == pytest.approx([LON, LAT])
    assert first["properties"] == {"height": 6.0, "crownDiameter": 4.0}
    assert second["properties"] == {"height": 12.0, "crownDiameter": 8.0}
    assert second["geometry"]["coordinates"][0] > LON  # 100 m east


def test_ground_rings_are_closed_polygons_per_material() -> None:
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    out = own_layers.ground_geojson(_frame(), {"Concrete": [square, [(0.0, 0.0), (1.0, 1.0)]]})
    assert list(out) == ["concrete"]
    features = out["concrete"]["features"]
    assert len(features) == 1  # the 2-point ring is left out
    ring = features[0]["geometry"]["coordinates"][0]
    assert len(ring) == 5 and ring[0] == ring[-1]


def test_an_unknown_material_is_refused() -> None:
    with pytest.raises(ValueError, match="asphalt, concrete, soil, vegetation, water"):
        own_layers.material_name("Brick Pavers")


def test_ground_materials_warn_outside_the_thermal_analyses() -> None:
    ground = {"water": [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]]}
    assert own_layers.notes("sky-view-factors", [], ground)[0].startswith("Warning: ground materials")
    assert own_layers.notes("thermal-comfort-index", [(0, 0, None, None)], ground) == [
        "Trees: 1 (0 with a size from the geometry; the others 6 m high, 4 m crown).",
        "Ground materials: water 1. Where two overlap, one of them is used.",
    ]
