# Infrared Cookbook

Case studies for the [Infrared SDK](https://infrared.city/docs/sdk/). Each one answers one question about a real site.

| Folder | What is in it |
|---|---|
| [`notebooks/`](notebooks/) | Nine Python notebooks, 00 to 08. Start here. |
| [`scripts/`](scripts/) | Three short Python scripts: `quickstart.py`, `own_geometry.py`, `comfort.py`. Each prints the preview cost and asks y/N. `--yes` skips the question. |
| [`apps/`](apps/) | Runnable apps: map grid, 3D facades, Cloudflare key proxy (TypeScript), FastAPI backend (Python). |
| [`sample-data/`](sample-data/) | GeoJSON models (Vienna scenarios, platform upload) used by the examples. |

## Run

```bash
git clone git@github.com:Infrared-city/infrared-skills.git
cd infrared-skills/cookbook/notebooks   # run from here: the notebooks import helpers in this folder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export INFRARED_API_KEY=...        # get a key at https://infrared.city
jupyter lab
```

On a headless server, run `xvfb-run -a jupyter lab` for the 3D views. Requirements: [`notebooks/requirements.txt`](notebooks/requirements.txt).

The apps have their own README with run steps.

## Cost

Area runs use tokens. One job is one tile for one analysis. Always call `client.preview_area(...)` first: it is free and runs on your machine. Read `would_bill_jobs` and `estimated_cost_tokens`, then run. Notebook [08](notebooks/08_scale_and_cost.ipynb) shows how.

Feedback: <https://github.com/Infrared-city/infrared-skills/issues>
