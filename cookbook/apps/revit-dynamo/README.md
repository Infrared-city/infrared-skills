# Infrared in Revit 2026 (Dynamo)

One Dynamo script, `IR_Analysis.dyn`, runs an Infrared analysis on the buildings you select in Revit.
It shows the result as a coloured surface in the model, with a legend. The `target` input chooses
what it analyses: `ground`, `facades` (walls and roofs) or `both`.

| `target` | What it analyses | Analyses (`analysis` input) |
|---|---|---|
| `ground` | The ground around the buildings | `svf`, `solar`, `sun-hours`, `wind`, `utci` |
| `facades` | The walls and roofs of the buildings | `svf`, `solar`, `sun-hours`, `daylight` |
| `both` (or `all`) | Both, one after the other | `svf`, `solar`, `sun-hours` on both; `wind`, `utci` on the ground only; `daylight` on the facades only |

One Infrared request computes the ground grid or the facades, not both. So `both`
is **two runs and two costs**. The preview shows both costs and their sum. If the
analysis exists on one target only (for example `wind`), `both` runs it there and
the Watch text says that the other target was skipped.

## What it does

1. You select buildings in Revit.
2. The script reads their geometry and the project location.
3. The script shows the cost of the run. This is free.
4. You set `preview_only` to `False`. The script runs the analysis on the Infrared servers.
5. Revit shows a coloured surface in the model and a legend in a drafting view.

## Requirements

