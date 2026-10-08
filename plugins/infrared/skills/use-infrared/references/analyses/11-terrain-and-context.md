# Terrain and far context

Terrain goes in `ground_geometry` on the request. Far objects that only cast shade go in
`context_geometry`. Call code: [../python/surfaces-and-sensors.md](../python/surfaces-and-sensors.md).

## The SDK does not fetch terrain

There is no terrain service. Omit `ground_geometry` and the ground is a flat plane at z = 0.
There is no error, and the result looks normal. Bring your own terrain every time.

`terrain` is one flat mesh `{coordinates, indices}` in metres on the same frame and z datum as your
buildings. Make a mesh from a height grid first (see the helper in the Python page). A GeoTIFF
needs your own reader (`rasterio`) and a re-projection to the metre grid. The mesh must cover the
whole polygon. A building beyond the edge is placed at the edge height.

A BIM terrain solid is closed. `ground_geometry` wants the top surface only. Keep the up-facing
triangles (normal z above 0.5) and drop the bottom cap and the skirt.

Set `terrain_alignment` yourself: the field is unset by default.

Which analyses take it: the four solar analyses and UTCI and TCS. Wind refuses terrain: it has no `ground_geometry`.

## `terrain_alignment`

| Mode | What happens | Use when |
|---|---|---|
| `"as-is"` | Trusts your geometry. No seating, no check. The guide names it the default for a supplied scene (the SDK field is unset until you set it) | Your model already sits on its terrain |
| `"auto-align"` | Seats every solid on the local ground, with a 0.5 m skirt | Buildings at z = 0 on a real terrain |
| `"assume-aligned"` | Checks only. A base outside terrain -1.5 to +1.0 m refuses the job (422, with the offenders) | You want a mismatch to fail loud |

Wind and PWC accept `"to-ground"` and `"as-is"`. No mode moves the sensors: with terrain, the grid
always drapes onto it. The modes change what happens to the solids.
Do not compare modes by their mean: a small change of the mean can hide large changes on many
facades. Compare per surface.

## Results on the ground, with terrain

Run a plain grid analysis with `ground_geometry`. The 1 m grid drapes onto the relief
(z = terrain + 1.5 m). The terrain shades the sun.

- `physical_grid()` is a flat raster with no z. To draw it on the terrain, re-sample your own
  terrain at each cell centre ([../recipes/rendering-results-well.md](../recipes/rendering-results-well.md)).
- Row 0 is south, column 0 is west, pitch 1 m.
- Cells under a building footprint are `0.0` on this path, not NaN. NaN means outside the polygon
  or off the terrain. Mask the footprints with your own polygons before a shadow statistic.

## Far shade in 1.0

A tile reads geometry 128 m past its edge. Terrain is cut for each tile to what its buildings and
trees need. An object farther away gives no shade and no error. This includes `context_geometry`.
To keep distant relief, give it as low-poly `context_geometry` that touches the 128 m margin.
`terrain_context_margin_m` on `run_area` widens the terrain slice for valley and escarpment sites;
the payload grows with the square of the reach.

Advice: give far geometry as sparse, low-poly blocks and hills. Each mesh uploads once for every
tile that holds it. A context mesh over about 50,000 triangles gives a warning.
A later release adds a `context_reach_m` setting.
