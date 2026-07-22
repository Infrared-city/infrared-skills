"""Shared helpers for the Infrared *advanced* direct-API demo notebooks.

These notebooks demonstrate the additive **advanced** simulation inputs that
the public ``infrared-sdk`` Pydantic models do not yet expose:

  * facade / roof sensor synthesis  -- ``analysis-surfaces``
  * bring-your-own sensor grids     -- ``sensor-points`` / ``sensor-normals``
  * terrain occluder / drape        -- ``ground-geometry``
  * occluder-only context geometry  -- ``context-geometry``
  * multi-month / annual windows    -- ``time-period``
  * the UTCI ``physics:"advanced"`` thermal tier

They ride **alongside** the normal model request fields and are sent by
hand-building the async JSON payload and POSTing it to the *same* async
endpoints the SDK uses. The SDK's own wire contract is reused verbatim.

Everything here is self-contained: geometry is fetched through the public
SDK (``client.buildings.get_area`` etc.) and cached **relative to this
file**, so the notebooks run cold for any SDK user with an API key.

Config (env vars, never hard-coded):
  * ``INFRARED_API_KEY``   -- your key (required).
  * ``INFRARED_BASE_URL``  -- optional; defaults to **staging**
    ``https://api-test.infrared.city`` because the advanced features are
    deployed there first. For production use ``https://api.infrared.city/v2``.

Base-URL gotcha (verified live):
  * **staging** ``api-test.infrared.city`` -- routes (data fetch *and* the
    async model endpoints) live at the **host root**; adding ``/v2`` -> 404.
  * **production** ``api.infrared.city/v2`` -- everything is under ``/v2``.

So one base URL drives both the SDK client and the hand-built async POSTs;
``async_base()`` just returns it. Pick the right one for your environment.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import requests

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

#: Vienna Karlsplatz inner AOI -- ~330 m x 200 m, fits in one 512 m solar tile.
VIENNA_KARLSPLATZ: dict = {
    "type": "Polygon",
    "coordinates": [
        [
            [16.3680, 48.2000],
            [16.3710, 48.2000],
            [16.3710, 48.2018],
            [16.3680, 48.2018],
            [16.3680, 48.2000],
        ]
    ],
}

#: AOI centroid -- used for weather lookup and the payload latitude/longitude.
VIENNA_LAT = 48.2009
VIENNA_LON = 16.3695

#: Default to staging (host-root, NO /v2), where advanced features deploy first.
#: Production is "https://api.infrared.city/v2" (everything under /v2).
DEFAULT_BASE_URL = "https://api-test.infrared.city"

_APP_HEADER = {"x-infrared-application": "sdk"}
_CACHE_DIR = Path(__file__).resolve().parent / ".cache"


# --------------------------------------------------------------------------
# Client / auth
# --------------------------------------------------------------------------


def base_url() -> str:
    """Resolve the SDK base URL: ``INFRARED_BASE_URL`` env -> staging default."""
    return os.environ.get("INFRARED_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def api_key() -> str:
    """Read ``INFRARED_API_KEY`` from the environment (never hard-coded)."""
    key = os.environ.get("INFRARED_API_KEY")
    if not key:
        raise RuntimeError(
            "INFRARED_API_KEY is not set. Export it (or put it in a .env file "
            "loaded with python-dotenv) before running this notebook."
        )
    return key


def make_client():
    """Construct an ``InfraredClient`` against the resolved base URL."""
    from infrared_sdk import InfraredClient

    return InfraredClient(api_key=api_key(), base_url=base_url())


def async_base() -> str:
    """Root for the hand-built async POSTs (``{root}/async/{type}``).

    Same shape as the SDK base URL: staging at the host root, prod under
    ``/v2``. (See the base-URL gotcha in the module docstring.)
    """
    return base_url()


# --------------------------------------------------------------------------
# Geometry fetch + cache (relative to this file)
# --------------------------------------------------------------------------


def _cache_path(name: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / name


def _building_to_mesh(b: Any) -> dict:
    """Normalise an SDK building object (or dict) to a dotbim mesh dict."""
    if isinstance(b, dict):
        return {"coordinates": b["coordinates"], "indices": b.get("indices")}
    # Pydantic model from the SDK.
    d = b.model_dump() if hasattr(b, "model_dump") else dict(b)
    return {"coordinates": d["coordinates"], "indices": d.get("indices")}


def fetch_buildings(client, polygon: dict, cache_name: str) -> dict:
    """Fetch buildings for ``polygon`` and return a ``{id: dotbim-mesh}`` dict.

    Result is cached under ``.cache/<cache_name>`` (relative to this module)
    so re-runs are instant and offline. ``coordinates`` are in the
    polygon-bbox-SW meter frame -- exactly the tile-local frame the advanced
    direct-API fields expect.
    """
    p = _cache_path(cache_name)
    if p.exists():
        return json.loads(p.read_text())
    area = client.buildings.get_area(polygon)
    meshes = {bid: _building_to_mesh(b) for bid, b in area.buildings.items()}
    p.write_text(json.dumps(meshes))
    return meshes


def fetch_vegetation(client, polygon: dict, cache_name: str) -> dict:
    """Fetch vegetation (tree) features for ``polygon``; cache + return dict."""
    p = _cache_path(cache_name)
    if p.exists():
        return json.loads(p.read_text())
    try:
        veg = client.vegetation.get_area(polygon)
        features = dict(veg.features)
    except Exception:  # noqa: BLE001 -- vegetation is optional for these demos
        features = {}
    p.write_text(json.dumps(features))
    return features


def fetch_ground_materials(client, polygon: dict, cache_name: str) -> dict:
    """Fetch ground-material layers for ``polygon``; cache + return dict."""
    p = _cache_path(cache_name)
    if p.exists():
        return json.loads(p.read_text())
    try:
        gm = client.ground_materials.get_area(polygon)
        layers = dict(gm.layers)
    except Exception:  # noqa: BLE001 -- ground materials are optional here
        layers = {}
    p.write_text(json.dumps(layers))
    return layers


def fetch_weather_identifier(client) -> str:
    """Return the nearest weather-file identifier for the AOI (Vienna)."""
    locs = client.weather.get_weather_file_from_location(
        lat=VIENNA_LAT, lon=VIENNA_LON, radius=80
    )
    for loc in locs:
        ident = loc.get("identifier") or loc.get("fileName") or loc.get("id")
        if ident:
            return ident
    raise RuntimeError("No weather file found near the AOI.")


# --------------------------------------------------------------------------
# Direct-API async wire contract  (submit -> poll -> fetch results)
# --------------------------------------------------------------------------
#
# Identical to ``infrared_sdk/analyses/jobs.py``:
#   submit  : POST {root}/async/{type}, body = zip(payload.json), CT app/zip
#   poll    : GET  {root}/async/jobs/{job_id}      -> {jobStatus|status, ...}
#   results : GET  {root}/async/jobs/{job_id}/results -> Link header presigned
#   download: GET  presigned (no auth)             -> zip/gzip/raw json


def _hdr() -> dict:
    return {**_APP_HEADER, "x-api-key": api_key()}


def submit(analysis_type: str, payload: dict, timeout=(30, 300)):
    """POST a hand-built payload dict as a zipped ``payload.json``.

    Returns ``(status_code, response_json, job_id_or_None)``.
    """
    url = f"{async_base()}/async/{analysis_type}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("payload.json", json.dumps(payload).encode("utf-8"))
    r = requests.post(
        url,
        data=buf.getvalue(),
        headers={**_hdr(), "Content-Type": "application/zip"},
        timeout=timeout,
    )
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = {"_raw": r.text[:2000]}
    job_id = None
    if isinstance(body, dict):
        job_id = body.get("jobId") or body.get("job_id") or body.get("id")
    return r.status_code, body, job_id


def wait(job_id: str, max_wait=400, on_state: Optional[Callable] = None):
    """Poll ``{root}/async/jobs/{job_id}`` until terminal.

    Returns ``(final_status, last_body, elapsed_s)``. Terminal statuses are
    ``Succeeded`` / ``Failed``; everything else is transient.
    """
    t0 = time.perf_counter()
    delay, last = 1.0, None
    while time.perf_counter() - t0 < max_wait:
        r = requests.get(
            f"{async_base()}/async/jobs/{job_id}", headers=_hdr(), timeout=(30, 120)
        )
        last = r.json() if r.content else {}
        status = (
            last.get("jobStatus") or last.get("status")
            if isinstance(last, dict)
            else None
        )
        if on_state:
            on_state(status)
        if status and status.lower() in ("succeeded", "failed"):
            return status, last, round(time.perf_counter() - t0, 1)
        time.sleep(delay)
        delay = min(delay * 1.5, 8.0)
    return "timeout", last, round(time.perf_counter() - t0, 1)


def fetch_results(job_id: str):
    """GET the presigned ``Link`` URL and download + decompress the result."""
    r = requests.get(
        f"{async_base()}/async/jobs/{job_id}/results", headers=_hdr(), timeout=(10, 120)
    )
    r.raise_for_status()
    presigned = r.headers.get("Link", "").strip("<>")
    if not presigned:
        raise RuntimeError(f"no Link header (status={r.status_code})")
    content = requests.get(presigned, timeout=(10, 600)).content
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return json.loads(zf.read(zf.namelist()[0]))
    if content[:2] == b"\x1f\x8b":
        return json.loads(gzip.decompress(content))
    return json.loads(content)


def run_job(
    analysis_type: str, payload: dict, max_wait=400, label: str = "", quiet=False
):
    """Full submit -> poll -> fetch helper. Returns ``(result_dict, info)``.

    ``info`` carries ``submit_status``, ``final_status``, ``elapsed_s`` and,
    on failure, an ``error`` string. On a non-202 submit or non-Succeeded
    job, ``result_dict`` is ``None`` and the reason is in ``info``.
    """
    tag = f"[{analysis_type}/{label}] " if label else f"[{analysis_type}] "
    code, resp, job_id = submit(analysis_type, payload)
    info = {"submit_status": code, "job_id": job_id}
    if code >= 400:
        err = (
            (resp.get("detail") or resp.get("message") or json.dumps(resp)[:300])
            if isinstance(resp, dict)
            else str(resp)[:300]
        )
        info["error"] = err
        if not quiet:
            print(f"{tag}submit {code}: {err}")
        return None, info
    if not job_id:
        info["error"] = f"submit {code} but no job id in response"
        if not quiet:
            print(f"{tag}{info['error']}")
        return None, info
    status, last, elapsed = wait(job_id, max_wait=max_wait)
    info["final_status"] = status
    info["elapsed_s"] = elapsed
    if status != "Succeeded":
        info["error"] = (
            json.dumps(last)[:300] if isinstance(last, dict) else str(last)[:300]
        )
        if not quiet:
            print(f"{tag}{status} after {elapsed}s")
        return None, info
    result = fetch_results(job_id)
    if not quiet:
        keys = (
            sorted(result.keys()) if isinstance(result, dict) else type(result).__name__
        )
        sc = result.get("sensor-count") if isinstance(result, dict) else None
        print(
            f"{tag}Succeeded in {elapsed}s  keys={keys}"
            + (f"  sensors={sc}" if sc else "")
        )
    return result, info


# --------------------------------------------------------------------------
# Surface-result reconstruction  (frame -> world-space colored triangles)
# --------------------------------------------------------------------------
#
# Post-PR-#120 the worker serialises the exact clipped footprint of every kept
# cell as ``cell-tris`` -- a list aligned 1:1 with ``values`` (same length =
# ``nu*nv``, ``None`` exactly where ``values`` is ``None``). Each non-null entry
# is a flat ``[x,y,z, x,y,z, ...]`` list of triangle-fan vertices in **world
# coordinates** (``len % 9 == 0``: 3 vertices x 3 coords per triangle).
# ``cell-area`` (∈ (0,1] per kept cell, also 1:1 with ``values``) gives the
# in-surface area fraction. Rendering straight from ``cell-tris`` gives smooth
# boundary-clipped cells with no index math, no half-cell offset, and no
# value-transpose risk: the triangles ARE the cell.


def _frame_axes(f: dict):
    """``(origin, u_unit, v_unit, normal, grid-size)`` or ``None`` if degenerate."""
    o = np.asarray(f["origin"], float)
    u = np.asarray(f["u-axis"], float)
    v = np.asarray(f["v-axis"], float)
    gs = float(f.get("grid-size", 4.0))
    if not (
        np.all(np.isfinite(o)) and np.all(np.isfinite(u)) and np.all(np.isfinite(v))
    ):
        return None
    lu, lv = np.linalg.norm(u), np.linalg.norm(v)
    if lu < 1e-6 or lv < 1e-6 or not np.isfinite(gs) or gs <= 0:
        return None
    nrm = np.cross(u, v)
    ln = np.linalg.norm(nrm)
    nrm = nrm / ln if ln > 1e-9 else np.array([0.0, 0.0, 1.0])
    return o, u / lu, v / lv, nrm, gs


def _cell_tris_to_tris(flat, o, nrm, gs):
    """Flat ``[x,y,z,...]`` (``len % 9 == 0``) -> list of ``(3,3)`` triangles.

    Rejects the frame's cell (returns ``None``) if a triangle has an edge much
    longer than the grid pitch, or a vertex sitting implausibly far off the
    frame plane -- the spikes that came from corrupt frames.
    """
    arr = np.asarray(flat, float)
    if arr.size == 0 or arr.size % 9 != 0 or not np.all(np.isfinite(arr)):
        return None
    tris = arr.reshape(-1, 3, 3)
    max_edge = 4.0 * gs + 1.0
    e = np.concatenate(
        [
            np.linalg.norm(tris[:, 1] - tris[:, 0], axis=1),
            np.linalg.norm(tris[:, 2] - tris[:, 1], axis=1),
            np.linalg.norm(tris[:, 0] - tris[:, 2], axis=1),
        ]
    )
    if e.size == 0 or np.max(e) > max_edge:
        return None
    d = (tris.reshape(-1, 3) - o) @ nrm
    if np.max(np.abs(d)) > max_edge:
        return None
    return list(tris)


def reconstruct_cells(surfaces: dict):
    """Turn an ``analysis-surfaces`` result into a world-space triangle soup.

    Renders each kept cell from its exact **clipped** footprint (``cell-tris``,
    post-PR-#120) so boundary cells are real polygons, not full squares. Falls
    back to the full grid quad only for a cell that has no usable ``cell-tris``
    (e.g. an older frame). Frame iteration uses the wire order
    ``k = iv*nu + iu`` (``iv`` outer, ``iu`` inner) and treats ``origin`` as the
    **cell-(0,0) centre** for the fallback quad.

    Returns ``(tris, values, normals)``:
      * ``tris``    -- ``(T, 3, 3)`` world-space triangle vertices,
      * ``values``  -- ``(T,)`` per-triangle value (its cell's value),
      * ``normals`` -- ``(T, 3)`` per-triangle frame-plane normal (for shading).
    These feed straight into :func:`ir_render.surface_mesh`.
    """
    tri_list, tri_val, tri_nrm = [], [], []
    for f in surfaces.values():
        ax = _frame_axes(f)
        if ax is None:
            continue
        o, u, v, nrm, gs = ax
        nu, _ = int(f["nu"]), int(f["nv"])
        vals = f["values"]
        ctris = f.get("cell-tris")
        du, dv = u * gs, v * gs
        for idx, val in enumerate(vals):
            if val is None:
                continue
            polys = None
            if isinstance(ctris, list) and idx < len(ctris) and ctris[idx] is not None:
                polys = _cell_tris_to_tris(ctris[idx], o, nrm, gs)
            if polys is None:
                # fallback: full grid quad. Wire order is iv-outer / iu-inner;
                # origin is the cell-(0,0) CENTRE, so corners are +-0.5 cell.
                iv, iu = divmod(idx, nu)
                c = o + iu * du + iv * dv
                p00 = c - 0.5 * du - 0.5 * dv
                p10 = c + 0.5 * du - 0.5 * dv
                p11 = c + 0.5 * du + 0.5 * dv
                p01 = c - 0.5 * du + 0.5 * dv
                polys = [np.array([p00, p10, p11]), np.array([p00, p11, p01])]
            for t in polys:
                tri_list.append(t)
                tri_val.append(val)
                tri_nrm.append(nrm)
    if not tri_list:
        return (np.zeros((0, 3, 3)), np.zeros((0,)), np.zeros((0, 3)))
    return (
        np.asarray(tri_list, float),
        np.asarray(tri_val, float),
        np.asarray(tri_nrm, float),
    )


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------


def building_triangles(mesh: dict):
    """``(coords Nx3, tris Mx3)`` for a dotbim mesh, or ``None`` if no indices."""
    co = np.asarray(mesh["coordinates"], float).reshape(-1, 3)
    idx = mesh.get("indices")
    if not idx:
        return None
    return co, np.asarray(idx, int).reshape(-1, 3)


def building_faces(buildings: dict, max_buildings: int = 400):
    """Flat list of triangle corner arrays for a light grey context render."""
    faces = []
    for mesh in list(buildings.values())[:max_buildings]:
        bt = building_triangles(mesh)
        if bt is None:
            continue
        co, tris = bt
        faces.extend(co[t] for t in tris)
    return faces


def aoi_bounds_local(polygon: dict, ref_lat: float = VIENNA_LAT):
    """Approx local-meter bbox of a lon/lat polygon, relative to its SW corner.

    Buildings come back in the polygon-bbox-SW meter frame, so this gives the
    matching extent for axis limits. Uses an equirectangular approximation
    (fine at single-tile scale).
    """
    ring = polygon["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(ref_lat))
    w = (max(lons) - min(lons)) * m_per_deg_lon
    h = (max(lats) - min(lats)) * m_per_deg_lat
    return float(w), float(h)
