# Notebooks

Ten case studies. Each notebook is standalone: run them in any order. They share the plot helpers in [`ir_plot.py`](ir_plot.py).

| # | Notebook | Question | Analyses | City |
|---|---|---|---|---|
| 00 | [`00_quickstart`](00_quickstart.ipynb) | How much open sky do people see in the streets? | Sky view factor | Hamburg |
| 01 | [`01_design_variants`](01_design_variants.ipynb) | Which of four designs stays coolest on a hot afternoon? (your own GeoJSON model) | UTCI | Vienna |
| 02 | [`02_summer_heat`](02_summer_heat.ipynb) | How much do street trees and light paving cool a dense block? | UTCI, thermal comfort statistics | Barcelona |
| 03 | [`03_wind_comfort`](03_wind_comfort.ipynb) | Where is it too windy to sit, stand or walk? | Wind speed, pedestrian wind comfort | New York |
| 04 | [`04_solar_facades_3d`](04_solar_facades_3d.ipynb) | Which facades and roofs of a dense block get the most sun in summer? (3D) | Solar radiation on facades and roofs | Vienna |
| 05 | [`05_sensors_3d`](05_sensors_3d.ipynb) | How much daylight reaches facades and a park, at points you choose? (3D) | Daylight availability on own sensor points | Vienna |
| 06 | [`06_interior`](06_interior.ipynb) | How much daylight reaches the rooms? How much heating and cooling do they need? (Beta) | Daylight factor, energy balance | example building |
| 07 | [`07_terrain_and_context`](07_terrain_and_context.ipynb) | How many winter sun hours does a hillside get, and what does a ridge take away? | Direct sun hours with terrain and context | example slope near Innsbruck |
| 08 | [`08_scale_and_cost`](08_scale_and_cost.ipynb) | What does a run cost? How do I run several analyses fast? | Preview, several analyses on one geometry | Rotterdam |
| 09 | [`09_all_analyses`](09_all_analyses.ipynb) | What do all eight area analyses show for one district? How do I run them in one call? | All eight area analyses, one call, overview map | Amsterdam |

Notebooks 04 to 07 draw 3D views with [`ir_view3d.py`](ir_view3d.py). Site helpers are in [`ir_site.py`](ir_site.py).

## Run

Start Jupyter in this folder (`cookbook/notebooks`). The notebooks import `ir_plot`, `ir_site` and `ir_view3d` from here.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # SDK 1.0 with [geodata], maps, jupyter
export INFRARED_API_KEY=...         # or copy .env.example to .env
jupyter lab
```

Python 3.11 or newer. On a headless server, start Jupyter with `xvfb-run -a jupyter lab` so the 3D views can render. The client reads `INFRARED_API_KEY` from the environment.

## Cost

A real run uses tokens. Each notebook calls `preview_area` first (free, local). Read the preview before you run. Use a small polygon to try things.

Public buildings, trees and ground come from Overture (`infrared-sdk[geodata]`). Source and heights vary by region.
