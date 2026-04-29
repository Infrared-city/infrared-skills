"""Predefined city polygons for the public Infrared SDK demos.

Each city has two polygons:

  - ``POLYGON_SMALL``: ~150 m x 150 m square around the city centre.
    Fits in a single solar inference tile (512 m). Cheap and fast to run.
  - ``POLYGON_LARGE``: irregular pentagon ~ 1 km wide, drawn to span
    multiple tiles (4-6 tiles, depending on alignment). Used for tiling
    demos in ``04_tiling_and_area_api.ipynb``.

Pick a city via ``CITIES["munich"]`` or one of the helper getters.

Note on data coverage: Infrared's gridded layers (buildings, vegetation,
ground materials) are populated from OpenStreetMap and similar sources
worldwide, but coverage and quality vary by region. If a fetch returns
zero buildings for a given polygon, try a different polygon or city.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    """A city preset with a centre point, a small polygon, and a large polygon."""

    name: str
    country: str
    continent: str
    latitude: float
    longitude: float
    polygon_small: dict
    polygon_large: dict


def _square_polygon(lat: float, lon: float, half_lat: float, half_lon: float) -> dict:
    """Closed CCW square polygon centred at (lat, lon)."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half_lon, lat - half_lat],
            [lon + half_lon, lat - half_lat],
            [lon + half_lon, lat + half_lat],
            [lon - half_lon, lat + half_lat],
            [lon - half_lon, lat - half_lat],
        ]],
    }


def _irregular_polygon(lat: float, lon: float, half_lat: float, half_lon: float) -> dict:
    """Irregular pentagon centred at (lat, lon).

    Spans roughly 2 x ``half_lon`` east-west and 2 x ``half_lat`` north-south,
    sized so that with the solar tile size of 512 m the polygon hits 4-6
    non-empty tiles. Shaped to obviously not be axis-aligned.
    """
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half_lon,         lat - half_lat * 0.6],
            [lon - half_lon * 0.3,   lat - half_lat],
            [lon + half_lon,         lat - half_lat * 0.4],
            [lon + half_lon * 0.7,   lat + half_lat],
            [lon - half_lon * 0.6,   lat + half_lat * 0.7],
            [lon - half_lon,         lat - half_lat * 0.6],
        ]],
    }


def _make_city(name: str, country: str, continent: str, lat: float, lon: float) -> City:
    # Small: ~150 m on a side. half_lat 0.0007 deg = ~78 m.  half_lon scales by cos(lat).
    import math
    cos_lat = math.cos(math.radians(lat))
    small_half_lat = 0.0007
    small_half_lon = 0.0007 / max(cos_lat, 0.1)
    # Large: ~1.2 km wide, ~1.2 km tall.
    large_half_lat = 0.0055
    large_half_lon = 0.0055 / max(cos_lat, 0.1)
    return City(
        name=name,
        country=country,
        continent=continent,
        latitude=lat,
        longitude=lon,
        polygon_small=_square_polygon(lat, lon, small_half_lat, small_half_lon),
        polygon_large=_irregular_polygon(lat, lon, large_half_lat, large_half_lon),
    )


# ---------------------------------------------------------------------------
# 5 cities, one per continent.
# ---------------------------------------------------------------------------

CITIES: dict[str, City] = {
    # Europe -- Munich, near Marienplatz.
    "munich": _make_city("Munich", "Germany", "Europe", 48.1374, 11.5755),
    # Europe -- Vienna, Rathauspark (mixed buildings + park + water).
    "vienna": _make_city("Vienna", "Austria", "Europe", 48.2107, 16.3585),
    # North America -- New York, Lower Manhattan / Tribeca.
    "new_york": _make_city("New York", "USA", "North America", 40.7180, -74.0060),
    # South America -- Sao Paulo, Avenida Paulista.
    "sao_paulo": _make_city("Sao Paulo", "Brazil", "South America", -23.5613, -46.6562),
    # Asia -- Tokyo, Shibuya.
    "tokyo": _make_city("Tokyo", "Japan", "Asia", 35.6595, 139.7005),
    # Oceania -- Sydney CBD near Town Hall.
    "sydney": _make_city("Sydney", "Australia", "Oceania", -33.8730, 151.2070),
}


def get(slug: str = "munich") -> City:
    """Look up a city by slug. Defaults to ``munich``."""
    if slug not in CITIES:
        raise KeyError(
            f"Unknown city {slug!r}. Available: {sorted(CITIES)}"
        )
    return CITIES[slug]


def list_cities() -> list[tuple[str, str, str]]:
    """Return ``[(slug, name, continent)]`` pairs."""
    return [(s, c.name, c.continent) for s, c in CITIES.items()]


if __name__ == "__main__":
    for slug, name, continent in list_cities():
        c = get(slug)
        print(f"{slug:10s}  {name:12s}  {continent:14s}  ({c.latitude:.4f}, {c.longitude:.4f})")
