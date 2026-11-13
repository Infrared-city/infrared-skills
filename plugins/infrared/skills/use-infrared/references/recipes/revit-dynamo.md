# Recipe: Infrared SDK in Revit 2026 (Dynamo)

Use the Python SDK (`infrared-sdk` 1.0.0) from a Dynamo Python node in Revit 2026. There is no plugin to install: the user unzips a folder and opens one `.dyn` file.

The working script is the cookbook app [`cookbook/apps/revit-dynamo`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/revit-dynamo). Start from it. Do not write a new graph from zero. Its README is the user guide; this page is for the agent.

Companion file: [`revit-dynamo-pitfalls.md`](revit-dynamo-pitfalls.md), the short list of traps. Read it before you change code and when a run fails.

API detail: https://infrared.city/docs/sdk/ (agents: https://infrared.city/docs/sdk/llms.txt).

## 1. What the user gets

- One graph, `IR_Analysis.dyn`. The user selects buildings in Revit, types one command line and presses Run. The graph has three nodes: `command`, the Python node and a Watch node, so it also runs from Dynamo Player.
- Targets: `ground` (a grid around the buildings), `facades` (walls and roofs) or `both` (two runs, two costs).
- Analyses: `svf`, `solar`, `sun-hours`, `daylight`, `wind`, `utci`, `pwc`, `tcs` on the ground; `svf`, `solar`, `sun-hours`, `daylight` on the facades.
- `pwc` (pedestrian wind comfort) and `tcs` (thermal comfort statistics) take a criterion or subtype as the next word. Without it, the first one is used:
  - `pwc`: `lawson-lddc` (default), `lawson-2001`, `lawson-1970`, `davenport`, `nen-8100-comfort`, `nen-8100-safety`, `vdi-3787`. Example: `pwc lawson-2001`.
  - `tcs`: `thermal-comfort` (default), `heat-stress`, `cold-stress`. Example: `tcs heat-stress`.
- Not in the script: the interior analyses (daylight factor, energy balance) and own sensor points. Do not offer them in Revit.
- The result is a coloured surface in the model, a legend in a drafting view, and a status text in a Watch node.

## 2. Install

Dynamo in Revit 2026 runs CPython 3.9.12. It has no pip. So the packages are built outside Revit.

1. On any machine with Python 3.9 or later and pip, run `python build_libs.py` in the app folder. It downloads the wheels of `infrared-sdk[geodata]==1.0.0` for Python 3.9 on Windows x64 and writes `build/infrared-dynamo-libs.zip` (about 50 MB).
2. Unzip it into `%APPDATA%\Infrared\revit-dynamo` (the libs folder). The folder must hold `ir_dynamo`, `ir_revit`, `dynamo` and the SDK packages.
3. Open `dynamo/IR_Analysis.dyn` in Dynamo. The stub reads the libs from `%APPDATA%\Infrared\revit-dynamo`; the `INFRARED_DYNAMO_LIBS` environment variable names another folder.

The zip holds Windows x64 packages only. The script refuses an SDK other than 1.0.0.

## 3. API key and location

- Key: the command `set-key`. A password dialog opens and saves the key in `~/.infrared/api_key.txt`. The `INFRARED_API_KEY` environment variable has priority. Never put the key in the `.dyn` file, in the log or in the chat.
- Location: Revit stores one latitude and longitude (Manage > Location) and a true north angle. The script uses them as the position of the **internal origin**, not of the Project Base Point or the Survey Point. If the model is far from the internal origin, the user adds `lat 48.2085 lon 16.3721` to the command.
- The location matters for the sun, the weather and `context` (public buildings around the selection). An error of some metres changes nothing in a run without context.
- A new Revit project has a default location in the Boston area. A model of another city that keeps it is analysed with the sun and weather of Boston. The Watch text then starts with a warning: tell the user to set Manage > Location, or give `lat` and `lon`.

### The first session, in order

Lead a new user through these steps, one at a time. The README has the same steps as a table ("A first session, from zero").

