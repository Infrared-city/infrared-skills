# Update tool for an exported city

Change some buildings or trees of an exported city and run only the changed tiles. The guide has the full text
([a whole city and changes](https://infrared.city/docs/sdk/#3d-tiles-a-whole-city-and-changes)). This page is the checklist for an agent.
Python and TypeScript have the same calls (TypeScript: camelCase and an options object).

| Python | TypeScript | What it does |
|---|---|---|
| `TileExport(target)` | `new TileExport(target)` | the export (it keeps every job result for the update) |
| `client.update_preview(payloads, city, target, buildings=, vegetation=, ids=)` | `client.updatePreview(inputs, city, target, { buildings, vegetation, ids })` | finds the changed tiles and the price; free, no POST |
| `client.update(preview, max_tokens=, refresh_coarse=False)` | `client.update(preview, { maxTokens, refreshCoarse })` | sends the changed tiles, commits; `refresh_coarse` also rebuilds the far view (no job) |
| `export_geometry(city, target, buildings=, trees=)` | `exportGeometry(city, target, { buildings, trees })` | the grey layer before any paid run; free, no API key |
| `prune(target, keep_days=7, dry_run=False)` | `prune(target, { keepDays, dryRun })` | deletes old revisions |

Rules:

- Use the SAME payloads, city polygon, `ids` and terrain as the export. Give the inputs of the WHOLE city as it is now.
  The origin is the SW corner of the polygon: do not change the polygon.
- Show `print(preview)` to the user. Always pass `max_tokens`. Never retry `update` without a new preview.
- Pass `refresh_coarse=True` on the last update of a batch. Without it the manifest lists the changed blocks in `stale`: the
  detail tiles are new, the far view and the merged ground are old for those blocks.
- `update` rebuilds the grey layer by itself.
- `prune(keep_days=7)` deletes nothing in the first 7 days. Use `dry_run=True` first.
- One writer per target. `summary.sent == 0` means nothing changed. A failed update billed what it sent.

```python
import os
from infrared_sdk import FolderTarget, InfraredClient, TileExport, export_geometry, prune
from infrared_sdk.analyses.types import AnalysesName, SvfModelRequest, WindModelRequest

client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])
payloads = [WindModelRequest(analysis_type=AnalysesName.wind_speed, wind_speed=5, wind_direction=90),
            SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)]
ids = {0: "wind", 1: "svf"}
# city: GeoJSON polygon. buildings: {id: {"coordinates": [...], "indices": [...]}} in metres.
# vegetation: {id: GeoJSON Feature}. new_trees: the same shape.
export_geometry(city, "city/", buildings=buildings, trees=vegetation)          # free: grey buildings first
export = TileExport(FolderTarget("city/"), ids=ids, trees=vegetation)          # terrain=... if you exported terrain
client.run_area_and_wait(payloads, city, buildings=buildings, vegetation=vegetation, export=export)   # billed once
old = buildings["b17"]                                                         # your edit: move b17 8 m east
buildings_now = dict(buildings, b17=dict(old, coordinates=[
    c + 8.0 if i % 3 == 0 else c for i, c in enumerate(old["coordinates"])]))
vegetation_now = dict(vegetation, **new_trees)
preview = client.update_preview(payloads, city, "city/", ids=ids, buildings=buildings_now, vegetation=vegetation_now)
print(preview)        # every part compared -> 5 tiles (5 jobs) in 1 part -> 50 tokens (full run: 260)
summary = client.update(preview, max_tokens=preview.tokens, refresh_coarse=True)    # after the user agrees
print(summary.sent, "jobs sent,", summary.kept, "kept")
prune("city/", keep_days=7)                                                    # later
```

```ts
const preview = await client.updatePreview(inputs, city, target,
  { ids: { 0: "wind", 1: "svf" }, buildings: buildingsNow, vegetation: vegetationNow });
console.log(String(preview));
const summary = await client.update(preview, { maxTokens: preview.tokens, refreshCoarse: true });
```

Bucket: `S3Target(boto3.client("s3", ...), bucket, prefix)` in place of `"city/"`. Large city: `change=[[west, south, east, north], ...]`
(degrees) plans only the parts the edits reach; the preview says "K of M parts compared": show it. Words (tile, job, token):
[Words for cost](https://infrared.city/docs/sdk/#words-for-cost).

Refusals come before any POST; nothing is billed. Match the start of the text.

| The text starts with | Do this |
|---|---|
| `the settings or the weather differ` | Use the export's payloads; new settings need a new export id |
| `a kept result is missing` / `is broken` | Export again to a new id |
| `the update costs` / `the update sends` | Show the price; raise `max_tokens` only if the user agrees |
| `the export changed since the preview` / `UpdateConflict` | Run `update_preview` again |
| `the trees of the export stand on its terrain` | Pass the export's `terrain=` to `TileExport` |
| `this target cannot write a file only when it is unchanged` | Use `FolderTarget` or `S3Target` |

## Variants

A version is a few pointer files under `versions/<name>/`; it shares all other files. The live city does not change.
The inputs of a variant are the WHOLE city of its base plus the edit: `houses = dict(buildings_live, **edit)`.

```python
from infrared_sdk import promote, prune
p = client.update_preview(payloads, city, "city/", ids=ids, buildings=houses, vegetation=vegetation, version="park-v2")
client.update(p, max_tokens=p.tokens)       # base="v1" makes a version from a version
promote("city/", "park-v2")                 # park-v2 is now the live city
```

`versions/index.json` lists the versions for a viewer. `delete_version(target, name)` removes one; `prune` then deletes its own files.

| The text starts with | Do this |
|---|---|
| `the version exists with another base` | Leave `base=` out, or use another name |
| `a version name is 1 to 64 characters` | Use `a-z`, `0-9`, `_`, `-` |
| `the version name live is the city itself` | Leave `version=` out to update the live city |
| `an update of the live city reads the live city` | Use `promote` to make a version live |
