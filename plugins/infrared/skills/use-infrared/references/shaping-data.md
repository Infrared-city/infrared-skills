# Get data, then shape it

Two independent jobs. Combine them or not.

1. **Get data**: your own (BIM, Rhino, IFC, GeoJSON) or fetched with the SDK (buildings, trees, ground,
   weather). The output is data you hold.
2. **Shape it**: turn what you hold into what the SDK expects, and the results back into what your tool needs.

## Shaping: principles

- **Read the contract both ways.** Before you write code, know what each input channel accepts and what each
  result returns. The result format decides how you draw, store and export as much as the input decides the payload.
- **Map what exists, 1:1.** Assume only what is missing (rooms, a ground slab, a location), and say so in the
  log or the UI. A look-alike built from outlines runs, bills and gives confident, wrong numbers.
- **Look before you pay.** Put what you send next to the source (one picture per channel). Most failures
  return 200 and a plausible value.
- **Diagnose from stored results.** When a result looks wrong, measure it (which faces, which orientation,
  before and after) before you change the pipeline or run again.
- **Use what the SDK already does** before you build your own: several analyses on one upload, render
  buffers for facades, the directional merge for wind.
