"""The site frame: Revit metres <-> SDK metres, through the SDK kernel.

Two frames meet here.

* Revit frame: metres, x east, y north (true north), origin = the project
  site location (``site_lon``, ``site_lat``). The Revit side builds it.
* SDK frame: metres, origin = south-west corner of the run polygon.

They are not a plain translation: the east-west scale depends on the latitude
of each origin. The kernel gives the exact affine, so no degree maths is
written here.

NOTE: every kernel call of ir_dynamo is in this file. The functions used
(``infrared_sdk.tiling.reanchor``, ``infrared_sdk.tiling.tiles.TileService`` and
``infrared_sdk.ground_materials.cleaning.project_polygon_to_meters``) are not
documented public API. They are pinned to infrared-sdk 1.0.0. A later SDK
swap touches only this file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
from infrared_sdk.ground_materials.cleaning import project_polygon_to_meters
from infrared_sdk.tiling.tiles import TileService
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


def tile_count(polygon: Dict, analysis_type: str) -> int:
    """The number of tiles (billed jobs) the SDK cuts ``polygon`` into."""
    service = TileService(
        polygon=polygon, logger=logging.getLogger("ir_dynamo"), analysis_type=analysis_type
    )
    return sum(1 for row in service.generate_tiles_for_polygon() for tile in row if not tile.empty)


FILL_REACH_M = 1100.0  # more than two tiles: the search always finds the next tile count
FILL_SAFETY_M = 1.0


def fill_buffer(
    site_lon: float, site_lat: float, bbox_m: Sequence[float], buffer_m: float, analysis_type: str
) -> float:
    """The largest margin that costs the same number of tiles as ``buffer_m``.

    A tile starts at the south-west corner of the run polygon. With a small
    polygon the selection sits in that corner of its tile, and the public
    buildings the SDK reads lie mostly north and east of it. A polygon that
    fills the tile puts the selection in the middle, for the same cost.
    """

    def count(buffer: float) -> int:
        frame = make_frame(site_lon, site_lat, bbox_m, buffer)
        try:
            return tile_count(frame.polygon, analysis_type)
        except ValueError:  # over the tile limit of the SDK
            return -1

    base = count(buffer_m)
    low, high = buffer_m, buffer_m + FILL_REACH_M
    if base < 0 or count(high) == base:
        return buffer_m
    while high - low > 0.5:
        middle = 0.5 * (low + high)
        if count(middle) == base:
            low = middle
        else:
            high = middle
    return max(buffer_m, low - FILL_SAFETY_M)


def point_lonlat(site_lon: float, site_lat: float, x: float, y: float) -> Tuple[float, float]:
    """``(lon, lat)`` of a Revit-frame point (metres east and north of the site)."""
    lon, lat = unproject(site_lon, site_lat, x, y)
    return float(lon), float(lat)


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
    ``shape`` is ``(rows, cols)``. The size is the metre extent of the bounds
    box, from its own SW corner, divided by the number of cells.
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


def grid_corner_sdk(frame: SiteFrame, bounds: Sequence[float]) -> Tuple[float, float]:
    """The SW corner of a ground grid (its ``bounds``) in the SDK frame, in metres.

    The kernel affine from a frame anchored at that corner to the SDK frame
    moves the point (0, 0). Row 0 of the grid is the south edge.
    """
    shift = frame_affine(bounds[0], bounds[1], frame.origin_lon, frame.origin_lat)
    return float(shift.shift_x), float(shift.shift_y)
