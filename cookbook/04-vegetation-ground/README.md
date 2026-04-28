# 04 — Vegetation + ground materials (fetch-once-reuse)

Layers (buildings, trees, ground materials) don't change when you sweep wind direction or tweak weather windows. This recipe shows the fetch-once-reuse pattern that avoids redundant API calls across multiple runs.

**Run:** `python vegetation_ground.py`
**Deps:** `infrared-sdk plotly python-dotenv`
