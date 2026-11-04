from __future__ import annotations

import numpy as np
import pytest

from ir_dynamo import frame

LON, LAT = 16.371, 48.208


def make(buffer_m: float = 5.0) -> frame.SiteFrame:
    return frame.make_frame(LON, LAT, (-10.0, -10.0, 10.0, 10.0), buffer_m)


def test_polygon_is_closed_and_has_the_buffered_size() -> None:
    f = make()
    ring = f.polygon["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert f.size_m[0] == pytest.approx(30.0, abs=0.01)
    assert f.size_m[1] == pytest.approx(30.0, abs=0.01)


def test_sw_corner_of_the_polygon_is_the_sdk_origin() -> None:
    f = make()
    # SW corner in the Revit frame is (-15, -15). In the SDK frame it is (0, 0).
    sw = frame.points_to_sdk(f, [-15.0, -15.0, 2.0])
    assert sw[0] == pytest.approx(0.0, abs=1e-6)
    assert sw[1] == pytest.approx(0.0, abs=1e-6)
    assert sw[2] == 2.0
    ne = frame.points_to_sdk(f, [15.0, 15.0, 0.0])
    assert ne[0] == pytest.approx(f.size_m[0], abs=1e-3)
    assert ne[1] == pytest.approx(f.size_m[1], abs=1e-3)


def test_round_trip_revit_sdk_revit() -> None:
    f = make()
    rng = np.random.default_rng(1)
    pts = rng.uniform(-14, 14, size=(50, 3)).reshape(-1)
    back = frame.points_to_revit(f, frame.points_to_sdk(f, pts))
    assert np.max(np.abs(back - pts)) < 1e-6


def test_sdk_frame_is_not_a_plain_translation() -> None:
    # The scale is the cosine ratio of the two origin latitudes (a tiny, real change).
    f = make()
    assert f.to_sdk.scale_x != 1.0
    assert f.to_sdk.scale_x == pytest.approx(1.0, abs=1e-4)


def test_empty_array() -> None:
    assert frame.points_to_sdk(make(), []).size == 0


def test_grid_cell_size_matches_the_polygon_extent() -> None:
    f = make()
    ring = f.polygon["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    cx, cy = frame.grid_cell_m((min(lons), min(lats), max(lons), max(lats)), (30, 30))
    assert cx == pytest.approx(1.0, abs=1e-3)
    assert cy == pytest.approx(1.0, abs=1e-3)


def test_point_lonlat_moves_north_and_east() -> None:
    assert frame.point_lonlat(LON, LAT, 0.0, 0.0) == pytest.approx((LON, LAT))
    lon, lat = frame.point_lonlat(LON, LAT, 100.0, 1000.0)
    assert lon > LON and lat == pytest.approx(LAT + 1000.0 / 111_200.0, abs=1e-4)
