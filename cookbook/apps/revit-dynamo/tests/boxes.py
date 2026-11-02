"""A box as a triangle list, for tests and the live smoke run."""

from __future__ import annotations

from typing import List


def box_soup(
    x0: float, y0: float, z0: float, dx: float, dy: float, dz: float
) -> List[float]:
    """12 triangles (flat xyz list) of a closed box, outward winding."""
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    v = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    faces = [
        (0, 3, 2),
        (0, 2, 1),  # bottom
        (4, 5, 6),
        (4, 6, 7),  # top
        (0, 1, 5),
        (0, 5, 4),  # south
        (1, 2, 6),
        (1, 6, 5),  # east
        (2, 3, 7),
        (2, 7, 6),  # north
        (3, 0, 4),
        (3, 4, 7),  # west
    ]
    out: List[float] = []
    for face in faces:
        for i in face:
            out.extend(v[i])
    return out
