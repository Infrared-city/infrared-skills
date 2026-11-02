"""The 2D rotation and unit scale of revit_location (no Revit needed)."""

import math

import numpy as np
from revit import revit_location as loc


def test_round_trip():
    pts = np.array([10.0, 20.0, 5.0, -3.0, 7.0, 0.0])
    metres = loc.internal_ft_to_site_m(pts, 0.7)
    back = loc.site_m_to_internal_ft(metres, 0.7)
    assert np.allclose(back, pts)


def test_feet_to_metres_without_rotation():
    out = loc.internal_ft_to_site_m([1.0, 2.0, 3.0], 0.0)
    assert np.allclose(out, [0.3048, 0.6096, 0.9144])


def test_true_north_direction():
    # True north is 90 deg counter-clockwise from project north: project -x is true north.
    out = loc.internal_ft_to_site_m([-1.0 / 0.3048, 0.0, 0.0], math.pi / 2)
    assert np.allclose(out, [0.0, 1.0, 0.0], atol=1e-9)
