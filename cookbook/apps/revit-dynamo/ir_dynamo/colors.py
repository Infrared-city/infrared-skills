"""The colours and bins of the Infrared platform, for Revit. No Revit import.

The SDK draws result images with the colour registry of the platform (the kernel
function ``render_grid_registry``). This module asks that same renderer how it
colours a ramp of values and turns the answer into legend bins:

1. a 1-row ramp grid (``RAMP_SIZE`` values from low to high) is rendered with
   ``render_grid_image_local``; it stays under the 960 px cap, so it is 1:1;
2. the PNG is decoded (``decode_png``);
3. runs of equal colour are the bins (a "binned" registry scale has a few);
4. ``Legend.bin_of`` gives the bin of each result value.

The kernel draws a scale with registry ``steps`` (UTCI, wind speed) as a few
flat colours, and a scale without ``steps`` (sky view factor, solar radiation,
sun hours, daylight) as a smooth 256-colour gradient although the registry says
"binned". A gradient cannot be 256 Revit materials: it is cut into
``FALLBACK_BINS`` equal bins, each with the platform colour at its middle, and a
line says so.

Range (``RANGE_MODES``, the modes of ``infrared_sdk.legend``):

* ``"trimmed"`` (default in Revit): the 2nd to 98th percentile of the values
  (``legend_range(..., "trimmed")``), so a few extreme cells do not wash out the
  colours and the variation is visible;
* ``"exact"``: the result's own min and max;
* ``"platform"``: what the platform draws. The registry's fixed range
  (``registry_fixed_range``: UTCI, wind speed) when there is one, else the
  trimmed range. Example: wind speed is always 0..20 m/s there, so a 5 m/s
  inflow shows in the three lowest (blue) colours only.

The kernel colours a grid over the registry ``steps`` if the config has them,
else over the 2nd to 98th percentile of the grid's finite cells (SDK 1.0.0
has no key for a fixed range there). So:

* a config with ``steps``: in the two measured modes the ``steps`` of a copy
  are set to the chosen range; the same platform colours spread over it;
* a config without ``steps``: ``pad_values`` adds cells at the range's ends,
  enough that the 2nd and 98th percentile ARE the range ends.

A ramp over the range therefore gets the colours the platform draws for the
data (``tests/test_colors.py`` renders a real data grid and compares).

Offline (the registry cannot be fetched): the old hand-written viridis gradient
in 10 equal bins, and a warning line. The run does not fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .png import decode_png  # noqa: F401  (part of this module's API)

try:  # the SDK is there in a real run; the pure functions work without it
    from infrared_sdk.legend import legend_range, registry_fixed_range
except ImportError:  # pragma: no cover

    def registry_fixed_range(analysis_type: str, variant: Optional[str] = None) -> Any:
        return None

    def legend_range(result: Any, mode: str = "exact", *, fixed: Any = None) -> Any:
        return None


RAMP_SIZE = 512  # under the 960 px cap of the renderer: one pixel per value
MAX_BINS = 32  # a registry scale with more colours is treated as a gradient
FALLBACK_BINS = 10
RANGE_MODES = ("trimmed", "exact", "platform")
DEFAULT_RANGE_MODE = "trimmed"
# Offline fallback, low -> high (viridis stops).
GRADIENT = [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]

# ------------------------------------------------------------------ legend


@dataclass(frozen=True)
class Bin:
    """One legend bin: its colour and the value range it covers (low <= v <= high)."""

    rgb: Tuple[int, int, int]
    low: float
    high: float


@dataclass(frozen=True)
class Legend:
    """The bins of one analysis, low -> high, and the ramp they came from.

    ``ramp_values`` is ascending (``RAMP_SIZE`` values from the range low to high);
    ``ramp_bin[i]`` is the bin of ``ramp_values[i]``.
    """

    analysis_type: str
    bins: List[Bin]
    ramp_values: np.ndarray
    ramp_bin: np.ndarray
    source: str  # "registry" or "fallback"

    def bin_of(self, values: Any) -> np.ndarray:
        """The bin of each value: the nearest ramp position; outside values go to the
        end bins. NaN gets ``-1`` (no bin)."""
        v = np.asarray(values, dtype=np.float64)
        ramp = self.ramp_values
        nan = np.isnan(v)
        pos = np.searchsorted(ramp, np.where(nan, ramp[0], v))
        pos = np.clip(pos, 1, len(ramp) - 1)
        nearer_left = (v - ramp[pos - 1]) <= (ramp[pos] - v)
        pos = np.where(nearer_left, pos - 1, pos)
        out = self.ramp_bin[pos].astype(int)
        out[nan] = -1
        return out

    def to_dict(self) -> Dict[str, Any]:
        """What a saved result needs to be drawn again: the bins and the ramp."""
        return {
            "analysis_type": self.analysis_type,
            "source": self.source,
            "bins": [{"rgb": list(b.rgb), "low": b.low, "high": b.high} for b in self.bins],
            "ramp_values": self.ramp_values.tolist(),
            "ramp_bin": self.ramp_bin.tolist(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Legend":
        return cls(
            analysis_type=str(data.get("analysis_type", "")),
            bins=[Bin(tuple(int(c) for c in b["rgb"]), b["low"], b["high"]) for b in data["bins"]],
            ramp_values=np.asarray(data["ramp_values"], dtype=np.float64),
            ramp_bin=np.asarray(data["ramp_bin"], dtype=int),
            source=str(data.get("source", "registry")),
        )


def pad_values(low: float, high: float, count: int) -> List[float]:
    """Cells to add to a grid of ``count`` values so that a config without
    ``steps`` is coloured over exactly ``low`` .. ``high``.

    The kernel then uses the 2nd and 98th percentile (linear) of all cells. With
    more than 2 % of the cells at each end (``count // 40 + 4`` > 0.021 n + 1),
    those percentiles are ``low`` and ``high``, if the values are clipped to it.
    """
    k = int(count) // 40 + 4
    return [float(low)] * k + [float(high)] * k


def value_colors(
    analysis_type: str,
    low: float,
    high: float,
    visual_configurations: Optional[Dict[str, Any]] = None,
    size: int = RAMP_SIZE,
) -> Tuple[np.ndarray, np.ndarray]:
    """The colour the SDK renderer gives to ``size`` values from ``low`` to ``high``.

    Returns ``(ramp_values, ramp_rgb)``: shapes ``(size,)`` and ``(size, 3)``.
    The ramp is a 1-row grid (plus ``pad_values`` rows for a config without
    ``steps``, so it is coloured over exactly ``low`` .. ``high``).
    """
    from infrared_sdk.layers.image_local import render_grid_image_local

    if size > 900:
        raise ValueError("size must stay under the 960 px cap of the renderer.")
    ramp = np.linspace(float(low), float(high), size)
    grid: List[List[Any]] = [ramp.tolist()]
    config = (visual_configurations or {}).get(analysis_type)
    if isinstance(config, dict) and not config.get("steps"):
        pad: List[Any] = pad_values(low, high, size)
        pad += [None] * (-len(pad) % size)
        grid += [pad[i : i + size] for i in range(0, len(pad), size)]
    png = render_grid_image_local(
        grid=grid,
        analysis_type=analysis_type,
        visual_configurations=visual_configurations,
        max_long_axis_px=0,  # every cell, never resampled
    )
    image = decode_png(png)
    if image.shape[0] != len(grid) or image.shape[1] != size:
        raise ValueError("The rendered ramp has the size %s, not %d x %d." % (image.shape[:2], len(grid), size))
    return ramp, image[0, :, :3].astype(int)


def collapse(ramp: np.ndarray, rgb: np.ndarray) -> Tuple[List[Bin], np.ndarray]:
    """Runs of one colour are bins. Returns ``(bins, ramp_bin)``, bins low -> high.

    The range of a bin is from its first to its last ramp value.
    """
    change = np.any(rgb[1:] != rgb[:-1], axis=1)
    starts = np.concatenate([[0], np.nonzero(change)[0] + 1])
    ends = np.concatenate([starts[1:], [len(ramp)]]) - 1
    ramp_bin = np.zeros(len(ramp), dtype=int)
    bins = []
    for k, (a, b) in enumerate(zip(starts, ends)):
        ramp_bin[a : b + 1] = k
        bins.append(Bin(tuple(int(c) for c in rgb[a]), float(ramp[a]), float(ramp[b])))
    return bins, ramp_bin


def _evenly(ramp: np.ndarray, count: int) -> Tuple[List[Bin], np.ndarray]:
    """``count`` equal bins over the ramp, coloured along the viridis GRADIENT."""
    stops = np.asarray(GRADIENT, dtype=np.float64)
    where = np.linspace(0.0, len(stops) - 1.0, count)
    low = np.floor(where).astype(int).clip(0, len(stops) - 2)
    part = (where - low)[:, None]
    colors = np.rint(stops[low] * (1.0 - part) + stops[low + 1] * part).astype(int)
    ramp_bin = np.minimum((np.arange(len(ramp)) * count) // len(ramp), count - 1)
    bins = []
    for k in range(count):
        mine = ramp[ramp_bin == k]
        bins.append(Bin(tuple(int(c) for c in colors[k]), float(mine[0]), float(mine[-1])))
    return bins, ramp_bin


def fallback_legend(analysis_type: str, low: float, high: float) -> Legend:
    """The old hand-written gradient in 10 equal bins (used when the registry is out)."""
    ramp = np.linspace(low, high, RAMP_SIZE)
    bins, ramp_bin = _evenly(ramp, FALLBACK_BINS)
    return Legend(analysis_type, bins, ramp, ramp_bin, "fallback")


def parse_range_mode(text: Any) -> str:
    """``"trimmed"``, ``"exact"`` or ``"platform"``; empty gives ``DEFAULT_RANGE_MODE``.

    Raises
    ------
    ValueError
        For any other text.
    """
    mode = str(text or "").strip().lower() or DEFAULT_RANGE_MODE
    if mode not in RANGE_MODES:
        raise ValueError("legend must be one of %s, not %r." % (", ".join(RANGE_MODES), text))
    return mode


def _measured_range(
    mode: str, values: Any, low: Optional[float], high: Optional[float]
) -> Tuple[Optional[float], Optional[float]]:
    """The range in a measured mode. The SDK computes the "trimmed" percentiles."""
    if mode == "trimmed" and values is not None and len(values):
        grid = np.asarray(values, dtype=np.float64).reshape(1, -1)
        found = legend_range(grid, "trimmed")
        if found is not None:
            return float(found[0]), float(found[1])
    return low, high


def load_configurations(visual_configurations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The registry ``visualConfigurations`` (fetched and cached by the SDK)."""
    if visual_configurations is not None:
        return visual_configurations
    from infrared_sdk.layers._registry import fetch_visual_configurations

    return fetch_visual_configurations()[0]


def resolve_range(
    analysis_type: str,
    low: Optional[float],
    high: Optional[float],
    values: Any,
    range_mode: str,
    visual_configurations: Dict[str, Any],
) -> Tuple[float, float, Dict[str, Any], List[str]]:
    """The colour range of a result and the registry to render it with.

    Returns ``(low, high, configurations, warning_lines)``. In a measured mode
    (``"trimmed"``, ``"exact"``) a config with ``steps`` gets ``steps = [low,
    high]`` in a copy, so the renderer spreads the same platform colours over
    that range. In ``"platform"`` mode the registry's fixed range wins.

    Raises
    ------
    LookupError
        When the registry has no entry for ``analysis_type``.
    """
    mode = parse_range_mode(range_mode)
    if analysis_type not in visual_configurations:
        raise LookupError("the colour registry has no entry for %r" % analysis_type)
    warnings: List[str] = []
    fixed = registry_fixed_range(analysis_type)
    if mode == "platform" and fixed is not None:
        low, high = fixed
    else:  # the platform colours a scale without a fixed range over the trimmed range
        measured = "trimmed" if mode == "platform" else mode
        low, high = _measured_range(measured, values, low, high)
    if low is None or high is None:
        low, high = 0.0, 1.0
    low, high = float(low), float(high)
    if not high > low:
        high = low + 1.0  # one value only: a range needs a width
    config = visual_configurations[analysis_type]
    if mode != "platform" and isinstance(config, dict) and config.get("steps"):
        config = dict(config, steps=[low, high])
        visual_configurations = dict(visual_configurations, **{analysis_type: config})
    if mode != "platform" and fixed is not None:
        warnings.append(
            "Legend range (%s): %.4g .. %.4g. The platform always uses %.4g .. %.4g; "
            "set legend to platform to see that." % (mode, low, high, fixed[0], fixed[1])
        )
    return low, high, visual_configurations, warnings


def without_steps(configs: Dict[str, Any], analysis_type: str) -> Dict[str, Any]:
    """A copy of the registry with no ``steps`` for ``analysis_type``.

    The renderer then draws a smooth gradient through the platform colours, as it
    does for sky view factor (``gradient``); ``pad_values`` pins its range.
    """
    config = configs.get(analysis_type)
    if not isinstance(config, dict) or "steps" not in config:
        return configs
    config = {k: v for k, v in config.items() if k != "steps"}
    return dict(configs, **{analysis_type: config})


def make_legend(
    analysis_type: str,
    low: Optional[float],
    high: Optional[float],
    visual_configurations: Optional[Dict[str, Any]] = None,
    values: Any = None,
    range_mode: str = "platform",
    gradient: bool = False,
) -> Tuple[Legend, List[str]]:
    """The legend for one result. Returns ``(legend, warning_lines)``.

    ``gradient``: draw a scale with ``steps`` (wind speed, UTCI) as a smooth
    gradient through the same colours, see ``without_steps``.

    ``low``, ``high``: the legend min and max of the result (may be None for an
    empty result). ``values``: the result values, for the ``"trimmed"`` range.
    ``range_mode``: one of ``RANGE_MODES`` (see the module text).
    If the registry cannot be fetched or does not know the analysis, the
    fallback gradient is used and a line says so.
    """
    mode = parse_range_mode(range_mode)
    try:
        configs = load_configurations(visual_configurations)
        low, high, configs, warnings = resolve_range(analysis_type, low, high, values, mode, configs)
        if gradient:
            configs = without_steps(configs, analysis_type)
        ramp, rgb = value_colors(analysis_type, low, high, configs)
        bins, ramp_bin = collapse(ramp, rgb)
        if len(bins) > MAX_BINS:
            bins, ramp_bin = _evenly(ramp, FALLBACK_BINS)
            for k in range(len(bins)):  # keep the registry colour at each bin's middle
                mid = np.nonzero(ramp_bin == k)[0]
                bins[k] = Bin(tuple(int(c) for c in rgb[mid[len(mid) // 2]]), bins[k].low, bins[k].high)
            warnings.append(
                "The platform draws %s as a smooth gradient; the legend shows it in %d bins."
                % (analysis_type, FALLBACK_BINS)
            )
        return Legend(analysis_type, bins, ramp, ramp_bin, "registry"), warnings
    except Exception as error:  # offline, a registry change: never fail the run
        try:
            low, high = _measured_range(mode, values, low, high)
        except Exception:
            pass  # the SDK is not there either: the exact range
        low = 0.0 if low is None else float(low)
        high = low + 1.0 if high is None or not float(high) > low else float(high)
        return fallback_legend(analysis_type, low, high), [
            "Colour registry not available (%s); using the built-in colours, "
            "not the platform colours." % error
        ]
