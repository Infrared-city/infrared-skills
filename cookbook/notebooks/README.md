# Infrared SDK — Public Demo Notebooks

Hands-on Jupyter notebooks that walk through the Infrared SDK end-to-end:
fetching urban geometry (buildings, vegetation, ground materials), pulling
weather data, running the eight microclimate analyses, rendering results,
and using the async / webhook flow.

Each notebook is **self-contained and runnable in any order**. Pick a city,
import the SDK, hit the API.

## Prerequisites

- Python 3.11+
- An Infrared API key. Request access at <https://infrared.city>.

## Installation

```bash
git clone <this-folder>             # or download/extract the public-demos/ folder
cd public-demos
python -m venv .venv && source .venv/bin/activate   # or: .venv\Scripts\activate on Windows

# Install the SDK and demo deps:
pip install infrared-sdk
pip install -r requirements.txt
```

## Configure your API key

```bash
cp .env.example .env
# then edit .env and paste your INFRARED_API_KEY
```

The notebooks call `python-dotenv` to load `.env` automatically.

## Pick a city

`cities.py` ships with six preset cities, covering every continent:

| Slug         | City        | Country   | Continent     |
| ------------ | ----------- | --------- | ------------- |
| `munich`     | Munich      | Germany   | Europe        |
| `vienna`     | Vienna      | Austria   | Europe        |
| `new_york`   | New York    | USA       | North America |
| `sao_paulo`  | Sao Paulo   | Brazil    | South America |
| `tokyo`      | Tokyo       | Japan     | Asia          |
| `sydney`     | Sydney      | Australia | Oceania       |

Each city has two polygons:

- `polygon_small` — ~150 m square, fits in one solar tile (fast / cheap to run).
- `polygon_large` — irregular pentagon ~1.2 km wide, generates 4-6 tiles
  (used in the tiling notebook).

You can switch city in any notebook by changing one line:

```python
from cities import get
city = get("tokyo")  # try "munich", "new_york", "sao_paulo", "tokyo", "sydney"
```

> **Coverage caveat.** Infrared's gridded layers are populated from
> OpenStreetMap-style sources worldwide, but density and freshness vary
> by region. If a fetch returns zero buildings for a given polygon, try
> a different polygon or a different city.

## Reading order

The notebooks are numbered to suggest a path, but each is standalone:

| # | Notebook                           | What it covers                                                 |
|---|------------------------------------|----------------------------------------------------------------|
| 0 | `00_quickstart.ipynb`              | Install, env, instantiate the client, run one analysis end-to-end |
| 1 | `01_buildings.ipynb`               | `client.buildings.get_area`, DotBim mesh format, building heights |
| 2 | `02_vegetation_and_ground.ipynb`   | `client.vegetation`, `client.ground_materials`, layer formats |
| 3 | `03_weather_and_time_periods.ipynb`| Weather file lookup, `filter_weather_data`, `TimePeriod` semantics |
| 4 | `04_tiling_and_area_api.ipynb`     | `preview_area`, rectangular vs. irregular polygons, tile geometry, `AreaResult` |
| 5 | `05_analysis_types_tour.ipynb`     | All 8 analysis types with payload patterns and outputs |
| 6 | `06_image_rendering.ipynb`         | `gen_grid_image`, orientation, colormap caveats |
| 7 | `07_async_and_webhooks.ipynb`      | `run_area`, `check_area_state`, `merge_area_jobs`, webhooks |

## Optional: webhook receiver

`07_async_and_webhooks.ipynb` references `webhook_receiver.py`, a tiny
Flask server that prints each webhook the Infrared dispatcher posts.
See the docstring at the top of the file for setup instructions
(including a one-liner for `cloudflared` to expose it publicly).

## License

The notebooks are distributed under the same Apache-2.0 license as the
SDK (the full license ships with the `infrared-sdk` package).
