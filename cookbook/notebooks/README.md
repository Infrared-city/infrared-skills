# Notebooks

Nine case studies. Each notebook is standalone: run them in any order. They share the plot helpers in [`ir_plot.py`](ir_plot.py).

| # | Notebook | Question | Analyses | City |
|---|---|---|---|---|
| 00 | [`00_quickstart`](00_quickstart.ipynb) | How much open sky do people see in the streets? | Sky view factor | Hamburg |
| 01 | [`01_design_variants`](01_design_variants.ipynb) | Which of four designs stays coolest on a hot afternoon? (your own GeoJSON model) | UTCI | Vienna |
| 02 | [`02_summer_heat`](02_summer_heat.ipynb) | How much do street trees and light paving cool a dense block? | UTCI, thermal comfort statistics | Barcelona |
| 03 | [`03_wind_comfort`](03_wind_comfort.ipynb) | Where is it too windy to sit, stand or walk? | Wind speed, pedestrian wind comfort | New York |
| 04 | `04_solar_facades_3d` | Which facades and roofs get the most sun? | Solar radiation on surfaces | see notebook |
| 05 | `05_sensors_3d` | How do I analyse my own sensor points? | Sky view factor, daylight availability | see notebook |
| 06 | `06_interior` | How good is the daylight in a room? What does it need for heating and cooling? | Daylight factor, energy balance | see notebook |
| 07 | `07_terrain_and_context` | How do hills and far buildings change the result? | Terrain and context geometry | see notebook |
| 08 | [`08_scale_and_cost`](08_scale_and_cost.ipynb) | What does a run cost? How do I run several analyses fast? | Preview, several analyses on one geometry | Rotterdam |

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # SDK 1.0 with [geodata], maps, jupyter
export INFRARED_API_KEY=...         # or copy .env.example to .env
jupyter lab
```

Python 3.11 or newer. The client reads `INFRARED_API_KEY` from the environment.

## Cost

A real run uses tokens. Each notebook calls `preview_area` first (free, local). Read the preview before you run. Use a small polygon to try things.

Public buildings, trees and ground come from Overture (`infrared-sdk[geodata]`). Source and heights vary by region.
