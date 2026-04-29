# Infrared Cookbook

Two flavours, same SDK:

- [`notebooks/`](notebooks/) — eight Jupyter notebooks with embedded outputs, walking through every analysis end-to-end against five preset cities. Auto-mirrored from the SDK source.
- [`scripts/`](scripts/) — runnable `.py` examples (wind, UTCI, multi-analysis, vegetation/ground, tiling, fetch-layers, advanced usage) plus an async webhook walkthrough at [`scripts/areas_demo_async/`](scripts/areas_demo_async/). Auto-mirrored from the SDK source.

Both directories are auto-synced from the SDK on every release — do not hand-edit. File feedback at <https://github.com/Infrared-city/infrared-skills/issues>.

## Setup

```bash
git clone git@github.com:Infrared-city/infrared-skills.git
cd infrared-skills/cookbook/notebooks   # or cookbook/scripts
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste your INFRARED_API_KEY
```

Get an API key at <https://infrared.city>.
