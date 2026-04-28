# 05 — Area tiling walkthrough

Educational walkthrough of how the SDK tiles polygons larger than 512×512 m. Previews tile cost, runs a wind analysis over a multi-tile polygon, and overlays per-tile boundaries on the merged grid so you can see where one tile ends and the next begins.

Wind tiling uses 50% overlap (256 m centre-to-centre); solar/thermal tiling is edge-to-edge with a 666 m context window.

**Run:** `python tiling.py`
**Deps:** `infrared-sdk plotly python-dotenv`
