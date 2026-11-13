"""What gets a result and what only shades; the run area; the lines about them."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
from boxes import box_soup

from ir_dynamo import frame, grid_check, meshes, payloads, results, run, summary
from ir_revit import revit_filters, revit_legend, revit_results, revit_selection

LON, LAT = 16.3701, 48.1983
BOX = (-10.0, -10.0, 10.0, 10.0)


def test_the_context_margin_fills_the_tile_for_the_same_cost() -> None:
    kind = "sky-view-factors"
    small = frame.make_frame(LON, LAT, BOX, 30.0)
    margin = frame.fill_buffer(LON, LAT, BOX, 30.0, kind)
    filled = frame.make_frame(LON, LAT, BOX, margin)
    assert frame.tile_count(small.polygon, kind) == frame.tile_count(filled.polygon, kind) == 1
    assert 490.0 < filled.size_m[0] < 512.0  # one more metre of margin is a second tile
    wide = frame.make_frame(LON, LAT, BOX, margin + 8.0)
    assert frame.tile_count(wide.polygon, kind) > 1


def test_near_keeps_the_elements_that_can_shade() -> None:
    soups = {"close": box_soup(60, 0, 0, 10, 10, 10), "far": box_soup(900, 0, 0, 10, 10, 10)}
    assert list(meshes.near(soups, BOX, 400.0)) == ["close"]


class _Client:
    def preview_area(self, polygon: Any, **kw: Any) -> Any:
        self.buildings = kw["buildings"]
        return SimpleNamespace(tile_count=1, would_bill_jobs=1, estimated_cost_tokens=10, sensor_count=None)


def test_shade_elements_are_sent_but_do_not_size_the_area() -> None:
    client = _Client()
    own = {"b1": box_soup(-10, -10, 0, 20, 20, 15)}
    shade = {"s1": box_soup(100, 0, 0, 10, 10, 30), "s2": box_soup(2000, 0, 0, 10, 10, 30)}
    out = run.run_analysis("ground", "svf", own, LON, LAT, shade_m=shade, client=client)
    assert sorted(client.buildings) == ["b1", "s1"]  # s2 is too far to shade
    assert out["warnings"][0] == "Area: 80 x 80 m (the selection and a margin of 30 m; set it with the word margin)."
    assert any(w.startswith("Shade only: 1 other element(s)") for w in out["warnings"])
    out = run.run_analysis("ground", "svf", own, LON, LAT, buffer_m=100.0, client=client)
    assert out["warnings"][0] == "Area: 220 x 220 m (the selection and a margin of 100 m)."


def _facade_result() -> Any:
    # Two surfaces of two buildings, two cells each, one triangle per cell.
    tri = np.array([0, 0, 0, 1, 0, 0, 0, 0, 1], dtype=np.float32)
    far = tri + np.array([500, 0, 0] * 3, dtype=np.float32)
    tris = SimpleNamespace(
        cell_offsets=np.arange(5),
        drawn=np.ones(4),
        anchors=np.array([[5.0, 6.0]]),
        positions=(np.concatenate([tri, far, tri, tri]),),
    )
    values = np.array([10.0, 20.0, 30.0, 40.0])
    cols = SimpleNamespace(
        ids=("b1/0", "link7-22/0"),
        triangles=tris,
        cell_offsets=np.array([0, 2, 4]),
        physical_values=lambda a, b: values[a:b],
    )
    return SimpleNamespace(columns=cols)


def test_facade_cells_of_shade_elements_and_outside_the_area_are_left_out() -> None:
    f = frame.make_frame(LON, LAT, BOX, 5.0)
    out = results.facade_triangles(f, _facade_result(), skip={"link7-22"}, box_m=f.size_m)
    assert out["values"] == [10.0]  # 20 is outside the area; 30 and 40 are on a shade element
    assert out["left_out"] == {"shade": 2, "outside": 1}
    assert (out["legend_min"], out["legend_max"]) == (10.0, 10.0)
    assert results.building_of("link7-22/13") == "link7-22"


def test_the_grid_check_counts_only_buildings_inside_the_area() -> None:
    f = frame.make_frame(LON, LAT, BOX, 5.0)  # a 30 x 30 m area
    grid = np.zeros((512, 512))
    grid[30:, :] = np.nan
    grid[:, 30:] = np.nan  # the server gives no value outside the area
    grid[10:20, 10:20] = np.nan  # the building of the selection
    ring = f.polygon["coordinates"][0]
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    step_lon, step_lat = (max(lons) - min(lons)) / 30.0, (max(lats) - min(lats)) / 30.0
    bounds = (min(lons), min(lats), min(lons) + 512 * step_lon, min(lats) + 512 * step_lat)
    result = SimpleNamespace(physical_grid=lambda: grid, bounds=bounds)

    def roof(x0: float, y0: float, x1: float, y1: float) -> dict:
        xyz = [x0, y0, 9.0, x1, y0, 9.0, x1, y1, 9.0, x0, y1, 9.0]
        return {"coordinates": xyz, "indices": [0, 1, 2, 0, 2, 3]}

    # The roof sent is one cell east of the hole: a shift of one cell fits better, and the
    # context building far outside the area must not hide that.
    buildings = {"own": roof(11, 10, 21, 20), "ctx-1": roof(100, 100, 400, 400)}
    lines = grid_check.alignment_lines(f, result, buildings)
    assert "SDK rule: 90 %; best: x +1, y +0 cell(s): 100 %" in lines[0]
    assert lines[-1].startswith("Warning:")


def test_the_revit_default_location_gives_a_warning() -> None:
    assert payloads.default_location_note(42.41486, -71.25807, "revit")[0].startswith("Warning:")
    assert payloads.default_location_note(42.41486, -71.25807, "override") == []
    assert payloads.default_location_note(48.1983, 16.3701, "revit") == []


def test_warnings_first_keeps_the_order_of_the_rest() -> None:
    lines = ["a", "[ground] Warning: x", "b", "Weather: station S, 33 km. Warning: that is far.", "Error on facades: y"]
    out = summary.warnings_first(lines)
    assert out[0] == "Warnings (3):" and out[4:] == ["---", "a", "b"]
    assert summary.warnings_first(["a", "b"]) == ["a", "b"]


def test_a_legend_view_gets_a_legal_unique_name() -> None:
    label = "daylight facades months 1-12 hours 8-18 run (2026-11-12 14.41)"
    name = revit_legend.view_name("facades", label, [])
    assert name == "Infrared legend - facades - " + label
    assert revit_legend.view_name("facades", "a:b;c", [name]) == "Infrared legend - facades - a-b-c"
    assert revit_legend.view_name("facades", label, [name]) == name + " (2)"


def test_a_shape_tells_its_run_and_its_target() -> None:
    label = "solar both run (2026-11-13 09.10)"
    ground = revit_results.shape_label("ground", label)
    assert ground == "ground - " + label and revit_results.shape_label("ground", "") == ""
    # The two shapes of a `both` run have their own text, so each has its own filter.
    assert ground != revit_results.shape_label("facades", label)
    assert revit_results.target_of("ground", label) == "ground"
    assert revit_results.target_of("kept", ground) == "ground"  # the tag of an earlier version
    assert revit_results.target_of("kept", label) == ""
    # Drawn again (show-last): the shape of the same run and target is replaced, no other.
    assert revit_results.same_run(ground, "ground", "ground", label)
    assert revit_results.same_run(label, "ground", "ground", label)  # drawn by an earlier version
    assert not revit_results.same_run(ground, "ground", "facades", label)
    assert not revit_results.same_run(label, "kept", "ground", label)
    assert not revit_results.same_run(ground, "ground", "ground", "wind 5 25 run (2026-11-13 09.20)")
    assert not revit_results.same_run("", "kept", "ground", "")


def test_a_legend_view_has_the_run_in_its_name() -> None:
    old, new = "wind 5 25 run (2026-11-13 09.10)", "daylight ground run (2026-11-13 09.20)"
    base, name = "Infrared legend - ground", "Infrared legend - ground - " + old
    assert revit_legend.view_name("ground", old, []) == name
    assert revit_legend.view_name("ground", "", []) == base  # a result without a label
    # The view of the result in the model: by its label, the last one of that label.
    assert revit_legend.current_view_name("ground", old, [base, name]) == name
    assert revit_legend.current_view_name("ground", old, [name, name + " (2)", name + " (x)"]) == name + " (2)"
    # A view of an earlier version has the target only. The view of another run is not it.
    other = "Infrared legend - ground - " + new
    assert revit_legend.current_view_name("ground", old, [base, other]) == base
    assert revit_legend.current_view_name("ground", old, [other]) == ""
    assert revit_legend.current_view_name("ground", "", [name]) == ""


def test_each_result_label_has_one_view_filter() -> None:
    old = "wind 5 25 run (2026-11-13 09.10)"
    new = "facades - daylight facades months 1-12 run (2026-11-13 09.20)"
    assert revit_filters.filter_name("a:b;c") == "Infrared result - a-b-c"
    create, delete = revit_filters.plan([old, new, new, ""], [])
    assert create == {"Infrared result - " + old: old, "Infrared result - " + new: new}
    assert delete == []
    # The result of `old` is gone: its filter goes. A filter of the user stays.
    existing = ["Infrared result - " + old, "Infrared result - " + new, "Walls 200"]
    assert revit_filters.plan([new], existing) == ({}, ["Infrared result - " + old])


def test_the_last_selection_is_kept_for_its_own_model(tmp_path: Any) -> None:
    path = str(tmp_path / "sub" / "selection.json")
    assert revit_selection.recall(path, "a.rvt") is None
    revit_selection.remember(path, "a.rvt", ["u1", "u2"], [["link", "u3"]])
    assert revit_selection.recall(path, "a.rvt") == {"host": ["u1", "u2"], "linked": [["link", "u3"]]}
    assert revit_selection.recall(path, "b.rvt") is None
