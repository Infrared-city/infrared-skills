"""Target / context building split for the `context-geometry` demo.

`client.buildings.get_area(polygon)` fetches buildings **inside** the polygon
only - so to give the inner AOI realistic surrounding occluders we fetch a
**larger** polygon and split it: buildings whose centroid lies in the inner
AOI are the *target*; the rest are *context* (occluders that cast shadows in
but never receive synthesized sensors).

Buildings come back in the fetched polygon's bbox-SW meter frame, so all the
geometry here lives in **one** frame (the larger polygon's), which is exactly
what we need for a single consistent payload.
"""

from __future__ import annotations

import numpy as np

#: Equirectangular metres-per-degree (fine at single-AOI scale).
_M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(ref_lat: float) -> float:
    return _M_PER_DEG_LAT * float(np.cos(np.radians(ref_lat)))


def expand_polygon(polygon: dict, halo_m: float, ref_lat: float) -> dict:
    """Rectangular polygon = bbox of ``polygon`` grown by ``halo_m`` on each side."""
    ring = polygon["coordinates"][0]
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    dlat = halo_m / _M_PER_DEG_LAT
    dlon = halo_m / _m_per_deg_lon(ref_lat)
    x0, x1 = min(lons) - dlon, max(lons) + dlon
    y0, y1 = min(lats) - dlat, max(lats) + dlat
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


def inner_rect_local(inner: dict, outer: dict, ref_lat: float):
    """``(x0, y0, x1, y1)`` of the ``inner`` polygon in ``outer``'s SW-meter frame."""
    m_lon = _m_per_deg_lon(ref_lat)
    o = outer["coordinates"][0]
    ox, oy = min(p[0] for p in o), min(p[1] for p in o)
    i = inner["coordinates"][0]
    ilons, ilats = [p[0] for p in i], [p[1] for p in i]
    return (
        (min(ilons) - ox) * m_lon,
        (min(ilats) - oy) * _M_PER_DEG_LAT,
        (max(ilons) - ox) * m_lon,
        (max(ilats) - oy) * _M_PER_DEG_LAT,
    )


def split_target_context(buildings: dict, rect):
    """Split ``buildings`` into ``(target_ids, context_ids)`` by centroid in ``rect``.

    ``rect`` = ``(x0, y0, x1, y1)`` in the buildings' local meter frame. Target =
    centroid inside the inner rectangle; context = everything else.
    """
    x0, y0, x1, y1 = rect
    target, context = set(), set()
    for bid, mesh in buildings.items():
        co = np.asarray(mesh["coordinates"], float).reshape(-1, 3)
        cx, cy = co[:, 0].mean(), co[:, 1].mean()
        (target if (x0 <= cx <= x1 and y0 <= cy <= y1) else context).add(bid)
    return target, context


def subset(buildings: dict, ids) -> dict:
    """Return the sub-dict of ``buildings`` whose keys are in ``ids``."""
    ids = set(ids)
    return {k: v for k, v in buildings.items() if k in ids}


def aggregate_means(result: dict) -> dict:
    """``{building_id: mean}`` from a surface result's ``aggregates.buildings``."""
    aggs = (result.get("aggregates") or {}).get("buildings") or {}
    return {bid: a.get("mean") for bid, a in aggs.items() if a.get("mean") is not None}