1. Unzip the libs zip into `%APPDATA%\Infrared\revit-dynamo`. Delete an earlier version first.
2. In Revit, open Manage > Dynamo and open `dynamo\IR_Analysis.dyn` from that folder.
3. `help`: the Watch node lists every word.
4. `set-key`: the user pastes the API key in the dialog. One time.
5. Manage > Location: the city of the project.
6. Open a Shaded 3D view.
7. `select`: the user clicks the buildings and presses Finish.
8. `svf`: the free preview, with the cost.
9. `svf run`: the first result and its legend view.
10. `wind 5 W run`: a second result. The first one stays in the model, hidden in this view.
11. `VG` > Filters in the 3D view: the user shows or hides each result.
12. `show-last legend trimmed`: the last result with another range, free.
13. `solar facades run`: a result on the walls and roofs.
14. `export-obj`: a file for the platform, free.
15. `clear`: deletes every result, legend view and filter.

## 4. The command

The graph has one input, the `command` node. One line runs everything. A word that is not in the line takes the default below. Words, any order, any case:

| Words | Default when left out |
|---|---|
| `svf`, `solar`, `sun-hours`, `daylight`, `wind`, `pwc`, `tcs`, `utci`; `pwc lawson-2001`, `tcs heat-stress` (also `lddc`, `vdi`, `nen`, `heat`, `cold`) | (one is needed); PWC `lawson-lddc`, TCS `thermal-comfort` |
| `show-last` (takes `legend`, `gradient`), `export-obj [all] [model]`, `clear`, `set-key`, `help` | |
| `select`, `select link` | Revit asks the user to click the buildings (or elements inside linked models) and to press Finish. The next commands use them. During the pick the result shapes are hidden in the active view and the Mass category is shown |
| `ground`, `facades`, `both` | `ground` where the analysis runs, else `facades` |
| `months 6-8` or `months jun-aug`, `hours 9-17` | `6-8`, `8-18`; PWC `1-12`, `0-23` |
| `wind 5 270`, `wind 5 W` (or `speed 5 direction 270`) | 5 m/s from 270° (west). Wind analysis only: an error with any other |
| `surfaces facades\|roofs\|all` | `all`; facades only |
| `model`, `alone` | The selection gets the result; the rest of the model and its links only shade. `model`: every building element of the model and its loaded links gets a result, no selection needed. `alone`: nothing else shades (faster) |
| `context` | off. Adds the public buildings; the result covers them too, inside the run area |
| `margin 100` | Metres around the selection: 30 (ground), 5 (facades); with `context` the largest margin that costs no extra tile (the area is about 500 m wide) |
| `legend platform\|trimmed\|exact` (or the bare word), `gradient` | `platform`, off |
| `lat 48.2085 lon 16.3721` | the Revit project location |
| `keep` | read and not used (until 2026-11-13 it kept the earlier result): every result stays now |
| `run` | **no `run` = free preview**. Only `run` spends tokens |

Examples: `pwc` · `wind 5 270 run` · `utci months jun-aug hours 12-15` · `solar both context run` · `daylight facades model run` · `clear` · `show-last legend exact`. Each run writes `Command: <the line with every value filled in>` at the top of the Watch text, then a `Warnings (n):` block with every warning and error, then the other lines; a preview ends with `To run it (paid): <line> run`. A wrong word gives `Command error: Unknown word 'facdes'. Did you mean 'facades'?` and runs nothing. An empty command gives the help text. The script marks its node as modified on each run, so the same line can run again (the log has a `rerun:` line); it skips the execution that Dynamo then makes with the earlier text (a `skipped:` line).

Selection: there is no selection node. The script reads the selection of Revit, or the picks of the `select` command; with nothing selected it uses the last selection in the same model again. Walls, floors, roofs, masses, families, DirectShapes and imported meshes work. An element inside a linked model is picked with Tab; a selected link gives a result on all its building elements. The building elements that are not selected (the building categories and the imports, in the model and in its loaded links, up to 400 m away) only shade: the Watch text counts them in a `Shade only:` line. The terrain is the Toposolids and Topography surfaces of the selection, else every one of the model and its links; the ground result is drawn on it. A ground modelled as a floor, a mass or an import is analysed as a building if it is selected: the site must be a Toposolid. Without terrain the ground is a flat plane at Revit elevation 0. Wind and PWC do not accept terrain: the buildings are lowered to their base, and the result is drawn on the terrain.

## 5. What a run does

