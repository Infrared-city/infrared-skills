"""ir_dynamo.colors: PNG decoder, bins from the real SDK renderer, bin_of, range choice.

No network: the registry config is a copy (``VC``) passed as ``visual_configurations``.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest

from ir_dynamo import colors
from ir_dynamo.settings import parse_hours

pytest.importorskip("infrared_sdk")
from infrared_sdk.layers.image_local import render_grid_image_local  # noqa: E402


def _config(rgb, steps=None):
    config = {
        "colors": rgb,
        "colorInterpolation": "binned",
        "legendType": "equal_ranges",
        "resultSubdivisionFactor": 3,
        "barsSubdivisionFactor": 2,
        "legendSubdivisionFactor": 2,
        "legendMaxHandling": "closed",
        "legendMinHandling": "closed",
    }
    if steps:
        config["steps"] = steps
    return config


# Copied from the public colour registry (version 1.6.1).
VC = {
    "sky-view-factors": _config(
        [[8, 64, 129], [43, 140, 190], [124, 204, 196], [204, 235, 198], [247, 252, 240]]
    ),
    "solar-radiation": _config(
        [[75, 107, 169], [170, 200, 247], [245, 239, 103], [239, 156, 21], [234, 38, 0]]
    ),
    "direct-sun-hours": _config(
        [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]]
    ),
    "thermal-comfort-index": _config(
        [
            [0, 0, 3],
            [43, 17, 94],
            [113, 31, 129],
            [182, 54, 121],
            [240, 96, 93],
            [254, 175, 120],
            [251, 252, 191],
        ],
        steps=[-40, 46],
    ),
}


def _png(rows, color=2, filters=None):
    """A PNG built by hand (rows of RGB tuples), each row with a chosen filter."""
    channels = 3 if color == 2 else 4
    h, w = len(rows), len(rows[0])
    raw, prev = b"", bytes(w * channels)
    for y, row in enumerate(rows):
        line = bytes(c for px in row for c in px)
        kind = (filters or [0] * h)[y]
        out = bytearray()
        for i, v in enumerate(line):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if kind == 0:
                p = 0
            elif kind == 1:
                p = a
            elif kind == 2:
                p = b
            elif kind == 3:
                p = (a + b) >> 1
            else:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            out.append((v - p) & 255)
        raw += bytes([kind]) + bytes(out)
        prev = line

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    head = struct.pack(">IIBBBBB", w, h, 8, color, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", head)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_decoder_reads_all_five_filter_types() -> None:
    rng = np.random.RandomState(1)
    rows = [[tuple(int(v) for v in rng.randint(0, 256, 3)) for _ in range(7)] for _ in range(5)]
    image = colors.decode_png(_png(rows, filters=[0, 1, 2, 3, 4]))
    assert image.shape == (5, 7, 3)
    assert image.tolist() == [[list(px) for px in row] for row in rows]


def test_decoder_refuses_what_it_does_not_read() -> None:
    good = _png([[(1, 2, 3)]])
    with pytest.raises(ValueError, match="signature"):
        colors.decode_png(b"nope")
    with pytest.raises(ValueError, match="checksum"):
        colors.decode_png(good[:-5] + b"\x00" + good[-4:])
    with pytest.raises(ValueError):
        colors.decode_png(good[:30])
    # 16-bit: patch the IHDR depth and its checksum.
    body = bytearray(good[16:29])
    body[8] = 16
    crc = struct.pack(">I", zlib.crc32(b"IHDR" + bytes(body)) & 0xFFFFFFFF)
    sixteen = good[:16] + bytes(body) + crc + good[33:]
    with pytest.raises(ValueError, match="8-bit RGB"):
        colors.decode_png(sixteen)


def test_decoder_reads_the_real_renderer_png() -> None:
    png = render_grid_image_local(
        grid=[[0.0, 50.0, 100.0], [100.0, None, 0.0]],
        analysis_type="sky-view-factors",
        visual_configurations=VC,
        max_long_axis_px=0,
    )
    image = colors.decode_png(png)
    assert image.shape == (2, 3, 4)  # RGBA
    assert image[1, 1, 3] == 0  # the no-data cell is transparent
    assert image[0, 0, :3].tolist() == [8, 64, 129]  # lowest bin: first registry colour


@pytest.mark.parametrize(
    "analysis_type, low, high, flat",
    [
        ("thermal-comfort-index", -20.0, 45.0, True),  # registry steps: a few flat colours
        ("sky-view-factors", 0.0, 100.0, False),  # no steps: the kernel draws a gradient
        ("solar-radiation", 0.0, 300.0, False),
        ("direct-sun-hours", 0.0, 12.0, False),
    ],
)
def test_distinct_colours_and_the_legend_bins(monkeypatch, analysis_type, low, high, flat) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: None)
    ramp, rgb = colors.value_colors(analysis_type, low, high, VC)
    bins, ramp_bin = colors.collapse(ramp, rgb)
    print(analysis_type, "distinct colours:", len(bins))
    assert len({b.rgb for b in bins}) == len(bins)  # runs, so low -> high, no repeats
    assert (len(bins) <= 8) == flat
    legend, warnings = colors.make_legend(analysis_type, low, high, VC)
    if flat:
        assert legend.bins == bins and not warnings
    else:  # cut into equal bins with the platform colour at each bin's middle
        assert len(legend.bins) == colors.FALLBACK_BINS and warnings
        middle = np.nonzero(legend.ramp_bin == 0)[0]
        assert legend.bins[0].rgb == tuple(rgb[middle[len(middle) // 2]])
    assert legend.bins[0].low == low and legend.bins[-1].high == high


def test_collapse_ranges_and_order() -> None:
    ramp = np.arange(6.0)
    rgb = np.array([[1, 1, 1]] * 2 + [[2, 2, 2]] * 3 + [[3, 3, 3]])
    bins, ramp_bin = colors.collapse(ramp, rgb)
    assert [(b.rgb, b.low, b.high) for b in bins] == [
        ((1, 1, 1), 0.0, 1.0),
        ((2, 2, 2), 2.0, 4.0),
        ((3, 3, 3), 5.0, 5.0),
    ]
    assert ramp_bin.tolist() == [0, 0, 1, 1, 1, 2]


def _legend(low=0.0, high=100.0, analysis_type="sky-view-factors"):
    legend, _warnings = colors.make_legend(analysis_type, low, high, VC)
    assert legend.source == "registry"
    return legend


def test_bin_of_edges_clipping_and_nan(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: None)
    legend = _legend()
    last = len(legend.bins) - 1
    got = legend.bin_of([-50.0, 0.0, 100.0, 500.0, np.nan])
    assert got.tolist() == [0, 0, last, last, -1]
    # Monotone in the value, and every bin is reached.
    sweep = legend.bin_of(np.linspace(0, 100, 1001))
    assert (np.diff(sweep) >= 0).all() and set(sweep.tolist()) == set(range(last + 1))
    # A value at a bin's own range lands in that bin.
    for k, b in enumerate(legend.bins):
        assert legend.bin_of([b.low, b.high]).tolist() == [k, k]


@pytest.mark.parametrize(
    "analysis_type, fixed, data_low, data_high",
    [
        ("sky-view-factors", None, 3.0, 97.0),
        ("direct-sun-hours", None, 0.0, 9.5),
        ("solar-radiation", None, 12.0, 280.0),
        ("thermal-comfort-index", (-40.0, 46.0), -5.0, 38.0),  # data narrower than steps
    ],
)
def test_ramp_colours_match_what_the_renderer_draws_for_real_data(
    monkeypatch, analysis_type, fixed, data_low, data_high
) -> None:
    """The proof that the ramp range is the kernel's range: colour a data grid with
    the renderer and compare every cell with the ramp colour at its value."""
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: fixed)
    rng = np.random.RandomState(7)
    data = rng.uniform(data_low, data_high, (40, 50))
    data[0, 0], data[0, 1] = data_low, data_high  # the grid's own min and max
    low, high = fixed if fixed else (data_low, data_high)
    ramp, ramp_rgb = colors.value_colors(analysis_type, low, high, VC)
    png = render_grid_image_local(
        grid=data.tolist(),
        analysis_type=analysis_type,
        visual_configurations=VC,
        max_long_axis_px=0,
    )
    image = colors.decode_png(png)[:, :, :3].astype(int)
    nearest = np.abs(ramp[None, None, :] - data[:, :, None]).argmin(axis=2)
    off = np.abs(image - ramp_rgb[nearest]).max(axis=2)
    # A gradient may differ by a rounding step; a flat scale only at a bin edge.
    assert (off > 6).mean() < 0.01, (off > 6).mean()
    # And the legend bin colour is the ramp colour at the bin: same range, same bins.
    legend, _ = colors.make_legend(analysis_type, data_low, data_high, VC)
    assert legend.ramp_values[0] == low and legend.ramp_values[-1] == high


def test_fixed_range_wins_over_the_result_range(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: (-40.0, 46.0))
    legend, _ = colors.make_legend("thermal-comfort-index", 10.0, 20.0, VC)
    assert legend.ramp_values[0] == -40.0 and legend.ramp_values[-1] == 46.0
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: None)
    legend, _ = colors.make_legend("sky-view-factors", 10.0, 20.0, VC)
    assert legend.ramp_values[0] == 10.0 and legend.ramp_values[-1] == 20.0


def test_offline_falls_back_to_the_gradient_with_a_warning(monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr("infrared_sdk.layers._registry.fetch_visual_configurations", broken)
    legend, warnings = colors.make_legend("sky-view-factors", 0.0, 50.0)
    assert legend.source == "fallback" and len(legend.bins) == colors.FALLBACK_BINS
    assert legend.bins[0].rgb == colors.GRADIENT[0] and legend.bins[-1].rgb == colors.GRADIENT[-1]
    assert warnings and "no network" in warnings[0]
    assert legend.bin_of([0.0, 49.9, 50.0]).tolist() == [0, 9, 9]


def test_unknown_analysis_type_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: None)
    legend, warnings = colors.make_legend("no-such-analysis", 0.0, 1.0, VC)
    assert legend.source == "fallback" and warnings


def test_legend_round_trips_through_a_dict_and_names_materials(monkeypatch) -> None:
    monkeypatch.setattr(colors, "registry_fixed_range", lambda *a, **k: None)
    legend = _legend()
    again = colors.Legend.from_dict(legend.to_dict())
    assert again.bins == legend.bins
    assert again.bin_of([10.0, 90.0]).tolist() == legend.bin_of([10.0, 90.0]).tolist()
    assert colors.material_name(legend, 0) == "Infrared svf 01"
    assert colors.legend_lines(legend, "%")[0].startswith("  Infrared svf 01  rgb(")


def test_one_hour_is_accepted_and_ranges_still_work() -> None:
    assert parse_hours("13") == (13, 13)
    assert parse_hours(" 9 - 17 ") == (9, 17)
    assert parse_hours("9..17") == (9, 17)
    for bad in ("", "a", "25", "17-9", "1-2-3"):
        with pytest.raises(ValueError):
            parse_hours(bad)
