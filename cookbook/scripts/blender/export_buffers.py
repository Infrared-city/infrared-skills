"""Save the render buffers of a facade/roof result for `blender_facade_results.py`.

Run this in your SDK environment, not in Blender. One file per analysis. Analyses that ran on
the same geometry and surface grid share one layout, so Blender builds the mesh only once.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np


def save_buffers(
    result,
    path: str | Path,
    building_ids: Iterable[str],
    frame_offset: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Write `result.columns.render_buffers()` to `path` (.npz).

    `building_ids`: the ids you sent in `buildings` (Blender hides these in the context model).
    `frame_offset`: the polygon's south-west corner in YOUR model frame, in metres. The SDK
    returns results in the polygon-SW frame; Blender adds this offset to put them on your model.
    """
    buf = result.columns.render_buffers()
    valid = np.unpackbits(buf.validity, bitorder="little")[: len(buf.values)].astype(
        bool
    )
    np.savez_compressed(
        path,
        anchor=buf.anchor,
        frames=buf.frames,
        dims=buf.dims,
        outline=buf.outline,
        outline_offsets=buf.outline_offsets,
        values=buf.values.astype(np.float32),
        valid=valid,
        frame_offset=np.asarray(frame_offset, dtype=np.float64),
        building_ids=np.asarray(list(building_ids)),
    )
