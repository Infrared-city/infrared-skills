"""Illustrative terrain generation for the `ground-geometry` demo.

The Infrared SDK does **not** expose a DEM / terrain fetch, and these public
demos must run cold without external data. So for the `ground-geometry`
notebook we **synthesize** a believable terrain mesh over the AOI bbox: a
gentle plane tilt plus a couple of low-frequency sine bumps. It is clearly
labelled *illustrative* - swap in a real DEM (e.g. from Copernicus / SRTM,
re-projected to the tile-local meter frame) for a production study.

The output is a dotbim mesh dict ``{id: {coordinates, indices}}`` in the same
tile-local meter frame as the fetched buildings, ready to drop into a payload
as ``ground-geometry``.
"""

from __future__ import annotations

import numpy as np


def generate_terrain(
    *,
    size_m: float = 512.0,
    n: int = 40,
    slope: tuple = (0.03, 0.015),
    bumps=((1.0, 7.0), (1.5, 4.0)),
    z0: float = 0.0,
    seed: int = 7,
    mesh_id: str = "terrain0",
):
    """Generate an illustrative terrain mesh over ``[0, size_m]^2``.

    Parameters
    ----------
    size_m : float
        Square extent (m). Cover the whole 512 m tile by default.
    n : int
        Grid resolution per side (``n*n`` vertices, ``2*(n-1)^2`` triangles).
    slope : (sx, sy)
        Linear tilt gradients (m rise per m), giving a gentle overall slope.
    bumps : sequence of (amplitude_m, wavelength_fraction)
        Low-frequency sine bumps; wavelength = fraction * size_m.
    z0 : float
        Base elevation offset (m).
    seed : int
        RNG seed for a touch of smooth noise.

    Returns
    -------
    (mesh, heights) : (dict, (n, n) array)
        ``mesh`` is ``{mesh_id: {"coordinates": [...], "indices": [...]}}``;
        ``heights`` is the elevation grid for plotting / sampling.
    """
    rng = np.random.default_rng(seed)
    xs = np.linspace(0.0, size_m, n)
    ys = np.linspace(0.0, size_m, n)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")

    z = np.full_like(gx, z0, dtype=float)
    z += slope[0] * gx + slope[1] * gy
    for amp, wl_frac in bumps:
        wl = wl_frac * size_m
        z += amp * np.sin(2 * np.pi * gx / wl) * np.cos(2 * np.pi * gy / wl)
    # smooth low-frequency noise (one blurred random field)
    noise = rng.standard_normal((n, n))
    k = np.array([0.25, 0.5, 0.25])
    for _ in range(3):  # separable smoothing passes
        noise = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 0, noise)
        noise = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 1, noise)
    z += 1.2 * noise

    # Flatten to a vertex list and build the triangle index list.
    coords = []
    for i in range(n):
        for j in range(n):
            coords.extend([float(gx[i, j]), float(gy[i, j]), float(z[i, j])])

    def vid(i, j):
        return i * n + j

    indices = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            indices.extend([a, b, c, a, c, d])

    mesh = {mesh_id: {"coordinates": coords, "indices": indices}}
    return mesh, z


def sample_height(
    heights: np.ndarray, x: float, y: float, size_m: float = 512.0
) -> float:
    """Nearest-vertex terrain height at local ``(x, y)`` (for placing things)."""
    n = heights.shape[0]
    i = int(round(np.clip(x / size_m, 0, 1) * (n - 1)))
    j = int(round(np.clip(y / size_m, 0, 1) * (n - 1)))
    return float(heights[i, j])
