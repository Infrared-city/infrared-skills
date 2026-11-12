# Infrared in Revit 2026 (Dynamo)

One Dynamo script, `IR_Analysis.dyn`, runs an Infrared analysis on the buildings you select in Revit.
It shows the result as a coloured surface in the model, with a legend. The script has one input:
the `command` node. You type one line, for example `svf`, and press Run.

## Quick start

Do steps 1 to 3 one time. Then you only need steps 4 to 6.

1. **Install.** Unzip `infrared-dynamo-libs.zip` into `%APPDATA%\Infrared\revit-dynamo` (see Install).
2. **Open.** In Revit, open Manage > Dynamo, and open `%APPDATA%\Infrared\revit-dynamo\dynamo\IR_Analysis.dyn`.
3. **Key.** Type `set-key` in the `command` node and press Run. Paste your API key and press Save.
4. **Select.** In Revit, select the buildings. Or type `select`, press Run, click the buildings in Revit and press Finish. Open a Shaded 3D view.
5. **Preview.** Type `svf` in the `command` node and press Run. The Watch node shows the cost. This is free.
6. **Run.** Add the word `run` (`svf run`) and press Run again. Revit shows the result in the model.

Before the first real run, set the project location in Manage > Location (see "Set the
project location in Revit"). The sun, the weather and the public buildings come from it.

Type `help` in the `command` node to see every word.

## Copy a command

Each line is a free preview. Add `run` at the end to run it and pay tokens.

| You want | Type |
|---|---|
| Sky view factor on the ground | `svf` |
| Sky view factor on the ground and the facades | `svf both` |
| Sun hours in summer on the facades | `sun-hours facades months jun-aug` |
| Daylight for the whole year, 8 to 18 h | `daylight both months 1-12 hours 8-18` |
| Solar radiation on the roofs only | `solar facades surfaces roofs` |
| Wind of 5 m/s from the west | `wind 5 W` |
| Pedestrian wind comfort (whole year) | `pwc` |
| Heat stress on summer afternoons | `utci months jun-aug hours 12-15` |
| Pick the buildings in Revit | `select` |
| Pick elements inside a linked model | `select link` |
| The whole model, without a selection | `svf model` |
| With the public buildings around the site | `svf both context` |
| A larger ground area around the buildings | `svf margin 100` |
| A second result next to the first one | `daylight facades months 1-12 keep` |
| The last result again with another colour range (free) | `show-last legend exact` |
| An OBJ file for the Infrared platform (free) | `export-obj` |

## The analyses

| Target word | What it analyses | Analysis words |
|---|---|---|
| `ground` | The ground around the buildings | `svf`, `solar`, `sun-hours`, `daylight`, `wind`, `utci`, `pwc`, `tcs` |
| `facades` | The walls and roofs of the buildings | `svf`, `solar`, `sun-hours`, `daylight` |
| `both` | Both, one after the other | `svf`, `solar`, `sun-hours`, `daylight` on both; `wind`, `utci`, `pwc`, `tcs` on the ground only |

One Infrared request computes the ground grid or the facades, not both. So `both`
is **two runs and two costs**. The preview shows both costs and their sum. If the
analysis exists on one target only (for example `wind`), `both` runs it there and
the Watch text says that the other target was skipped.

`pwc` (pedestrian wind comfort) and `tcs` (thermal comfort statistics) take a criterion or
subtype as the next word. Without it, the first one is used.

- `pwc`: `lawson-lddc` (default), `lawson-2001`, `lawson-1970`, `davenport`,
  `nen-8100-comfort`, `nen-8100-safety`, `vdi-3787`. Example: `pwc lawson-2001`.
- `tcs`: `thermal-comfort` (default), `heat-stress`, `cold-stress`. Example: `tcs heat-stress`.

Both read the weather of the `months` and `hours` window. PWC is normally read over a whole
year (months 1-12, hours 0-23); with a shorter window the Watch text says so. Like `wind`,
PWC does not take terrain.

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
The script looks for the libs in `%APPDATA%\Infrared\revit-dynamo`. To use another
folder, set the `INFRARED_DYNAMO_LIBS` environment variable to it.

The graph has three nodes: `command` (the input), the Python node and a Watch node
(the output). So it also runs from Dynamo Player: the command is the one input there.

## Set the API key

1. Type `set-key` in the `command` node and press Run. A dialog opens.
2. Paste your key and press Save. The dialog shows dots, not the key.
3. Type the next command.

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
   is far from the internal origin, add `lat` and `lon` to the command, for
   example `lat 48.2085 lon 16.3721`. Use the position of the internal origin.
5. The position matters most with the word `context`. The public buildings are
   then placed from this position.

A new Revit project has a default location in the Boston area. The sun, the weather
and the public buildings come from the project location, so a model of another city
that keeps the default gives wrong results. The Watch text starts with a warning then.

## Run IR_Analysis

1. Open the script in Dynamo.
2. Open a 3D view (Shaded or Realistic). The result is a shape in the model, so every view shows it.
3. Select your buildings in Revit. Walls, floors, roofs, masses and families all work.
   There is no selection node: the script reads the selection of Revit. You can also
   type `select` and press Run: go to the Revit window, click the buildings, and
   press Finish in the Options Bar (top left, under the ribbon; Esc cancels). The
   next commands use these elements. `select link` does the same for
   elements inside linked models.
4. Type a command in the `command` node, for example `pwc`, `wind 5 270` or
   `utci months jun-aug hours 12-15`. Press Run. Without the word `run`
   it is a free preview: the Watch node shows the number of tiles, jobs and tokens.
5. To run it, add the word `run` (the Watch text gives the whole line:
   `To run it (paid): ...`). Press Run again. This spends tokens.
6. Wait. Revit does not respond while the run is going.

Type `help` to see every word. The words can be in any order.

| Words | What they set | Default |
|---|---|---|
| `svf`, `solar`, `sun-hours`, `daylight`, `wind`, `utci`, `pwc`, `tcs` | The analysis | none: you must give one |
| `ground`, `facades`, `both` | The target | `ground` where the analysis runs, else `facades` |
| `months 6-8`, `hours 9-17` | The time window | `6-8` and `8-18`; PWC the whole year |
| `wind 5 270` or `wind 5 W` | Wind analysis: speed (m/s) and the direction it comes from | 5 m/s from 270 |
| `surfaces roofs` | Facades only: `facades`, `roofs` or `all` | `all` |
| `model`, `alone` | What gets a result (see the next section) | the selection |
| `context` | Add the public buildings around the site | off |
| `margin 100` | Metres of ground around the selection | 30 (ground), 5 (facades) |
| `legend exact`, `gradient` | The colours (see Colours) | `legend platform` |
| `lat 48.2085 lon 16.3721` | Another location | the Revit project location |
| `keep` | The earlier result stays in the model | the new result replaces it |
| `run` | Run and pay tokens | free preview |

Other commands: `show-last` draws the saved results again, free (it takes `legend`,
`gradient` and `keep`). The script saves the last paid result of each target in
`.infrared\revit-dynamo-last-result.json` in your user folder. `export-obj` writes an
OBJ file for the platform upload, free (see "Export to the Infrared platform").
`set-key` opens the API key dialog.

The Watch text starts with `Command:` and the line with every value filled in. The
warnings and errors come next, in one block, before the other lines. The same text
goes to `.infrared\revit-dynamo-runs.log` in your user folder.

If nothing is selected in Revit, the script uses the last selection in the same
model again (of the last run or of `select`). The Watch text says so.

If you edit a file in `ir_dynamo` or `ir_revit`, press Run again. The script
reloads the files. You do not need to restart Revit.

## What gets a result, and what only shades

| Command | A result is drawn on | These only shade |
|---|---|---|
| (no word) | The elements you selected | The other building elements of the model and of its loaded links |
| `model` | Every building element of the model and of its loaded links. No selection is needed. | Nothing more |
| `alone` | The elements you selected | Nothing. Faster on a large model. |
| + `context` | The above, and the public buildings | Nothing more |

- A linked Revit model: its elements shade the result. To get a result on them, pick
  an element inside the link with Tab, or select the whole link, or use `model`.
  A link that is not loaded is not read; the Watch text says so.
- A building element is an element of a building category (walls, curtain panels and
  mullions, columns, beams, floors, roofs, windows, masses, parts) or an import
  (DWG, IFC). The elements you select are always read, whatever their category.
- Elements that only shade are read up to 400 m from the selection, at Medium detail.
  The Watch text gives their number.
- The run area is the box around the result elements plus the margin. The ground
  result fills it. With `context`, the default margin is the largest one that costs
  no extra tile: the area is about 500 m wide with the selection in the middle, and
  the facade result covers the public buildings inside it. Set `margin` for another size.
- The Watch text has an `Area:` line with the size and the margin.

## Terrain and the ground level

The terrain is the Toposolids and Topography surfaces of your selection. If you selected none, the script uses every Toposolid and Topography surface of the model and of its loaded links. The script uses their upward faces only, and does not analyse them as buildings. Without any, the ground is a flat plane at Revit elevation 0.

A ground modelled as a floor, a mass or an import is not terrain: if you select it, it is analysed as a building. Model the site as a Toposolid. The Watch text says which, and lists the categories of the selection, so you can see what the script found.

- With terrain, z = 0 of the analysis is the lowest terrain point near the buildings. Parts of buildings below the terrain (foundations) are left out. The ground result is drawn on the terrain.
- Without terrain, the ground is Revit elevation 0.
- Wind does not accept terrain. The buildings are lowered to their own base and the result is still drawn on the terrain.

## Export to the Infrared platform

The platform upload (platform.infrared.city) reads GeoJSON, OBJ and EPW files, not RVT or IFC.
Type `export-obj` and press Run. This is free: there is no API call, and no key is needed. `export-obj model` writes every building element of the open model, without a selection. The export writes the open model only, not its links.
The script writes `Documents\Infrared\<model name>-<date>-<time>.obj`. The Watch text gives the path.

The file:

- is in metres, with Z up and +Y north (true north): the axes the platform expects;
- has all building elements in one object, `building_model`, and one object per terrain element, `ground_<ElementId>`. A comment line `# element <ElementId>: <category>` is above each element. One object, because the platform gives a separate object that starts above the ground (for example the walls of a bay window on an upper floor) a floor on the ground: you see its outline on the ground in front of the building;
- leaves out the parts below the ground (basements, foundations), because the platform puts the lowest point of the model on its ground. An element that is then less than 0.5 m above the ground (a ground-floor slab, a pad) is left out too: it is ground, not building;
- holds the terrain near the buildings (50 m around them), from the Toposolids;
- holds only the building categories: walls, curtain panels and mullions, columns, structural columns and framing (beams), floors, slab edges, roofs, windows, masses and parts. Doors, stairs, railings, furniture, fixtures, equipment and generic models are left out. `export-obj all` keeps every category.

The OBJ has no georeference. The Watch text gives the longitude and latitude of the middle of the buildings.
On the platform, upload the file, drag the model to that point on the map, and then select Save.
In "Review model", check that the unit is metres, the up axis is z, and that the buildings are buildings.
If the model is upside down, clear "Flip vertical". The platform takes the denser end of the model as
the ground; a building with a detailed roof and no terrain can look denser at the top.

Keep the file below 40 MB, the platform limit. The Watch text gives the file size and the
triangles of each category, and the categories that were left out. If the file is too large,
select the outer shell only. Interior walls and floors do not change the outdoor result.

## What you see

A coloured surface in the model (a DirectShape in Generic Models): a square per
ground cell, a triangle per facade cell. Look at it in a Shaded or Realistic 3D view.
The colours are the platform colours (see Colours). The Watch node shows a status
text: the location, the cost, the values and the legend.
Each target has its own shape in the model. A new ground run replaces only the old
ground shape, and a facade run only the old facade shape, whatever the analysis.
The Watch text has a legend for each target.

To keep an earlier result, add the word `keep` to the new command, for example
`daylight facades months 1-12 run keep`. The earlier shape stays in the model and
its legend view gets a name with its command and time. No later run deletes a kept
shape. Properties > Comments of a shape gives its command and time. The shapes lie
in the same place: use one 3D view per result, and hide the other shapes there
(Hide in View > Elements).

To delete a result, select the shape in a 3D view and delete it. Delete the legend
drafting view in the Project Browser. Manage > Purge Unused removes the
`Infrared ...` materials.

## When something is wrong

Read the Watch text first. Its warnings and errors are in one block at the top.

| You see | Do this |
|---|---|
| `The Infrared libs are not in ...` | Unzip the libs zip into `%APPDATA%\Infrared\revit-dynamo` (see Install). |
| `No API key` | Type `set-key` and press Run. |
| `No building geometry found` | Select walls, floors, roofs or masses in Revit (or use `select`), or add the word `model`. |
| `Unknown word 'facdes'. Did you mean 'facades'?` | Correct the word. Type `help` to see every word. |
| A warning about the Boston area | Set Manage > Location, or add `lat` and `lon` to the command. |
| Press Run, and nothing changes | Look for a Revit dialog or a pick that waits (press Esc in Revit). In an old Dynamo the same command does not run two times: change the command. |
| No colours in the view | Use a Shaded or Realistic 3D view, not Hidden Line or Wireframe. |
| Everything has one colour | Add `legend trimmed` (free: `show-last legend trimmed`). |
| The ground result is at the wrong height | Model the site as a Toposolid. A floor or a mass is not terrain. |
| Only one building can be selected | The others are in a linked model. Use `select link`, or pick one with Tab, or use `model`. |
| The run is slow before it starts | Add `alone`: the rest of the model is then not read for shade. |
| `This graph is an older version` | Open the new `IR_Analysis.dyn` from the libs folder. |

The full text of each run is also in `.infrared\revit-dynamo-runs.log` in your user folder.

## Limits

- A new run replaces the earlier result of the same target (ground or facades), also
  of another analysis. Add `keep` to keep it. `show-last` holds only the last result
  of each target.
- A tile of the SDK starts at the south-west corner of the run area. A small area
  without `context` has its buildings in that corner, so elements more than about
  150 m south or west of the area do not shade it. With `context` the area fills the tile.
- Reading the elements that only shade takes time on a large model. `alone` skips it.
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
- The weather comes from the public station catalog: the station nearest to the project location, within 50 km. The Watch text names it, for example `Weather: station Wien-Innere.Stadt, AUT (110340, TMYx), 1.2 km from the site.`, and asks you to check the location when it is more than 20 km away. Solar, UTCI, PWC and TCS read weather; SVF, sun hours, daylight and wind do not.
- The Revit code (`ir_revit/`) is not covered by the automated tests. They cover
  `ir_dynamo` and the rotation maths only.

## Folder map

| Path | What it holds |
|---|---|
| `ir_dynamo/` | SDK calls, the target rules (`targets.py`) and the `command` line (`command.py`, `command_help.py`). No Revit code. Tested with pytest. |
| `ir_revit/` | Revit API code: selection (`revit_selection.py`), links and shade (`revit_scene.py`), location, geometry, display, key dialog, `entry.py`. |
| `dynamo/` | `IR_Analysis.dyn`. Its Python node has a few lines and calls `ir_revit.entry.run`. |
| `build_libs.py` | Builds the libs zip for Python 3.9 on Windows x64. |
| `tests/` | pytest tests for `ir_dynamo`. |

## Colours

The result uses the colours of the Infrared platform. The SDK renderer (`render_grid_image_local`, with the colour registry) draws the result; each cell takes the colour of its own pixel. The ground matrix is rendered as it came from the SDK (row 0 is the south edge). Each distinct colour is one Revit material, for example `Infrared svf 08AEC4`. The Watch text gives the values (count, min, max, percentiles), the legend in bins with the count of each bin, and the number of meshes and colours that Revit built. The `legend` word sets the colour range:

- `platform` (default): the range that the platform uses, so Revit and the platform show the same colours. UTCI and wind speed have a fixed range there (wind speed: 0 to 20 m/s, so a 5 m/s wind shows in blue only); the other analyses use the 2nd to 98th percentile, as the platform renderer does.
- `trimmed`: the 2nd to 98th percentile of the values. A few extreme cells do not wash out the colours, so the variation is visible (for example the wind wake behind a building).
- `exact`: the minimum and maximum of the result.

Each run also draws the legend in a drafting view: "Infrared legend - ground" and "Infrared legend - facades" (Project Browser > Views > Drafting Views). It shows one colour swatch and value range per bin, the highest value on top, the colour range in use, and the run: the command, the location and true north, the weather station, the date and time. For PWC it shows one swatch per comfort class (for example "A Frequent Sitting"), the first class on top, and no range. A new run of the same target redraws the same view, so you can put it on a sheet once. (The Revit API cannot create a Legend view; a drafting view can go on a sheet in the same way.)

To see the same result with another range, type `show-last legend exact` and press Run. This is free.

UTCI and wind speed use a few flat platform colours, as on the platform. Add the word `gradient` to draw them as a smooth gradient through the same colours (the platform itself shows the flat bins). Sky view factor, solar radiation, sun hours and daylight are smooth gradients: up to 256 colours, so up to 256 materials; the legend text shows them in 10 bins. If the registry cannot be reached, built-in colours are used and the Watch text says so.
