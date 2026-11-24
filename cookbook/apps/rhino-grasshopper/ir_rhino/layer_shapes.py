"""Triangles that show the trees and the colours of the ground materials. Pure numpy.

A tree is drawn as a trunk (a square prism) and a crown (an 8-sided double
cone, as wide as the crown diameter), the size the SDK uses. Only a picture:
the SDK gets the point, the height and the crown diameter.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

# The colour of each material in the view (RGB).
MATERIAL_RGB: Dict[str, Tuple[int, int, int]] = {
    "asphalt": (70, 70, 75),
    "concrete": (175, 175, 170),
    "soil": (150, 110, 70),
    "vegetation": (110, 170, 90),
    "water": (70, 135, 210),
}
CROWN_RGB = (60, 140, 60)
TRUNK_RGB = (110, 80, 50)
SIDES = 8
TRUNK_SHARE = 0.4  # the crown starts at 40 % of the height


LIGHT = np.array([-0.35, -0.55, 0.76])  # from the south-west, high
SHADES = 12  # grey levels: few colours keep the mesh fast to make


def lit_grey(tri: np.ndarray, grey: Tuple[int, int, int]) -> np.ndarray:
    """``(n, 3)`` RGB per triangle: ``grey`` darker as a face turns from the light.

    A Grasshopper preview draws vertex colours without light; this gives the 3D form.
    The sign of a normal is not trusted (public meshes mix both windings).
    """
    t = np.asarray(tri, dtype=np.float64).reshape(-1, 3, 3)
    normal = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    length = np.linalg.norm(normal, axis=1)
    normal = normal / np.where(length > 0, length, 1.0)[:, None]
    light = LIGHT / np.linalg.norm(LIGHT)
    level = np.round(np.abs(normal @ light) * (SHADES - 1)) / (SHADES - 1)
    factor = 0.55 + 0.45 * level
    return np.clip(np.outer(factor, np.asarray(grey, dtype=np.float64)), 0, 255).astype(np.int64)


def _ring(n: int, radius: np.ndarray) -> np.ndarray:
    """``(len(radius), n, 2)`` points of a circle of each radius."""
    angle = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return radius[:, None, None] * np.stack([np.cos(angle), np.sin(angle)], axis=1)[None]


def _band(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """``(t, 2n, 3, 3)`` triangles between two rings of ``(t, n, 3)`` points."""
    nxt_b, nxt_t = np.roll(bottom, -1, axis=1), np.roll(top, -1, axis=1)
    first = np.stack([bottom, nxt_b, nxt_t], axis=2)
    second = np.stack([bottom, nxt_t, top], axis=2)
    return np.concatenate([first, second], axis=1)


def _fan(ring: np.ndarray, tip: np.ndarray) -> np.ndarray:
    """``(t, n, 3, 3)`` triangles from a ring of ``(t, n, 3)`` points to a ``(t, 3)`` tip."""
    tips = np.repeat(tip[:, None, :], ring.shape[1], axis=1)
    return np.stack([ring, np.roll(ring, -1, axis=1), tips], axis=2)


def tree_triangles(trees: np.ndarray, unit: float) -> Tuple[np.ndarray, np.ndarray]:
    """``(tri, rgb)`` of the trees: ``tri`` ``(k, 3, 3)``, ``rgb`` ``(k, 3)``.

    ``trees`` is ``(t, 5)``: x, y, z of the base, height, crown diameter, all in model
    units. ``unit`` is one metre in model units (the trunk is 0.3 m wide).
    """
    t = np.asarray(trees, dtype=np.float64).reshape(-1, 5)
    if not len(t):
        return np.zeros((0, 3, 3)), np.zeros((0, 3), dtype=np.int64)
    base, height, crown = t[:, :3], t[:, 3], t[:, 4]
    start = base[:, 2] + TRUNK_SHARE * height

    def ring(n: int, radius: np.ndarray, z: np.ndarray) -> np.ndarray:
        xy = base[:, None, :2] + _ring(n, radius)
        return np.concatenate([xy, np.repeat(z[:, None, None], n, axis=1)], axis=2)

    trunk = _band(ring(4, np.full(len(t), 0.15 * unit), base[:, 2]), ring(4, np.full(len(t), 0.15 * unit), start))
    middle = ring(SIDES, crown / 2.0, start + 0.35 * (height - start + base[:, 2]))
    low = base.copy()
    low[:, 2] = start
    high = base.copy()
    high[:, 2] = base[:, 2] + height
    crown_tri = np.concatenate([_fan(middle, low), _fan(middle, high)], axis=1)
    tri = np.concatenate([trunk.reshape(-1, 3, 3), crown_tri.reshape(-1, 3, 3)])
    rgb = np.array([TRUNK_RGB] * trunk.reshape(-1, 3, 3).shape[0] + [CROWN_RGB] * crown_tri.reshape(-1, 3, 3).shape[0])
    return tri, rgb
