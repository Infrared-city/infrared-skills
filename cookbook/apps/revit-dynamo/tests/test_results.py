from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ir_dynamo import frame, results

F = frame.make_frame(16.371, 48.208, (-10.0, -10.0, 10.0, 10.0), 5.0)


def _bounds_for_cells(n: int) -> tuple:
    """Lon/lat bounds of a grid of n 1 m cells that starts at the polygon SW corner."""
    ring = F.polygon["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    dlon = (max(lons) - min(lons)) / 30.0
    dlat = (max(lats) - min(lats)) / 30.0
    return (min(lons), min(lats), min(lons) + n * dlon, min(lats) + n * dlat)


def test_ground_points_skip_no_data_and_land_in_the_revit_frame() -> None:
    grid = np.full((512, 512), np.nan)
    grid[0, 0] = (
        0.25  # SW cell: centre half a cell in from the grid's SW corner (the SDK rule)
    )
    grid[1, 2] = 0.75
    result = SimpleNamespace(physical_grid=lambda: grid, bounds=_bounds_for_cells(512))
    out = results.ground_points(F, result, z_offset=2.0)
    assert out["kind"] == "points" and len(out["points"]) == 2
    assert out["values"] == [0.25, 0.75]
    assert (out["legend_min"], out["legend_max"]) == (0.25, 0.75)
    assert out["cell_m"] == pytest.approx(1.0, abs=1e-3)
    x, y, z = out["points"][0]
    assert (x, y) == pytest.approx(
        (-14.5, -14.5), abs=0.01
    )  # polygon SW corner (-15, -15) plus half a cell
    assert z == 2.0
    x2, y2, _ = out["points"][1]
    assert (x2, y2) == pytest.approx((-12.5, -13.5), abs=0.01)  # col 2, row 1


def _facade_result(values=(10.0, np.nan, 30.0)):
    # 3 cells with 1 triangle each; one group; the tile sits at (5, 6) in the SDK frame.
    tri = np.array([0, 0, 0, 1, 0, 0, 0, 0, 1], dtype=np.float32)
    tris = SimpleNamespace(
        cell_offsets=np.array([0, 1, 2, 3]),
        drawn=np.array([1, 1, 1]),
        anchors=np.array([[5.0, 6.0]]),
        positions=(np.tile(tri, 3),),
    )
    cols = SimpleNamespace(
        triangles=tris,
        cell_offsets=np.array([0, 3]),
        physical_values=lambda a, b: np.array(values[a:b], dtype=np.float64),
    )
    return SimpleNamespace(columns=cols)


def test_facade_triangles_drop_cells_without_value() -> None:
    out = results.facade_triangles(F, _facade_result(), z_offset=1.0)
    assert out["kind"] == "triangles"
    assert out["values"] == [10.0, 30.0]
    assert len(out["triangles"]) == 2 * 9
    assert (out["legend_min"], out["legend_max"]) == (10.0, 30.0)
    # SDK (5, 6, 0) is (5 - 15, 6 - 15) = (-10, -9) in the Revit frame; z gets the offset.
    assert out["triangles"][:3] == pytest.approx([-10.0, -9.0, 1.0], abs=1e-3)


def test_facade_without_triangles_raises() -> None:
    with pytest.raises(RuntimeError, match="no cell triangles"):
        results.facade_triangles(F, SimpleNamespace(columns=None))


def test_empty_legend_is_none() -> None:
    grid = np.full((4, 4), np.nan)
    result = SimpleNamespace(physical_grid=lambda: grid, bounds=_bounds_for_cells(4))
    out = results.ground_points(F, result)
    assert out["points"] == [] and out["legend_min"] is None


def test_saved_real_grid_leaves_a_hole_exactly_where_the_box_is() -> None:
    """A crop of a real ground SVF grid (20 m box at 5..25 m, buffer 5 m, 1 m cells)."""
    import os

    crop = np.load(
        os.path.join(os.path.dirname(__file__), "data", "ground_svf_crop.npy")
    )
    full = np.full((512, 512), np.nan)  # the bounds belong to the full 512 cell grid
    full[: crop.shape[0], : crop.shape[1]] = crop
    result = SimpleNamespace(
        physical_grid=lambda: full,
        bounds=(
            16.370797580286474,
            48.20786510175911,
            16.377706821642462,
            48.21246962838142,
        ),
    )
    out = results.ground_points(F, result)
    pts = np.array(out["points"])
    box = 10.0  # the box is 20 m wide, centred on the Revit origin
    inside = (np.abs(pts[:, 0]) < box) & (np.abs(pts[:, 1]) < box)
    assert inside.sum() == 0
    # Cells right next to every wall are valid: centres 0.5 m from the wall.
    for wx, wy in [
        (-box - 0.5, 0.0),
        (box + 0.5, 0.0),
        (0.0, -box - 0.5),
        (0.0, box + 0.5),
    ]:
        near = np.hypot(pts[:, 0] - wx, pts[:, 1] - wy) < 0.6
        assert near.any(), (wx, wy)
    assert len(pts) == 500
