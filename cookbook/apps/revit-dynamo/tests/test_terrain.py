"""Terrain maths (ir_dynamo.terrain), the ground reference, burying and the SDK payload."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from boxes import box_soup

from ir_dynamo import frame, meshes, payloads, results, run, settings
from ir_dynamo import terrain as tm
from ir_revit import result_mesh as rm


def ramp(x0=-50.0, x1=50.0, slope=0.1, z0=0.0, flip=False):
    """A square terrain, 2 triangles, z = z0 + slope * x. ``flip``: winding down."""
    y0, y1 = x0, x1
    p = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    v = [(x, y, z0 + slope * x) for x, y in p]
    order = [(0, 1, 2), (0, 2, 3)]
    if flip:
        order = [(a, c, b) for a, b, c in order]
    return [c for tri in order for i in tri for c in v[i]]


def test_sampler_interpolates_and_is_nan_outside() -> None:
    s = tm.Sampler(tm.triangles(ramp()))
    z = s.z_at(np.array([[0.0, 0.0], [10.0, 5.0], [-50.0, 50.0], [60.0, 0.0]]))
    assert z[:3] == pytest.approx([0.0, 1.0, -5.0])
    assert np.isnan(z[3])


def test_prepare_turns_triangles_up_drops_steep_and_far() -> None:
    wall = [0, 0, 0, 0, 5, 0, 0, 0, 5]  # vertical
    far = [500, 500, 0, 510, 500, 0, 500, 510, 0]
    out, warnings = tm.prepare(
        {"t": ramp(flip=True) + wall + far, "gone": far}, (-10, -10, 10, 10), 5.0
    )
    assert list(out) == ["t"] and out["t"].shape == (2, 3, 3) and len(warnings) == 1
    normal = np.cross(out["t"][:, 1] - out["t"][:, 0], out["t"][:, 2] - out["t"][:, 0])
    assert (normal[:, 2] > 0).all()


def test_buried_drops_foundation_but_keeps_a_slab_on_the_ground() -> None:
    flat = tm.triangles(
        box_soup(0, 0, -3, 10, 10, 3)  # foundation: -3 .. 0
        + box_soup(0, 0, 0, 10, 10, 5)  # building: 0 .. 5
    )
    gone = tm.buried(flat, None, 0.0)
    assert gone[:12].sum() == 10  # all but the two top faces at z = 0
    assert not gone[12:].any()  # the slab on the ground (z = 0) stays: closed building


def test_buried_follows_the_terrain() -> None:
    s = tm.Sampler(tm.triangles(ramp(slope=0.1)))
    tri = tm.triangles([10, 0, 0.5, 12, 0, 0.5, 10, 2, 0.5])  # terrain is 1.0 here
    assert tm.buried(tri, s, 0.0).tolist() == [True]
    up = tm.triangles([10, 0, 2.0, 12, 0, 2.0, 10, 2, 2.0])
    assert tm.buried(up, s, 0.0).tolist() == [False]


def test_corner_heights_follow_slope_and_fall_back_outside() -> None:
    s = tm.Sampler(tm.triangles(ramp(slope=0.1)))
    pts = np.array([[0.0, 0.0, 7.0], [49.5, 0.0, 7.0], [200.0, 0.0, 7.0]])
    z = tm.corner_heights(pts, 2.0, s)
    assert z[0] == pytest.approx([-0.1, 0.1, 0.1, -0.1])
    assert z[1, 0] == pytest.approx(4.85) and z[1, 1] == pytest.approx(4.85)  # edge: mean inside
    assert z[2] == pytest.approx([7.0] * 4)  # outside: the centre z


def test_ground_triangles_use_corner_heights_and_lift() -> None:
    tri = rm.ground_triangles([[0, 0, 0.0]], 2.0, [[0.0, 1.0, 2.0, 3.0]])
    assert tri[0, :, 2].tolist() == pytest.approx([0.05, 1.05, 2.05])
    assert tri[1, :, 2].tolist() == pytest.approx([0.05, 2.05, 3.05])
    flat = rm.ground_triangles([[0, 0, 4.0]], 2.0)
    assert np.allclose(flat[:, :, 2], 4.05)


def test_coloured_triangles_pass_corner_z_through() -> None:
    result = {
        "kind": "points",
        "points": [[0.0, 0.0, 0.0]],
        "values": [1.0],
        "cell_m": 2.0,
        "legend_min": 0.0,
        "legend_max": 2.0,
        "corner_z": [[0.0, 1.0, 2.0, 3.0]],
    }
    tri, _ = rm.coloured_triangles(result, [0])
    assert tri[1, 2, 2] == pytest.approx(3.05)


def test_build_buildings_keeps_a_straddling_box_and_refuses_a_buried_one() -> None:
    soups = {"b": box_soup(-10, -10, -3, 20, 20, 18)}  # -3 .. 15
    f = frame.make_frame(16.371, 48.208, meshes.soup_bbox(soups), 5.0)
    buildings, z_offset, warnings = meshes.build_buildings(f, soups)
    assert z_offset == 0.0
    assert min(buildings["b"]["coordinates"][2::3]) == pytest.approx(-3.0)  # walls cross the ground: kept
    assert any("2 triangle(s) below the ground" in w for w in warnings)  # the underside
    low = {"b": box_soup(-10, -10, -9, 20, 20, 6)}  # -9 .. -3: entirely buried
    with pytest.raises(ValueError, match="above the ground"):
        meshes.build_buildings(f, low)


class FakeClient:
    def __init__(self) -> None:
        self.payload = None
        self.buildings = None

    def preview_area(self, polygon, **kw):
        self.payload = kw["payload"]
        self.buildings = kw["buildings"]
        return SimpleNamespace(
            tile_count=1, would_bill_jobs=1, estimated_cost_tokens=1, sensor_count=None
        )


def _scene():
    # A 20 m box from -13 m to 5 m (a basement), on a terrain that rises 0.1 per metre.
    return {"b": box_soup(-10, -10, -13, 20, 20, 18)}, {"t": ramp(slope=0.1, z0=1.0)}


def test_run_with_terrain_sends_ground_geometry_as_is_and_lowers_to_terrain_min() -> None:
    buildings, terrain = _scene()
    client = FakeClient()
    out = run.run_analysis(
        "ground", "svf", buildings, 16.371, 48.208, terrain_m=terrain, client=client
    )
    gg = client.payload.ground_geometry
    assert set(gg) == {"t"} and "coordinates" in gg["t"] and "indices" in gg["t"]
    assert str(client.payload.terrain_alignment) == "as-is"
    assert min(gg["t"]["coordinates"][2::3]) >= -1e-6  # the lowest terrain point is 0 of the SDK
    assert any("below the ground" in w for w in out["warnings"])
    assert client.buildings["b"]["coordinates"]


def test_run_without_terrain_has_no_ground_geometry() -> None:
    client = FakeClient()
    run.run_analysis(
        "ground", "svf", {"b": box_soup(-10, -10, 0, 20, 20, 15)}, 16.371, 48.208, client=client
    )
    assert client.payload.ground_geometry is None


def test_wind_does_not_send_terrain() -> None:
    buildings, terrain = _scene()
    client = FakeClient()
    out = run.run_analysis(
        "ground", "wind", buildings, 16.371, 48.208, terrain_m=terrain, client=client
    )
    assert not hasattr(client.payload, "ground_geometry")
    assert client.payload.terrain_alignment == "to-ground"
    assert any("Wind does not take terrain" in w for w in out["warnings"])


def test_every_terrain_analysis_accepts_ground_geometry() -> None:
    gg = {"t": {"coordinates": [0, 0, 0, 1, 0, 0, 0, 1, 0], "indices": [0, 1, 2]}}
    for surface, label in [("ground", "svf"), ("ground", "sun-hours"), ("facades", "daylight")]:
        row = settings.find_analysis(label, surface)
        req = payloads.build_payload(row, surface, 48.2, 16.3, ground_geometry=gg)
        assert req.ground_geometry == gg and str(req.terrain_alignment) == "as-is"


def test_ground_points_get_corner_heights_from_a_sampler() -> None:
    f = frame.make_frame(16.371, 48.208, (-10.0, -10.0, 10.0, 10.0), 5.0)
    ring = f.polygon["coordinates"][0]
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    bounds = (min(lons), min(lats), max(lons), max(lats))
    grid = np.full((30, 30), np.nan)
    grid[5, 5] = 1.0
    result = SimpleNamespace(physical_grid=lambda: grid, bounds=bounds)
    s = tm.Sampler(tm.triangles(ramp(slope=0.1, z0=2.0)))
    out = results.ground_points(f, result, 2.0, s)
    cz = out["corner_z"][0]
    assert cz[1] - cz[0] == pytest.approx(0.1 * out["cell_m"], abs=1e-3)  # east is higher
    assert out["points"][0][2] == pytest.approx(sum(cz) / 4)
    assert "corner_z" not in results.ground_points(f, result, 2.0)
