"""Where the model is on the earth, and the maths between the model and the site frame.

Pure numpy, no Rhino import (tested with pytest).

The site frame is what ``ir_dynamo`` takes: metres, the origin at the site
lon/lat, +x east, +y true north, z up. Rhino gives the place with the
EarthAnchorPoint: a model point (``ModelBasePoint``) that sits at a lon/lat,
and the model direction of true north (``ModelNorth``). Without an
EarthAnchorPoint the command gives lat and lon for the model origin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Site:
    """Where the model is.

    Attributes
    ----------
    lon, lat : float
        Degrees, of the model point ``base``.
    north_rad : float
        Counter-clockwise turn (seen from above) that puts the model's true north on +y.
    base : tuple of float
        The model point at lon/lat, in model units.
    unit_m : float
        Metres per model unit (0.001 for millimetres).
    source : str
        ``"rhino"`` (the EarthAnchorPoint) or ``"command"`` (lat and lon of the command).
    """

    lon: float
    lat: float
    north_rad: float = 0.0
    base: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    unit_m: float = 1.0
    source: str = "rhino"


def north_rad(north_x: float, north_y: float) -> float:
    """The turn that puts the model direction ``(north_x, north_y)`` on +y."""
    if north_x == 0.0 and north_y == 0.0:
        return 0.0
    return math.pi / 2.0 - math.atan2(north_y, north_x)


def _turn(xyz: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    x, y = xyz[:, 0].copy(), xyz[:, 1].copy()
    xyz[:, 0] = c * x - s * y
    xyz[:, 1] = s * x + c * y
    return xyz


def model_to_site_m(xyz: Sequence[float], site: Site) -> np.ndarray:
    """Flat ``x, y, z, ...`` in model units -> flat site-frame metres."""
    out = np.asarray(xyz, dtype=np.float64).reshape(-1, 3) - np.asarray(site.base, dtype=np.float64)
    out *= site.unit_m
    return _turn(out, site.north_rad).reshape(-1)


def site_m_to_model(xyz_m: Sequence[float], site: Site) -> np.ndarray:
    """The inverse of ``model_to_site_m``."""
    out = _turn(np.asarray(xyz_m, dtype=np.float64).reshape(-1, 3).copy(), -site.north_rad)
    out /= site.unit_m
    out += np.asarray(site.base, dtype=np.float64)
    return out.reshape(-1)
