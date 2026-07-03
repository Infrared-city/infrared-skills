# Platform upload sample set

Drop-ready test files for the platform's "Bring your own data" flow
(project creation or the Data-layers panel). Synthetic Vienna block,
validated against the platform's own upload parsers — see
[`platform-byo-upload.md`](../../../plugins/infrared/skills/use-infrared/references/platform-byo-upload.md)
for the full file contract.

| File | Layer | Notes |
|---|---|---|
| `buildings.geojson` | Buildings | 32 footprints, `height_m` 6–32 |
| `variant-b.geojson` | Design variant | same block, taller — becomes Variant A/B |
| `trees.geojson` | Trees | 60 Points, `height` + `crownDiameter` set |
| `surfaces.geojson` | Ground surfaces | all 5 canonical materials tagged |
| *(not committed)* `vienna-synthetic.epw` | Weather | 1.2 MB — regenerate below |

Regenerate everything (any location):

```bash
python ../scripts/demo_platform_upload_files.py --center 16.37 48.20 --radius 200 --out .
```
