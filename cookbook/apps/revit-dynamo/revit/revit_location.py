"""The site location of the Revit project, and the maths between the two frames.

WHICH POINT IS THE LON/LAT?  (read this first)
    Revit stores ONE geographic location for the whole project
    (Manage > Location, ``doc.SiteLocation``). It has no point inside the
    model. This app ASSUMES that the lon/lat belongs to the INTERNAL ORIGIN of
    the Revit file (the 0,0,0 point of the internal coordinates), not to the
    Project Base Point and not to the Survey Point. The geometry that
    ``revit_geometry`` reads is in internal coordinates, so the origin of the
    "Revit frame" is exactly that point.

    What the user must set so it is right:
      * Manage > Location: the true city or address of the project (it sets
        latitude and longitude). Or give ``lat`` and ``lon`` to the script.
      * For the free area run, an error of some metres is not important.
      * Only ``fetch_context`` (public buildings around the site) needs the
        internal origin to be within about 10 m of the real lon/lat. If the
        model is far from the internal origin, or the Project Base Point was
        moved, give the lat/lon OF THE INTERNAL ORIGIN to the script.
    Shared coordinates (survey point offsets) are NOT used.

TRUE NORTH
    ``ProjectPosition.Angle`` of the active project location is the angle in
    radians between project north (up in a plan view) and true north. The
    script rotates the geometry about the Z axis so that +y is true north.
    The sign convention is the one thing nobody could test without Revit:
    ASSUMED, true north is ``Angle`` counter-clockwise from project north (the
    Revit API angle convention), so true = rotate(internal, -Angle). If the
    shade of a building falls on the wrong side in a project with a rotated
    true north, set ``ANGLE_SIGN = -1.0`` below.

All lon/lat maths stays in ``ir_dynamo/frame.py``. This file has only a unit
scale and a 2D rotation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

FEET_TO_M = 0.3048
# Flip to -1.0 if true north turns out to be on the other side (see above).
ANGLE_SIGN = 1.0


@dataclass(frozen=True)
class SiteLocation:
    """Where the project is.

    Attributes
    ----------
    lon, lat : float
        Degrees. The origin of the Revit frame (the internal origin).
    true_north_rad : float
        Angle from project north to true north, radians (as Revit gives it).
    source : str
        ``"revit"`` or ``"override"``: where lon/lat came from.
    """

    lon: float
    lat: float
    true_north_rad: float
    source: str


def read_location(
    doc: object, lat: Optional[float] = None, lon: Optional[float] = None
) -> SiteLocation:
    """Read the site location and true north from a Revit document.

    Parameters
    ----------
    doc : Autodesk.Revit.DB.Document
    lat, lon : float, optional
        Degrees. Give both to replace the location of the project. Give one
        only and you get an error.

    Raises
    ------
    ValueError
        When only one of ``lat`` and ``lon`` is given, or a value is out of range.
    """
    from Autodesk.Revit.DB import XYZ  # type: ignore  # Revit only

    if (lat is None) != (lon is None):
        raise ValueError("Give both lat and lon, or neither.")
    angle = float(doc.ActiveProjectLocation.GetProjectPosition(XYZ.Zero).Angle)
    if lat is not None and lon is not None:
        source = "override"
    else:
        site = doc.SiteLocation
        # SiteLocation.Latitude and .Longitude are in RADIANS.
        lat, lon, source = (
            math.degrees(site.Latitude),
            math.degrees(site.Longitude),
            "revit",
        )
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("lat/lon out of range: %.5f, %.5f" % (lat, lon))
    return SiteLocation(float(lon), float(lat), angle, source)


def internal_ft_to_site_m(xyz_ft: Sequence[float], true_north_rad: float) -> np.ndarray:
    """Internal Revit feet -> Revit frame metres (true north is +y).

    Parameters
    ----------
    xyz_ft : sequence of float
        Flat ``x, y, z, x, y, z, ...`` in feet, internal coordinates.
    true_north_rad : float
        ``SiteLocation.true_north_rad``.

    Returns
    -------
    numpy.ndarray
        Flat array, same length, metres.
    """
    out = np.asarray(xyz_ft, dtype=np.float64).reshape(-1, 3) * FEET_TO_M
    c, s = _cos_sin(-true_north_rad)
    x, y = out[:, 0].copy(), out[:, 1].copy()
    out[:, 0] = c * x - s * y
    out[:, 1] = s * x + c * y
    return out.reshape(-1)


def site_m_to_internal_ft(xyz_m: Sequence[float], true_north_rad: float) -> np.ndarray:
    """Revit frame metres -> internal Revit feet. The inverse of the function above."""
    out = np.asarray(xyz_m, dtype=np.float64).reshape(-1, 3).copy()
    c, s = _cos_sin(true_north_rad)
    x, y = out[:, 0].copy(), out[:, 1].copy()
    out[:, 0] = c * x - s * y
    out[:, 1] = s * x + c * y
    return (out / FEET_TO_M).reshape(-1)


def _cos_sin(angle: float) -> "tuple[float, float]":
    a = ANGLE_SIGN * angle
    return math.cos(a), math.sin(a)
