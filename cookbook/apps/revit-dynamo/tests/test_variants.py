"""PWC and TCS: labels with a criterion or subtype, requests, class colours and legends."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ir_dynamo import cell_colors, colors, legend_layout, payloads, settings, summary, variants

# Copied from the public colour registry (2026-11-05): one PWC criterion, one TCS subtype.
LDDC = {
    "colors": [[0, 0, 255], [0, 185, 255], [0, 255, 255], [0, 255, 0], [255, 185, 0], [255, 0, 0]],
    "steps": ["A", "B", "C", "D", "E", "S"],
    "stepsNames": ["Frequent Sitting", "Occasional Sitting", "Standing", "Walking",
                   "Business Walking", "Uncomfortable"],
    "colorInterpolation": "binned",
    "legendType": "equal_ranges",
    "resultSubdivisionFactor": 1,
    "barsSubdivisionFactor": 1,
    "legendSubdivisionFactor": 1,
    "legendMaxHandling": "closed",
    "legendMinHandling": "closed",
}  # fmt: skip
HEAT = {
    "colors": [[255, 245, 245], [252, 189, 159], [250, 100, 37], [219, 31, 10], [104, 3, 16]],
    "colorInterpolation": "binned",
    "legendType": "equal_ranges",
    "resultSubdivisionFactor": 3,
    "barsSubdivisionFactor": 2,
    "legendSubdivisionFactor": 2,
    "legendMaxHandling": "closed",
    "legendMinHandling": "closed",
}
VC = {
    "pedestrian-wind-comfort": {"lawson-lddc": LDDC},
    "thermal-comfort-statistics": {"heat-stress": HEAT},
}
PWC_KEY = "pedestrian-wind-comfort/lawson-lddc"


def test_labels_with_a_criterion_or_subtype() -> None:
    row = settings.find_analysis("pwc", "ground")
    assert (row.sdk_type, row.variant, row.label) == ("pedestrian-wind-comfort", "lawson-lddc", "pwc lawson-lddc")
    assert settings.find_analysis("PWC  Lawson_2001", "ground").variant == "lawson-2001"
    assert settings.find_analysis("wind comfort lddc", "ground").variant == "lawson-lddc"
    assert settings.find_analysis("tcs heat", "ground").variant == "heat-stress"
    assert settings.find_analysis("tcs", "ground").full_title == "Thermal comfort statistics (thermal-comfort)"
    assert settings.find_analysis("svf", "ground").variant == ""
    with pytest.raises(ValueError, match="lawson-1970"):
        settings.find_analysis("pwc lawson-99", "ground")
    with pytest.raises(ValueError, match="does not run on facades"):
        settings.find_analysis("pwc", "facades")


def test_pwc_says_when_the_window_is_not_a_whole_year() -> None:
    pwc = settings.find_analysis("pwc", "ground")
    assert settings.window_note(pwc, "1-12", "0-23") == []
    assert "whole year" in settings.window_note(pwc, "6-8", "8-18")[0]
    assert settings.window_note(settings.find_analysis("utci", "ground"), "6-8", "8-18") == []


class WeatherClient:
    """One station; the rows of the asked window, with every weather field set."""

    def __init__(self) -> None:
        self.weather = SimpleNamespace(
            get_weather_file_from_location=lambda **kw: [{"uuid": "station"}],
            filter_weather_data=self._rows,
        )

    @staticmethod
    def _rows(identifier, time_period):
        from infrared_sdk.models import WeatherDataPoint

        days = sum(
            [30, 31, 31][m - 6] for m in range(time_period.start_month, time_period.end_month + 1)
        )
        hours = time_period.end_hour - time_period.start_hour + 1
        fields = dict.fromkeys(WeatherDataPoint.model_fields, 1.0)
        return [
            dict(fields, windSpeed=3.0 + (i % 5), windDirection=float(i * 10 % 360), dryBulbTemperature=22.0)
            for i in range(days * hours)
        ]


def test_pwc_request_has_the_criterion_and_the_wind_series() -> None:
    row = settings.find_analysis("pwc lawson-2001", "ground")
    request = payloads.build_payload(row, "ground", 48.2, 16.37, months="6-6", hours="0-23", client=WeatherClient())
    assert request.criteria == "lawson-2001"
    assert len(request.wind_speed) == len(request.wind_direction) == 30 * 24
    terrain = {"t": {"coordinates": [0.0] * 9, "indices": [0, 1, 2]}}
    lowered = payloads.build_payload(
        row, "ground", 48.2, 16.37, months="6-6", hours="0-23", ground_geometry=terrain, client=WeatherClient()
    )
    assert lowered.terrain_alignment == "to-ground"  # a wind model: no terrain
    assert not getattr(lowered, "ground_geometry", None)


def test_tcs_request_has_the_subtype() -> None:
    row = settings.find_analysis("tcs cold", "ground")
    request = payloads.build_payload(row, "ground", 48.2, 16.37, months="6-6", hours="8-18", client=WeatherClient())
    assert request.subtype == "cold-stress"
    assert request.analysis_type == "thermal-comfort-statistics"


def test_colour_key_and_flatten() -> None:
    assert variants.colour_key("pedestrian-wind-comfort", "lawson-lddc") == PWC_KEY
    assert variants.colour_key("sky-view-factors") == "sky-view-factors"
    flat = variants.flatten(VC, PWC_KEY)
    assert flat[PWC_KEY] is LDDC and variants.is_class_scale(flat, PWC_KEY)
    tcs = variants.flatten(VC, "thermal-comfort-statistics/heat-stress")
    assert not variants.is_class_scale(tcs, "thermal-comfort-statistics/heat-stress")
    assert variants.flatten(VC, "pedestrian-wind-comfort/unknown") is VC


def test_class_legend_cells_and_lines() -> None:
    legend, warnings = colors.make_legend(PWC_KEY, 0, 4, VC, values=[0, 1, 4])
    assert warnings == [] and legend.labels[0] == "A Frequent Sitting"
    assert [b.rgb for b in legend.bins] == [tuple(c) for c in LDDC["colors"]]
    values = [0.0, 0.0, 1.0, 4.0, float("nan")]
    palette, index, notes = cell_colors.cell_colors(PWC_KEY, values, 0, 4, "trimmed", legend, visual_configurations=VC)
    assert notes == [] and palette == [(0, 0, 255), (0, 185, 255), (255, 185, 0), (0, 0, 0)]
    assert index.tolist()[:4] == [0, 0, 1, 2]
    lines = summary.legend_count_lines(legend, values, "class", "trimmed")
    assert lines[1].startswith("  A Frequent Sitting  rgb(0, 0, 255): 2 (50.0 %)")
    _, texts = legend_layout.legend_layout(legend, "Pedestrian wind comfort (lawson-lddc)", "class", "ground")
    assert texts[0].text == "Pedestrian wind comfort (lawson-lddc), ground"
    assert texts[1].text == "A Frequent Sitting" and texts[6].text == "S Uncomfortable"
    again = colors.Legend.from_dict(legend.to_dict())
    assert again.labels == legend.labels


def test_label_check() -> None:
    assert variants.label_check(["A", "B", "C"], ["A x", "B y", "C z", "D"]) == []
    assert variants.label_check([], ["A"]) == []
    assert "report this" in variants.label_check(["B", "A"], ["A x", "B y"])[0]


def test_tcs_takes_its_subtype_colours() -> None:
    key = "thermal-comfort-statistics/heat-stress"
    legend, warnings = colors.make_legend(key, 0.0, 100.0, VC, values=np.linspace(0, 100, 50), range_mode="exact")
    assert legend.source == "registry" and not legend.labels
    # No steps: a smooth gradient, sampled at the middle of each bin, so the end bins
    # are near (not at) the end colours of the heat-stress scale.
    assert len(legend.bins) == 10
    for got, want in ((legend.bins[0].rgb, HEAT["colors"][0]), (legend.bins[-1].rgb, HEAT["colors"][-1])):
        assert max(abs(a - b) for a, b in zip(got, want)) <= 25
