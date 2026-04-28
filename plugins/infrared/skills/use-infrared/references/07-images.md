# Image Generation

Render an analysis result grid to a PNG via the weather-service `gen_grid_image` endpoint. Useful for previews, dashboards, and reports without local matplotlib.

## Generating an image

```python
result = client.run_area_and_wait(payload, polygon, buildings=area.buildings)
grid = result.merged_grid.tolist()

img_bytes = client.weather.gen_grid_image(
    grid=grid,
    analysis_type="wind-speed",  # optional: improves color mapping
)

with open("output.png", "wb") as f:
    f.write(img_bytes)
```

`gen_grid_image` returns raw PNG bytes — write directly or wrap in `io.BytesIO` for upload. The `analysis_type` argument is optional but recommended; it picks the correct legend palette and range.

## PWC and TCS extras

For Pedestrian Wind Comfort and Thermal Comfort analyses, `gen_grid_image` accepts two extra optional parameters that select sub-categories of the colour mapping:

- `criteria` — comfort criterion (e.g. Lawson, NEN8100)
- `subtype` — analysis subtype identifier

Pass them through alongside `grid` and `analysis_type` when relevant.

## Pitfalls

- Pass `result.merged_grid.tolist()`, not the raw numpy array — the request body is JSON and numpy floats / NaN do not serialize directly. `to_list()` on a `TiledResult` (or `to_dict()` on `AreaResult`) does the NaN -> `None` conversion automatically.
- Without `analysis_type`, the server falls back to a generic palette — colours will not match heatmaps in other tools (e.g. Plotly using `min_legend`/`max_legend`).
- Output is a fixed PNG; for vector / interactive plots, render locally from `merged_grid` instead.
- The endpoint is part of the weather service (`client.weather`), not `client.analyses` — don't mix them up.

## See also

- `references/workflows/area-api.md` — `min_legend` / `max_legend` for matched local plots
- `references/analyses/` — analysis-type identifiers accepted by `gen_grid_image`
