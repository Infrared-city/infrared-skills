# Update tool for an exported city (Python)

TypeScript: the same calls in camelCase: `client.updatePreview`, `client.update(preview, { maxTokens, refreshCoarse })`.

| Name | What it does |
|---|---|
| `TileExport(target)` | the export (it keeps every job result for the update) |
| `client.update_preview(payloads, city, target, buildings=, vegetation=, ids=)` | finds the changed tiles, price; free, no POST |
| `client.update(preview, max_tokens=, refresh_coarse=False)` | sends the changed tiles, commits; `refresh_coarse=True` also rebuilds the far view (no job) |
| `prune(target, keep_days=7, dry_run=False)` | deletes old revisions; `dry_run=True` lists them |

Rules:

- Use the SAME payloads, city polygon and `ids` as the export. Give the inputs of the WHOLE city as it is now.
- Show `print(preview)` to the user before `client.update`. Always pass `max_tokens`.
- Never loop or retry `client.update` without a new preview.
- `prune(keep_days=7)` deletes nothing in the first 7 days. `dry_run=True` shows what goes. Use `keep_days=0`
  only when no update runs and no viewer opened the city before the last update.
- An update that changed nothing writes nothing: `summary.sent == 0`. `summary.sent` counts the jobs it ran,
  with the jobs a stopped call sent already (not billed again); a failed update billed what it sent.

```python
import os
from infrared_sdk import FolderTarget, InfraredClient, TileExport, prune
from infrared_sdk.analyses.types import AnalysesName, SvfModelRequest, WindModelRequest

client = InfraredClient(api_key=os.environ["INFRARED_API_KEY"])
payloads = [WindModelRequest(analysis_type=AnalysesName.wind_speed, wind_speed=5, wind_direction=90),
            SvfModelRequest(analysis_type=AnalysesName.sky_view_factors)]
ids = {0: "wind", 1: "svf"}
# city: GeoJSON polygon. buildings: {id: mesh} in metres. vegetation: {id: GeoJSON Feature}.
# 0. Free, no run: the grey buildings, before the user pays: top-level export_geometry(...)
# 1. Once, billed
export = TileExport(FolderTarget("city/"), ids=ids, trees=vegetation)
client.run_area_and_wait(payloads, city, buildings=buildings, vegetation=vegetation, export=export)
# 2. Your edit: move "b17" 8 m east, add trees (new_trees: {id: Feature})
old = buildings["b17"]
buildings_now = dict(buildings, b17=dict(old, coordinates=[
    c + 8.0 if i % 3 == 0 else c for i, c in enumerate(old["coordinates"])]))
vegetation_now = dict(vegetation, **new_trees)
# 3. Preview, not billed: the kernel compares every tile with the export
preview = client.update_preview(payloads, city, "city/", ids=ids,
                                buildings=buildings_now, vegetation=vegetation_now)
print(preview)  # every part compared -> 5 tiles in 1 part -> 50 tokens (full run: 260)
# 4. After the user agrees
summary = client.update(preview, max_tokens=preview.tokens)
print(summary.sent, "jobs sent,", summary.kept, "kept, parts", summary.parts)
prune("city/", keep_days=7)  # later
```

Bucket: use `S3Target(boto3.client("s3", ...), bucket, prefix)` for `"city/"`.

Price: `preview.tokens` (sent jobs) and `preview.full_tokens` (full run). `preview.analyses[i]["sent_tiles"]` and
`preview.parts` name the changed tiles and parts.

Large city (many parts): the preview plans every part (CPU, about 0.5 s per 4 km² part). Pass
`change=[[west, south, east, north], ...]` (degrees) around the edits to plan only the parts they reach. An edit
outside them is not found: `print(preview)` says "K of M parts compared"; show it to the user.

Refusals come before any POST; nothing is billed. Each text starts with fixed words: match the start.

| The text starts with | Do this |
|---|---|
| `the settings or the weather differ` | Use the export's payloads; new settings need a new export id |
| `the input hashes are of other hash rules` | Pass `change=` boxes over the edits, or export again to a new id |
| `the settings hash is of other hash rules` | Export again to a new id |
| `a kept result is missing` | Export again to a new id |
| `the update costs` (over `max_tokens`) | Show the price; raise `max_tokens` only if the user agrees |
| `the update sends` (over the tile cap, no `max_tokens`) | Show the price; pass `max_tokens=` to confirm it |
| `the export changed since the preview` / `UpdateConflict` | Run `update_preview` again |
| `this preview was run already` | A preview runs once: run `update_preview` again |
| `a kept result is broken` (from `update`) | A kept file is broken: export again to a new id |
| `the trees of the export stand on its terrain` | Pass the export's `terrain=` |
| `this target cannot write a file only when it is unchanged` | Use `FolderTarget` or `S3Target` |

## Variants

Many cheap variants of one city, compared in the viewer; keep the best. Each variant is a VERSION: a few pointer
files under `versions/<name>/`. It shares every file of the export but those of the parts it changes. Promote,
delete and later updates never change or break another version.

- The inputs of a variant are the WHOLE city as it is in its base (live with its earlier edits), plus the edit
  of the variant: `houses = dict(buildings_live, **edit)`. An edit left out is undone in the variant.
- A name that exists (no `base=`) is updated on top of itself: the preview says "into the existing version".
- A preview that says "no change: version v1 is not made" makes no version; `promote` needs a made one.
- `versions/index.json` lists the versions; after a promote the live `manifest.json` has `promoted_from`. Read it with
  `json.loads(target.get("versions/index.json"))` (a folder: `"city/versions/index.json"`).

| Name | What it does |
|---|---|
| `client.update_preview(..., version="v1", base="live")` | the update writes version `v1`; `live` does not change |
| `promote(target, "v1")` | `v1` becomes the live city (its pointer files, `manifest.json` last); stopped: run it again |
| `delete_version(target, "v1")` | removes `v1`; then `prune` deletes the files only it used |

```python
from infrared_sdk import delete_version, promote, prune

for name, edit in variants.items():  # {name: {building id: mesh}}
    houses = dict(buildings_live, **edit)  # the whole city of the base, plus the edit
    p = client.update_preview(payloads, city, "city/", ids=ids, buildings=houses,
                              vegetation=vegetation, version=name)
    print(p)  # ... -> 3 tiles in 1 part -> 30 tokens (full run: 260) / into the new version park-v2, made from live
    client.update(p, max_tokens=p.tokens)
# The viewer lists versions/index.json; the user picks one.
promote("city/", "park-v2")
for name in variants:
    delete_version("city/", name)
prune("city/", keep_days=7)
```

`base="v1"` makes a version from a version (an edit on top of `v1`).

| The text starts with | Do this |
|---|---|
| `the version exists with another base` | Leave `base=` out to change it, or use another name |
| `the base is not a version of the target` | Use a name of `versions/index.json`, or `live` |
| `a version name is 1 to 64 characters` | Use `a-z`, `0-9`, `_`, `-` only |
| `the version name live is the city itself` | Leave `version=` out to update the live city |
| `an update of the live city reads the live city` | Use `promote` to make a version live |
| `the version is not in the target` (from `promote`, `delete_version`) | Check `versions/index.json` |
| `the index was not written` | Nothing is lost: the step is done; the next update into a version, `promote` or `delete_version` puts the index right |

