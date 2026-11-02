"""The site frame: Revit metres <-> SDK metres, through the SDK kernel.

Two frames meet here.

* Revit frame: metres, x east, y north (true north), origin = the project
  site location (``site_lon``, ``site_lat``). The Revit side builds it.
* SDK frame: metres, origin = south-west corner of the run polygon.

They are not a plain translation: the east-west scale depends on the latitude
of each origin. The kernel gives the exact affine, so no degree maths is
written here.

NOTE: every kernel call of ir_dynamo is in this file. The functions used
(``infrared_sdk.tiling.reanchor`` and
``infrared_sdk.ground_materials.cleaning.project_polygon_to_meters``) are not
documented public API. They are pinned to infrared-sdk 1.0.0. A later SDK
swap touches only this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
from infrared_sdk.ground_materials.cleaning import project_polygon_to_meters
from infrared_sdk.tiling.reanchor import (
    FrameAffine,
    frame_affine,
    reanchor_coordinates,
    unproject,
)


@dataclass(frozen=True)
class SiteFrame:
    """The run area and the maps between the two frames.

    Attributes
    ----------
    site_lon, site_lat : float
        Origin of the Revit frame, in degrees.
    origin_lon, origin_lat : float
        Origin of the SDK frame (south-west corner of the polygon), in degrees.
    polygon : dict
        GeoJSON polygon of the run area (WGS84, lon/lat).
    size_m : tuple of float
        (east-west, north-south) size of the polygon in SDK metres.
    to_sdk, to_revit : FrameAffine
        The exact affine in each direction.
    """

    site_lon: float
    site_lat: float
    origin_lon: float
    origin_lat: float
    polygon: Dict
    size_m: Tuple[float, float]
    to_sdk: FrameAffine
    to_revit: FrameAffine


def make_frame(
    site_lon: float,
    site_lat: float,
    bbox_m: Sequence[float],
    buffer_m: float,
) -> SiteFrame:
    """Build the frame for a box in the Revit frame, grown by ``buffer_m``.

    Parameters
    ----------
    site_lon, site_lat : float
        Origin of the Revit frame, in degrees.
    bbox_m : sequence of 4 floats
        ``(min_x, min_y, max_x, max_y)`` of the selected buildings, in
        Revit-frame metres.
    buffer_m : float
        Margin added on every side, in metres.
    """
    x0, y0, x1, y1 = bbox_m
    x0, y0, x1, y1 = x0 - buffer_m, y0 - buffer_m, x1 + buffer_m, y1 + buffer_m
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    ring: List[List[float]] = []
    for x, y in corners:
        lon, lat = unproject(site_lon, site_lat, x, y)
        ring.append([lon, lat])
    ring.append(list(ring[0]))
    polygon = {"type": "Polygon", "coordinates": [ring]}
    meters, origin_lon, origin_lat = project_polygon_to_meters(polygon)
    xs = [p[0] for p in meters]
    ys = [p[1] for p in meters]
    return SiteFrame(
        site_lon=site_lon,
        site_lat=site_lat,
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        polygon=polygon,
        size_m=(max(xs) - min(xs), max(ys) - min(ys)),
        to_sdk=frame_affine(site_lon, site_lat, origin_lon, origin_lat),
        to_revit=frame_affine(origin_lon, origin_lat, site_lon, site_lat),
    )


def _move(flat: Sequence[float], affine: FrameAffine) -> np.ndarray:
    """Move a flat ``[x, y, z, ...]`` array through an affine (float64)."""
    if len(flat) == 0:
        return np.zeros(0, dtype=np.float64)
    return np.asarray(reanchor_coordinates(flat, affine), dtype=np.float64)


def points_to_sdk(frame: SiteFrame, flat_xyz: Sequence[float]) -> np.ndarray:
    """Flat Revit-frame ``[x, y, z, ...]`` to the SDK frame."""
    return _move(flat_xyz, frame.to_sdk)


def points_to_revit(frame: SiteFrame, flat_xyz: Sequence[float]) -> np.ndarray:
    """Flat SDK-frame ``[x, y, z, ...]`` to the Revit frame."""
    return _move(flat_xyz, frame.to_revit)


def tile_to_site(positions: np.ndarray, anchor_xy: Sequence[float]) -> np.ndarray:
    """Tile-local f32 positions plus the tile anchor: SDK-frame float64 ``(n, 3)``."""
    xyz = np.asarray(positions, dtype=np.float64).reshape(-1, 3).copy()
    xyz[:, 0] += anchor_xy[0]
    xyz[:, 1] += anchor_xy[1]
    return xyz


def grid_cell_m(bounds: Sequence[float], shape: Tuple[int, int]) -> Tuple[float, float]:
    """Cell size (east-west, north-south), in SDK metres, of a ground grid.

    ``bounds`` is ``(min_lon, min_lat, max_lon, max_lat)`` of the grid and
    ``shape`` is ``(rows, cols)``. The grid starts at the polygon SW corner,
    so the metres of its box are the extent from the same origin.
    """
    min_lon, min_lat, max_lon, max_lat = bounds
    ring = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
    ]
    ring.append(list(ring[0]))
    meters, _, _ = project_polygon_to_meters({"type": "Polygon", "coordinates": [ring]})
    width = max(p[0] for p in meters) - min(p[0] for p in meters)
    height = max(p[1] for p in meters) - min(p[1] for p in meters)
    return width / shape[1], height / shape[0]
