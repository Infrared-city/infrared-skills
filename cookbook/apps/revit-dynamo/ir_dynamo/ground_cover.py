"""The parts of the selection that lie flat on the ground, for a ground run. No Revit import.

The roads, lawns and ground sheets of an imported city are solids. Sent as SDK
buildings they cover the ground grid, and the ground under a building gets no
value: a tester's city (London Bridge, DWG layers such as
``3DSOLID-MAN_MADE_SURFACE``) had results only around it (2026-11-24).

One element of such an import holds many solids: a whole layer, with the
pavements and, in the same element, a platform on a viaduct. So each element is
cut into its parts (triangles joined by shared vertices, ``parts``); a part with
no point more than ``GROUND_COVER_M`` above the ground is left out of a ground
run, and the rest of the element is sent. The ground result is drawn on top of
the parts that were left out, so their solids in Revit do not hide it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import summary
from . import terrain as terrain_mod

GROUND_COVER_M = 1.0  # a part with no point higher than this above the ground lies on it
WELD_M = 1e-3  # vertices closer than this are one (Revit gives shared edges the same points)

Soup = Dict[str, Sequence[float]]


def parts(tri: np.ndarray) -> np.ndarray:
    """The part of each triangle of ``(n, 3, 3)``: an int label, equal for joined triangles.

    Triangles that share a vertex (within ``WELD_M``) are one part. Label
    propagation with pointer jumping, in numpy (no scipy in the libs folder).
    """
    tri = np.asarray(tri, dtype=np.float64).reshape(-1, 3, 3)
    if len(tri) == 0:
        return np.zeros(0, dtype=np.int64)
    keys = np.round(tri.reshape(-1, 3) / WELD_M).astype(np.int64)
    _, vertex = np.unique(keys, axis=0, return_inverse=True)
    vertex = np.asarray(vertex).reshape(-1, 3)
    label = np.arange(int(vertex.max()) + 1)
    a = np.concatenate([vertex[:, 0], vertex[:, 1]])
    b = np.concatenate([vertex[:, 1], vertex[:, 2]])
    while True:
        low = np.minimum(label[a], label[b])
        new = label.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new = new[new]  # pointer jumping: a label points to the smallest it has seen
        if np.array_equal(new, label):
            return label[vertex[:, 0]]
        label = new


def leave_out(
    soups: Soup,
    sampler: Optional[terrain_mod.Sampler],
    z_offset: float,
) -> Tuple[Soup, float, Optional[terrain_mod.Sampler], List[str]]:
    """The selection without the parts that lie flat on the ground.

    The ground under a point is the terrain (``sampler``), else the higher of
    ``z_offset`` and the lowest point of the selection. If every part is flat,
    nothing is left out and a warning says so.

    Returns ``(soups, draw_z, draw_sampler, lines)``: the soups to send, and where
    to draw the ground result: on the terrain and the flat parts (a sampler of
    both, highest wins), or without terrain at the top of the highest flat part,
    one height, so the cells of one colour can still be joined into one face.
    """
    names = list(soups)
    arrays = [terrain_mod.triangles(soups[n]) for n in names]
    if not arrays:
        return soups, z_offset, sampler, []
    every = np.concatenate(arrays)
    xyz = every.reshape(-1, 3)
    flat_z = z_offset if sampler is not None else max(z_offset, float(xyz[:, 2].min()))
    height = (xyz[:, 2] - terrain_mod.ground_z(sampler, xyz, flat_z)).reshape(-1, 3).max(axis=1)
    out: Dict[str, Sequence[float]] = {}
    cover: List[np.ndarray] = []
    whole: List[str] = []
    partly: List[str] = []
    start = 0
    for name, tri in zip(names, arrays):
        end = start + len(tri)
        label = parts(tri)
        top = np.full(int(label.max()) + 1 if len(label) else 0, -np.inf)
        np.maximum.at(top, label, height[start:end])
        flat = top[label] <= GROUND_COVER_M
        start = end
        if not flat.any():
            out[name] = soups[name]
            continue
        cover.append(tri[flat])
        if flat.all():
            whole.append(str(name))
        else:
            partly.append(str(name))
            out[name] = tri[~flat].reshape(-1).tolist()
    if not cover:
        return soups, z_offset, sampler, []
    if not out:
        return soups, z_offset, sampler, [
            "Warning: every selected element lies flat on the ground (no part more than "
            "%.0f m above it), so they are sent as buildings and cover the ground. Select "
            "the buildings too." % GROUND_COVER_M
        ]
    flat_tri = np.concatenate(cover)
    if sampler is not None:
        draw_z, draw_sampler = z_offset, terrain_mod.Sampler(np.concatenate([sampler.tri, flat_tri]))
    else:
        draw_z, draw_sampler = max(z_offset, float(flat_tri[:, :, 2].max())), None
    lines = [
        "Left out of the ground run, as they lie flat on the ground (no part more than "
        "%.0f m above it; roads, lawns, ground sheets) and as buildings would cover it: "
        "%d triangle(s). The ground result is drawn on top of them." % (GROUND_COVER_M, len(flat_tri))
    ]
    for text, ids in (
        ("whole element(s)", whole),
        ("element(s) in part; the rest of each is sent", partly),
    ):
        if ids:
            lines.append("  " + summary.id_list_line(text, ids))
    return out, draw_z, draw_sampler, lines
