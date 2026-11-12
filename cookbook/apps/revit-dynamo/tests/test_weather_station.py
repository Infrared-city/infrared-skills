"""The Watch line of the weather station (``payloads.station_line``)."""

from __future__ import annotations

from types import SimpleNamespace

from ir_dynamo import payloads, settings
from test_variants import WeatherClient

# A row of the public catalog (2026-11-06), near the Vienna city centre.
VIENNA = {
    "uuid": "d7ea920c-46cc-4f17-ba93-1c59196e65a4",
    "fileName": "AUT_WI_Wien-Innere.Stadt.110340_TMYx.2009-2023",
    "location_data": {
        "city": "Wien-Innere.Stadt", "state": "WI", "country": "AUT",
        "latitude": 48.1983, "longitude": 16.3669, "station_id": "110340",
        "source": "SRC-TMYx", "type": "Location",
    },
}  # fmt: skip


def test_the_line_names_the_station_and_its_distance() -> None:
    line = payloads.station_line(VIENNA, 48.2085, 16.3721)
    assert line == "Weather: station Wien-Innere.Stadt, AUT (110340, TMYx), 1.2 km from the site."


def test_a_far_station_asks_to_check_the_location() -> None:
    line = payloads.station_line(VIENNA, 48.5, 16.3721)  # about 34 km north
    assert "33." in line and "Warning: that is far. Check the project location" in line


def test_a_row_without_location_data_gives_its_file_name() -> None:
    assert payloads.station_line({"uuid": "u", "fileName": "F.epw"}, 0, 0) == "Weather: station F.epw."
    assert payloads.station_line({"uuid": "station"}, 0, 0) == "Weather: station station."


def test_a_weather_analysis_adds_the_line_to_the_notes() -> None:
    client = WeatherClient()
    client.weather = SimpleNamespace(
        get_weather_file_from_location=lambda **kw: [VIENNA],
        filter_weather_data=client.weather.filter_weather_data,
    )
    notes: list = []
    row = settings.find_analysis("utci", "ground")
    payloads.build_payload(row, "ground", 48.2085, 16.3721, months="6-6", hours="8-18", client=client, notes=notes)
    assert notes == ["Weather: station Wien-Innere.Stadt, AUT (110340, TMYx), 1.2 km from the site."]


def test_an_analysis_without_weather_adds_no_line() -> None:
    notes: list = []
    row = settings.find_analysis("daylight", "ground")
    payloads.build_payload(row, "ground", 48.2085, 16.3721, notes=notes)
    assert notes == []