1. Reads the location, the selected elements (Solid and Mesh geometry, in feet), the elements that only shade (the rest of the model and its loaded links) and the terrain. Solar, UTCI, PWC and TCS take the weather of the nearest public station within 50 km; the Watch text names it with its distance (`Weather: station ..., 1.2 km from the site.`) and asks to check Manage > Location above 20 km. Read this line before you explain a result.
2. Converts to the SDK frame: metres, x east, y north, origin at the south-west corner of the polygon bounding box, turned by true north. The polygon is the box of the result elements plus the margin; the `Area:` line gives its size.
3. `preview_area` (free) or `run_area_and_wait` (paid). Revit does not respond during the run: 30 seconds to 5 minutes.
4. Places the ground grid by the SDK rule (row 0 is the south edge, `bounds` gives the place, the cell centre is at `(col + 0.5, row + 0.5)` cells from the south-west corner). A "Grid alignment check" line in the Watch text compares this rule with a one-cell shift.
5. Colours each cell with the SDK renderer (`render_grid_image_local` and the platform colour registry): one pixel per cell.
6. Draws the result and the legend, saves the result for `show-last`, and writes the status text to the Watch node and to the log.

## 6. Results in Revit

- **Shape.** One DirectShape per run and target (Generic Models, name "Infrared result (ground)" or "(facades)"). Look at it in a Shaded or Realistic 3D view. Every result stays in the model; only `show-last` replaces a shape, that of the same run. Properties > Comments of a shape gives its target, command and time (`revit_results.shape_label`).
- **View filters.** Each result has a filter `Infrared result - <target> - <command> (<time>)` on its Comments (`revit_filters`). A run adds the filters to the active view and hides the earlier results of its target there, because they lie in the same place. The user shows or hides a result in Visibility/Graphics (VG) > Filters; another view shows every result until the filters are added there.
- **Clear.** The command `clear` deletes every result shape, legend view and result filter of the model. The saved results stay for `show-last`. A facade result has no cells on the shade-only elements: the surface id of the SDK is `<building id>/<number>`, and the script drops the cells of those buildings.
- **Edges.** On a flat ground the cells of one colour are joined into one face, so only the borders between colours show as lines. To hide those too, clear Show Edges in the view's Graphic Display Options. Do not give each colour a subcategory with its line colour: with 263 of them, Dynamo did not start another run (Revit itself still responded).
- **Materials.** One material per colour, for example `Infrared svf 08AEC4` or `Infrared pwc lawson-lddc 0000FF`. A smooth scale has up to 256 colours, so up to 256 materials.
- **Legend.** A drafting view per result, named "Infrared legend - <target> - <command> (<time>)" (Project Browser > Views > Drafting Views). Each run has its own view; `show-last` redraws the view of its result, so it can stay on a sheet. Under the swatches it has the run: the command, the location and true north, the weather station, the date and time. The Revit API cannot create a Legend view.
- **PWC classes.** The PWC result is a comfort class per cell (A, B, C, ... S). The legend shows one swatch per class with its name (for example "A Frequent Sitting"), the first class on top, and no range; `legend` and `gradient` do not apply. The Watch text gives the share of cells in each class. TCS is a percentage of time (0 to 100 %) on the colour scale of its subtype.
- **Colour range** (the `legend` word):
  - `platform` (default): the fixed range of the platform where it has one (wind speed 0 to 20 m/s, UTCI -40 to 46 °C), else the 2nd to 98th percentile. Revit then shows the colours of the platform. A 5 m/s wind shows in blue only.
  - `trimmed`: the 2nd to 98th percentile of the values. Use it to see the variation (for example the wind wake behind a building).
  - `exact`: the minimum and maximum of the result.
- **Another range, free.** The command `show-last legend exact` (or `trimmed`, `gradient`). The saved results are in `~/.infrared/revit-dynamo-last-result.json`, one entry per target and per Revit document.
- **Delete a result.** Select the shape in a 3D view and delete it. Delete the legend drafting view in the Project Browser. Manage > Purge Unused removes the `Infrared ...` materials.

## 6a. Export to the platform

The platform upload reads GeoJSON, OBJ and EPW, not RVT or IFC ([`platform-byo-upload.md`](../platform-byo-upload.md)). The command `export-obj` writes `Documents\Infrared\<model>-<date>-<time>.obj`; `export-obj model` writes every building element of the open model and of its loaded links without a selection. A link selected as a whole and elements picked inside a link are written too; the terrain of a link is not. It makes no API call and needs no key.