- Revit 2026 with Dynamo 3.4.
- An Infrared API key (<https://infrared.city>).
- Windows x64. The libs zip holds Windows packages only.

## Install

Choose one way.

**Download.** Get `infrared-dynamo-libs.zip`. Unzip it into this folder:
`%APPDATA%\Infrared\revit-dynamo`. The folder must now hold `ir_dynamo`, `ir_revit`,
`dynamo` and the SDK packages.

**Build it.** Run this on any machine that has Python 3.9 or later and pip:

```text
python build_libs.py
```

The script writes `build/infrared-dynamo-libs.zip` (about 50 MB). Unzip it as above.

Then open `dynamo/IR_Analysis.dyn` in Dynamo.
Dynamo opens the file in Manual run mode. Nothing runs until you press Run.

## Set the API key

1. Set `set_api_key` to `True` and press Run. A dialog opens.
2. Paste your key and press Save. The dialog shows dots, not the key.
3. Set `set_api_key` to `False`.

The script saves the key in `.infrared\api_key.txt` in your user folder.
The script never prints the key. You can also set the `INFRARED_API_KEY`
environment variable. The variable has priority. Do not put a key in a `.dyn` file.

## Set the project location in Revit

The script needs the place of the project and the direction of true north.

1. Open Manage > Location. Set the real city or address of the project.
   Revit stores one latitude and one longitude for the whole project.
2. Set true north: open a plan view, set the view to True North in its
   properties, and use Manage > Position > Rotate True North.
3. The script uses the latitude and longitude as the position of the
   internal origin of the Revit file. It does not use the Project Base Point
   or the Survey Point.
4. If the Project Base Point is far from the internal origin, or the model
   is far from the internal origin, you can enter `lat` and `lon` in the script.
   Use the position of the internal origin.
5. This matters only if you set `fetch_context` to `True`. The public
   buildings are then placed from this position. For a free run without
   context, an error of some metres changes nothing.

Leave `lat` and `lon` empty to use the project location.

## Run IR_Analysis

1. Open the script. Check that `libs_folder` is the folder you unzipped to.
2. Open a 3D view (Shaded or Realistic). The result is a shape in the model, so every view shows it.
3. Select your buildings in Revit. In Dynamo, click "Select Model Elements" and
   press Select. Walls, floors, roofs, masses and families all work.
4. Set `target` (`ground`, `facades` or `both`) and `analysis` (a label from the table above, or `show-last`).
5. Set `months` (for example `6-8`) and `hours` (for example `8-18`, or one hour like `13`).
6. Keep `preview_only` at `True`. Press Run. The Watch node shows the number
   of tiles, jobs and tokens.
7. Set `preview_only` to `False`. Press Run again. This spends tokens.
8. Wait. Revit does not respond while the run is going.

Other inputs: `fetch_context` adds public buildings around your selection.
`wind_speed` (m/s) and `wind_direction` (degrees, 270 = from the west) are for the
`wind` analysis (ground). `surfaces` (`facades`, `roofs` or `all`) is for the facade part.

`analysis = show-last` draws the saved results again, free. The script saves the
last paid result of each target in `.infrared\revit-dynamo-last-result.json` in your
user folder (a file from an older version, with one result, still works).

If you edit a file in `ir_dynamo` or `ir_revit`, press Run again. The script
reloads the files. You do not need to restart Revit.

## Terrain and the ground level

Select the terrain (a Toposolid or a Topography surface) together with the buildings. If you select no terrain, the script uses every terrain element of the document and says so in the Watch text.

- With terrain, z = 0 of the analysis is the lowest terrain point near the buildings. Parts of buildings below the terrain (foundations) are left out. The ground result is drawn on the terrain.
- Without terrain, the ground is Revit elevation 0.
- Wind does not accept terrain. The buildings are lowered to their own base and the result is still drawn on the terrain.

## What you see

A coloured surface in the model (a DirectShape in Generic Models): a square per
ground cell, a triangle per facade cell. Look at it in a Shaded or Realistic 3D view.
The colours are the platform colours (see Colours). The Watch node shows a status
text: the location, the cost, the values and the legend.
Each target has its own shape in the model. A new ground run replaces only the old
ground shape, and a facade run only the old facade shape. The Watch text has a
legend for each target.

To delete a result, select the shape in a 3D view and delete it. Delete the legend
drafting view in the Project Browser. Manage > Purge Unused removes the
`Infrared ...` materials.

## Limits

- The run blocks Revit. Expect between 30 seconds and 5 minutes. Do not
  close Revit while it runs.
- The ground grid is placed by the SDK rule (row 0 is the south edge, `bounds`
  gives the place). Each ground run checks it: the Watch text has a "Grid
  alignment check" line with the share of the cells under the buildings that
  have no value, for the SDK rule and for the best shift of one cell. A warning
  line follows if a shift fits better.
- Dynamo in Revit 2026 uses Python 3.9. So this folder uses Python 3.9 syntax.
  This is the reason it does not follow the 3.11+ rule of the rest of this repository.
- The SDK is pinned to `infrared-sdk` 1.0.0. The script refuses any other version.
- The area must stay below 100 000 m in each direction.
- The weather comes from the public station catalog, for the project location.
- The Revit code (`ir_revit/`) is not covered by the automated tests. They cover
  `ir_dynamo` and the rotation maths only.

## Folder map

| Path | What it holds |
|---|---|
| `ir_dynamo/` | SDK calls and the target rules (`targets.py`). No Revit code. Tested with pytest. |
| `ir_revit/` | Revit API code: location, geometry, display, key dialog, `entry.py`. |
| `dynamo/` | `IR_Analysis.dyn`. Its Python node has a few lines and calls `ir_revit.entry.run`. |
| `build_libs.py` | Builds the libs zip for Python 3.9 on Windows x64. |
| `tests/` | pytest tests for `ir_dynamo`. |

## Colours

The result uses the colours of the Infrared platform. The SDK renderer (`render_grid_image_local`, with the colour registry) draws the result; each cell takes the colour of its own pixel. The ground matrix is rendered as it came from the SDK (row 0 is the south edge). Each distinct colour is one Revit material, for example `Infrared svf 08AEC4`. The Watch text gives the values (count, min, max, percentiles), the legend in bins with the count of each bin, and the number of meshes and colours that Revit built. The `legend` input sets the colour range:

- `trimmed` (default): the 2nd to 98th percentile of the values. A few extreme cells do not wash out the colours, so the variation is visible (for example the wind wake behind a building).
- `exact`: the minimum and maximum of the result.
- `platform`: the range that the platform uses. UTCI and wind speed have a fixed range there (wind speed: 0 to 20 m/s, so a 5 m/s wind shows in blue only); the other analyses use the 2nd to 98th percentile, as the platform renderer does.

Each run also draws the legend in a drafting view: "Infrared legend - ground" and "Infrared legend - facades" (Project Browser > Drafting Views). It shows one colour swatch and value range per bin, the highest value on top, and the colour range in use. A new run of the same target redraws the same view, so you can put it on a sheet once. (The Revit API cannot create a Legend view; a drafting view can go on a sheet in the same way.)

To see the same result with another range, set `legend`, set `analysis` to `show-last` and press Run. This is free.

UTCI and wind speed use a few flat platform colours. Set `gradient` to `True` to draw them as a smooth gradient through the same colours (the platform itself shows the flat bins). Sky view factor, solar radiation, sun hours and daylight are smooth gradients: up to 256 colours, so up to 256 materials; the legend text shows them in 10 bins. If the registry cannot be reached, built-in colours are used and the Watch text says so.
