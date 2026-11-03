"""The colour of each result cell, drawn by the SDK renderer. No Revit import.

The SDK gives no "value -> colour" function; it renders a grid to a PNG
(``render_grid_image_local``, the kernel's ``render_grid_registry``). So the
result itself is rendered and each cell takes its own pixel:

* ground: the result matrix as it came from the SDK (``grid_shape`` and the
  ``row`` / ``col`` of each value). The top image row is grid row 0 (SDK docs).
* facades (or a saved result without its matrix): the values in a square grid.
  The renderer colours each cell by its value and the grid's range only, so the
  layout does not change a colour.

The image is uncapped (``max_long_axis_px=0``): one pixel per cell, never
resampled. The range comes from ``colors.resolve_range``: in the measured modes
the values are clipped to it before rendering, so the renderer's own min and
max are that range.

Then ``palette`` lists the distinct colours and ``index`` gives each value its
colour in it: one Revit material per colour.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import colors
from .png import decode_png


def _layout(
    count: int, grid_shape: Optional[Sequence[int]], cells: Optional[Sequence[Sequence[int]]]
) -> Tuple[int, int, np.ndarray, np.ndarray]:
    """``(rows, cols, row, col)``: where each value sits in the grid to render."""
    if grid_shape is not None and cells is not None and len(cells) == count:
        rc = np.asarray(cells, dtype=np.int64).reshape(-1, 2)
        return int(grid_shape[0]), int(grid_shape[1]), rc[:, 0], rc[:, 1]
    side = max(1, int(math.ceil(math.sqrt(count))))
    flat = np.arange(count)
    return int(math.ceil(count / side)) or 1, side, flat // side, flat % side


def render_values(
    values: Any,
    analysis_type: str,
    configs: Dict[str, Any],
    grid_shape: Optional[Sequence[int]] = None,
    cells: Optional[Sequence[Sequence[int]]] = None,
    pad: Optional[Tuple[float, float]] = None,
) -> np.ndarray:
    """The SDK colour of each value: ``(n, 3)`` ints. NaN values get no colour (0, 0, 0).

    ``pad = (low, high)`` adds ``colors.pad_values`` cells below the grid, so a
    config without ``steps`` is coloured over exactly that range (the renderer
    uses the 2nd and 98th percentile of the cells). They are not in the answer.
    """
    from infrared_sdk.layers.image_local import render_grid_image_local

    v = np.asarray(values, dtype=np.float64)
    rows, cols, row, col = _layout(len(v), grid_shape, cells)
    grid: List[List[Optional[float]]] = [[None] * cols for _ in range(rows)]
    for r, c, x in zip(row.tolist(), col.tolist(), v.tolist()):
        grid[r][c] = None if math.isnan(x) else x
    if pad is not None:
        flat: List[Optional[float]] = list(colors.pad_values(pad[0], pad[1], len(v)))
        flat += [None] * (-len(flat) % cols)
        grid += [flat[i : i + cols] for i in range(0, len(flat), cols)]
    png = render_grid_image_local(
        grid=grid,
        analysis_type=analysis_type,
        visual_configurations=configs,
        max_long_axis_px=0,  # one pixel per cell
    )
    image = decode_png(png)
    if image.shape[0] != len(grid) or image.shape[1] != cols:
        raise ValueError(
            "The SDK image is %d x %d, not the grid's %d x %d."
            % (image.shape[0], image.shape[1], len(grid), cols)
        )
    rgb = image[row, col, :3].astype(int)
    rgb[np.isnan(v)] = 0
    return rgb


def cell_colors(
    analysis_type: str,
    values: Any,
    low: Optional[float],
    high: Optional[float],
    range_mode: str,
    legend: colors.Legend,
    grid_shape: Optional[Sequence[int]] = None,
    cells: Optional[Sequence[Sequence[int]]] = None,
    visual_configurations: Optional[Dict[str, Any]] = None,
    gradient: bool = False,
) -> Tuple[List[Tuple[int, int, int]], np.ndarray, List[str]]:
    """``(palette, index, warning_lines)`` for the values of one result.

    ``palette``: the distinct colours, low value first. ``index[i]``: the colour
    of ``values[i]`` in it. If the SDK renderer cannot be used (offline, an
    analysis without a registry entry), each value takes the colour of its
    ``legend`` bin and a line says so. ``gradient``: see ``colors.without_steps``;
    a scale without ``steps`` gets its values clipped to the range, which is
    pinned with ``pad``.
    """
    v = np.asarray(values, dtype=np.float64)
    mode = colors.parse_range_mode(range_mode)
    try:
        configs = colors.load_configurations(visual_configurations)
        lo, hi, configs, _ = colors.resolve_range(analysis_type, low, high, v, mode, configs)
        if gradient:
            configs = colors.without_steps(configs, analysis_type)
        stepped = bool(configs[analysis_type].get("steps"))
        pad = None if stepped else (lo, hi)  # pin the range of a gradient scale
        drawn = v if mode == "platform" and stepped else np.clip(v, lo, hi)  # NaN stays NaN
        rgb = render_values(drawn, analysis_type, configs, grid_shape, cells, pad)
        note = []
    except Exception as error:  # never fail the drawing for the colours
        bins = np.maximum(legend.bin_of(v), 0)
        rgb = np.asarray([legend.bins[k].rgb for k in bins], dtype=int).reshape(-1, 3)
        note = ["Cell colours: the SDK renderer was not used (%s); legend colours." % error]
    if len(rgb) == 0:
        return [], np.zeros(0, dtype=int), note
    palette, index = np.unique(rgb, axis=0, return_inverse=True)
    index = np.asarray(index).reshape(-1)
    # Order the palette from low to high value (the mean value of each colour).
    mean = np.array([np.nanmean(v[index == k]) if np.any(index == k) else 0.0 for k in range(len(palette))])
    order = np.argsort(np.nan_to_num(mean))
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return [tuple(int(c) for c in palette[k]) for k in order], rank[index], note