- Metres, Z up, +Y north (the platform takes Z as up). All building elements are one object, `building_model`, with a comment `# element <ElementId>: <category>` above each element; each terrain element is `ground_<ElementId>`. The platform splits an object into connected parts and gives a raised part with nothing under it a floor at z = 0; with one object per element, a bay window on an upper floor got its outline drawn on the ground. No `usemtl` lines: a Revit material name like "Concrete" is a ground word for the platform classifier.
- The parts below the ground are left out, and triangles that cross it are cut: the platform puts the lowest point on its ground, so a basement would lift the building. An element less than 0.5 m above the ground after the cut (a ground-floor slab) is left out.
- The terrain within 50 m of the buildings is in the file.
- Only the building categories go in (`obj_export.is_building`: walls, curtain panels and mullions, columns, beams, floors, roofs, windows, masses); `export-obj all` keeps every category. The rule matches the BuiltInCategory name first, the English display name second. A whole architectural model with every category gave 2 million triangles and 71 MB; the Watch text gives the triangles of each category.
- The OBJ has no georeference. The Watch text gives the longitude and latitude of the middle of the buildings; the user drags the model there before Save.
- The platform limit is 40 MB. The Watch text gives the size.
- The platform guesses the vertical sign from point density (the denser end is the ground). A Revit building without terrain has a dense roof, so it can arrive upside down: tell the user to clear "Flip vertical" in Review model.
- Not yet checked on the platform: that a sloped `ground_*` object keeps its heights.

## 6b. Guide the user through a run

Give the user these steps. The agent cannot press Run in Revit.

1. Once: install the libs folder (section 2), open `IR_Analysis.dyn`, set the API key (section 3), and check Manage > Location.
2. In Revit, select the buildings (or use the word `model`). The Toposolids are the ground.
3. Write the command line for the user's request (section 4), without `run`: "PWC on the ground, west wind comfort" -> `pwc`; "summer afternoon heat on the facades" -> `utci facades months jun-aug hours 12-15`. The user pastes it into the `command` node and presses Run. The Watch text gives the cost, free.
4. If the cost is correct, the user pastes the `To run it (paid): ...` line from the Watch text (the same line with `run`) and presses Run. Revit does not respond for 30 seconds to 5 minutes.
5. Look at the result in a Shaded 3D view and the legend in the drafting view. Then read the end of `~/.infrared/revit-dynamo-runs.log` and explain the result to the user.

## 7. Change the script for the user

The code has three layers. Keep logic out of the `.dyn` file.

| Layer | Holds | Tested |
|---|---|---|
| `dynamo/IR_Analysis.dyn` | The `command` node, a Watch node and one Python node of a few lines (the stub). The stub puts the libs folder on `sys.path`, removes the loaded `ir_*` modules, calls `ir_revit.entry.run` and writes a traceback to the log | No |
| `ir_revit/` | Revit API code: selection, links and shade elements, location, geometry, display, legend view, key dialog, `entry.py` | Only in Revit |
| `ir_dynamo/` | SDK calls, payloads, frame, targets, colours, legend layout, summary. No Revit import | `pytest` in a normal Python |

Rules:

- Write Python 3.9 syntax in all three layers (no `match`, no `X | Y` types at run time).
- Put new logic in `ir_dynamo/` with a test. Keep `ir_revit/` to Revit API calls.
- A new analysis is a row in `ir_dynamo/settings.py` (`ANALYSES`: label, SDK type, unit, targets, period, weather, wind) and, if it needs a new request type, a branch in `ir_dynamo/payloads.py`. The `command` words come from that table (`ir_dynamo/command.py`).
- A new input is a new word in `ir_dynamo/command.py` (a field of `Command`, the parser, `Command.text`, the help line) with a test. Do not add an input node: the graph has the `command` node only. The stub calls `entry.run(command=IN[0])`; give the user the exact stub text to paste when it changes.
- Do not copy colour, legend or grid rules from other hosts. Use the SDK renderer and the SDK result fields.

## 8. Work from an agent

The agent cannot press Run in Revit. The loop is:

1. Change the files in the repo. Run `pytest tests` in the app folder and check the exit code, not only the last lines of the output.
2. Copy the changed files into the libs folder (`%APPDATA%\Infrared\revit-dynamo`). Revit runs that copy, not the repo.
3. Ask the user to press Run (preview first).
4. Read the end of `~/.infrared/revit-dynamo-runs.log`. Each run appends its status lines, or the traceback. Live progress lines show the seconds since the run started.
5. If the log has no new lines, the run did not reach the script: see the pitfalls page.

Ask the user for a paid run before you give a command with `run`. Keep paid test runs small: one building, one target.
