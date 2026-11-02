# Infrared in Revit 2026 (Dynamo)

Two Dynamo scripts run an Infrared analysis on the buildings you select in Revit.
They show the result in the active view, with a legend.

| Script | What it analyses | Analyses |
|---|---|---|
| `IR_Ground.dyn` | The ground around the buildings | `svf`, `solar`, `sun-hours`, `wind`, `utci` |
| `IR_Facades.dyn` | The walls and roofs of the buildings | `svf`, `solar`, `sun-hours`, `daylight` |

## What it does

1. You select buildings in Revit.
2. The script reads their geometry and the project location.
3. The script shows the cost of the run. This is free.
4. You set `preview_only` to `False`. The script runs the analysis on the Infrared servers.
5. Revit shows coloured points in the active view.

## Requirements

- Revit 2026 with Dynamo 3.4.
- An Infrared API key (<https://infrared.city>).
- Windows x64. The libs zip holds Windows packages only.

## Install

Choose one way.

**Download.** Get `infrared-dynamo-libs.zip`. Unzip it into this folder:
`%APPDATA%\Infrared\revit-dynamo`. The folder must now hold `ir_dynamo`, `revit`,
`dynamo` and the SDK packages.

**Build it.** Run this on any machine that has Python 3.9 or later and pip:

```text
python build_libs.py
```

The script writes `build/infrared-dynamo-libs.zip` (about 50 MB). Unzip it as above.

Then open `dynamo/IR_Ground.dyn` or `dynamo/IR_Facades.dyn` in Dynamo.
Dynamo opens both files in Manual run mode. Nothing runs until you press Run.

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

## Run IR_Ground and IR_Facades

1. Open the script. Check that `libs_folder` is the folder you unzipped to.
2. Open a 3D view or a plan view. The result goes into the active view.
3. Select your buildings in Revit. In Dynamo, click "Select Model Elements" and
   press Select. Walls, floors, roofs, masses and families all work.
4. Set `analysis`. Use one of the labels in the table above.
5. Set `months` (for example `6-8`) and `hours` (for example `8-18`).
6. Keep `preview_only` at `True`. Press Run. The Watch node shows the number
   of tiles, jobs and tokens.
7. Set `preview_only` to `False`. Press Run again. This spends tokens.
8. Wait. Revit does not respond while the run is going.

Other inputs: `fetch_context` adds public buildings around your selection.
IR_Ground has `wind_speed` (m/s) and `wind_direction` (degrees, 270 = from the
west) for the `wind` analysis. IR_Facades has `surfaces`: `facades`, `roofs` or `all`.

If you edit a file in `ir_dynamo` or `revit`, press Run again. The script
reloads the files. You do not need to restart Revit.

## What you see

Coloured points in the active view. Blue is a low value. Red is a high value.
The legend has the name of the analysis and the unit. The Watch node shows a
status text: the location, the cost, and how many points Revit shows.
Each run clears the points of the last run in that view.

## Limits

- The run blocks Revit. Expect between 30 seconds and 5 minutes. Do not
  close Revit while it runs.
- Facade values show as one point at the centre of each result triangle.
  They do not colour the faces. This is version 1.
- The ground grid is placed with a measured shift of one cell
  (`GROUND_GRID_SHIFT` in `ir_dynamo/results.py`). One live run gave this value.
  The cause is not known yet. Treat the cell position as correct to about one cell.
- Dynamo in Revit 2026 uses Python 3.9. So this folder uses Python 3.9 syntax.
  This is the reason it does not follow the 3.11+ rule of the rest of this repository.
- The SDK is pinned to `infrared-sdk` 1.0.0. The script refuses any other version.
- The area must stay below 100 000 m in each direction.
- The weather comes from the public station catalog, for the project location.
- The Revit code (`revit/`) is not covered by the automated tests. They cover
  `ir_dynamo` and the rotation maths only.

## Folder map

| Path | What it holds |
|---|---|
| `ir_dynamo/` | SDK calls. No Revit code. Tested with pytest. |
| `revit/` | Revit API code: location, geometry, display, key dialog, `entry.py`. |
| `dynamo/` | The two `.dyn` files. Each Python node has a few lines and calls `revit.entry.run`. |
| `build_libs.py` | Builds the libs zip for Python 3.9 on Windows x64. |
| `tests/` | pytest tests for `ir_dynamo`. |
