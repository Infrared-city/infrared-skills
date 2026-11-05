# Recipe: Infrared SDK in Revit 2026 (Dynamo)

Use the Python SDK (`infrared-sdk` 1.0.0) from a Dynamo Python node in Revit 2026. There is no plugin to install: the user unzips a folder and opens one `.dyn` file.

The working script is the cookbook app [`cookbook/apps/revit-dynamo`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/revit-dynamo). Start from it. Do not write a new graph from zero. Its README is the user guide; this page is for the agent.

Companion file: [`revit-dynamo-pitfalls.md`](revit-dynamo-pitfalls.md), the short list of traps. Read it before you change code and when a run fails.

API detail: https://infrared.city/docs/sdk/ (agents: https://infrared.city/docs/sdk/llms.txt).

## 1. What the user gets

- One graph, `IR_Analysis.dyn`. The user selects buildings in Revit, sets the inputs and presses Run.
- Targets: `ground` (a grid around the buildings), `facades` (walls and roofs) or `both` (two runs, two costs).
- Analyses: `svf`, `solar`, `sun-hours`, `wind`, `utci` on the ground; `svf`, `solar`, `sun-hours`, `daylight` on the facades.
- The result is a coloured surface in the model, a legend in a drafting view, and a status text in a Watch node.

## 2. Install

Dynamo in Revit 2026 runs CPython 3.9.12. It has no pip. So the packages are built outside Revit.

1. On any machine with Python 3.9 or later and pip, run `python build_libs.py` in the app folder. It downloads the wheels of `infrared-sdk[geodata]==1.0.0` for Python 3.9 on Windows x64 and writes `build/infrared-dynamo-libs.zip` (about 50 MB).
2. Unzip it into `%APPDATA%\Infrared\revit-dynamo` (the libs folder). The folder must hold `ir_dynamo`, `ir_revit`, `dynamo` and the SDK packages.
3. Open `dynamo/IR_Analysis.dyn` in Dynamo. Check that the `libs_folder` input is the libs folder.

The zip holds Windows x64 packages only. The script refuses an SDK other than 1.0.0.

## 3. API key and location

- Key: set `set_api_key` to `True` and press Run. A password dialog opens and saves the key in `~/.infrared/api_key.txt`. Then set `set_api_key` to `False`. The `INFRARED_API_KEY` environment variable has priority. Never put the key in the `.dyn` file, in the log or in the chat.
- Location: Revit stores one latitude and longitude (Manage > Location) and a true north angle. The script uses them as the position of the **internal origin**, not of the Project Base Point or the Survey Point. If the model is far from the internal origin, the user can type `lat` and `lon`.
- The location matters for weather and for `fetch_context` (public buildings around the selection). An error of some metres changes nothing in a run without context.

## 4. Inputs

| Input | Values | Notes |
|---|---|---|
| `target` | `ground`, `facades`, `both` | `both` is two runs and two costs |
| `analysis` | a label from section 1, `show-last` or `export-obj` | `show-last` draws the saved results again, free. `export-obj` writes an OBJ file for the platform upload, free |
| `months`, `hours` | `6-8`, `8-18`, `13` | For solar, sun hours and UTCI |
| `preview_only` | `True` / `False` | `True` shows tiles, jobs and tokens, free. Always preview first |
| `fetch_context` | `True` / `False` | Public buildings around the selection |
| `lat`, `lon` | empty or degrees | Empty: the Revit project location |
| `wind_speed`, `wind_direction` | m/s, degrees (270 = from the west) | Ground wind only |
| `surfaces` | `facades`, `roofs`, `all` | Facade target only |
| `legend` | `trimmed` (default), `exact`, `platform` | The colour range, see section 6 |
| `gradient` | `True` / `False` | Wind speed and UTCI as a smooth gradient |
| `set_api_key` | `True` / `False` | Opens the key dialog and stops |
| `terrain` | a second element selection | The ground, of any type (Toposolid, floor, mass, import). The ground result is drawn on it |

Selection: walls, floors, roofs, masses, families, DirectShapes and imported meshes work. Put the ground in the `terrain` selection: any element type works there. With an empty `terrain` selection, the Toposolids and Topography surfaces of the main selection are the terrain, else every terrain of the document. Without terrain the ground is a flat plane at Revit elevation 0. A linked Revit model is not read. Wind does not accept terrain: the buildings are lowered to their base, and the result is drawn on the terrain.

## 5. What a run does

1. Reads the location, the selected elements (Solid and Mesh geometry, in feet) and the terrain.
2. Converts to the SDK frame: metres, x east, y north, origin at the south-west corner of the polygon bounding box, turned by true north.
3. `preview_area` (free) or `run_area_and_wait` (paid). Revit does not respond during the run: 30 seconds to 5 minutes.
4. Places the ground grid by the SDK rule (row 0 is the south edge, `bounds` gives the place, the cell centre is at `(col + 0.5, row + 0.5)` cells from the south-west corner). A "Grid alignment check" line in the Watch text compares this rule with a one-cell shift.
5. Colours each cell with the SDK renderer (`render_grid_image_local` and the platform colour registry): one pixel per cell.
6. Draws the result and the legend, saves the result for `show-last`, and writes the status text to the Watch node and to the log.

## 6. Results in Revit

- **Shape.** One DirectShape per target (Generic Models, name "Infrared result (ground)" or "(facades)"). Look at it in a Shaded or Realistic 3D view. A new run of the same target replaces only that shape.
- **Materials.** One material per colour, for example `Infrared svf 08AEC4`. A smooth scale has up to 256 colours, so up to 256 materials.
- **Legend.** A drafting view per target: "Infrared legend - ground" or "Infrared legend - facades" (Project Browser > Drafting Views). A new run redraws the same view, so it can stay on a sheet. The Revit API cannot create a Legend view.
- **Colour range** (`legend` input):
  - `trimmed`: the 2nd to 98th percentile of the values. Use it to see the variation (for example the wind wake behind a building).
  - `exact`: the minimum and maximum of the result.
  - `platform`: the fixed range of the platform where it has one (wind speed 0 to 20 m/s, UTCI -40 to 46 °C), else the 2nd to 98th percentile. A 5 m/s wind shows in blue only.
- **Another range, free.** Change `legend` or `gradient`, set `analysis` to `show-last` and press Run. The saved results are in `~/.infrared/revit-dynamo-last-result.json`, one entry per target and per Revit document.
- **Delete a result.** Select the shape in a 3D view and delete it. Delete the legend drafting view in the Project Browser. Manage > Purge Unused removes the `Infrared ...` materials.

## 6a. Export to the platform

The platform upload reads GeoJSON, OBJ and EPW, not RVT or IFC ([`platform-byo-upload.md`](../platform-byo-upload.md)). `analysis = export-obj` writes `Documents\Infrared\<model>-<date>-<time>.obj`. It makes no API call and needs no key.

- Metres, Z up, +Y north (the platform takes Z as up). One object per element: `building_<ElementId>`, `ground_<ElementId>`. No `usemtl` lines: a Revit material name like "Concrete" is a ground word for the platform classifier.
- The parts below the ground are left out: the platform puts the lowest point on its ground, so a basement would lift the building.
- The terrain within 50 m of the buildings is in the file.
- Only the building categories go in (`obj_export.is_building`: walls, curtain panels and mullions, columns, beams, floors, roofs, windows, masses); `export-obj all` keeps every category. The rule matches the BuiltInCategory name first, the English display name second. A whole architectural model with every category gave 2 million triangles and 71 MB; the Watch text gives the triangles of each category.
- The OBJ has no georeference. The Watch text gives the longitude and latitude of the middle of the buildings; the user drags the model there before Save.
- The platform limit is 40 MB. The Watch text gives the size.
- The platform guesses the vertical sign from point density (the denser end is the ground). A Revit building without terrain has a dense roof, so it can arrive upside down: tell the user to clear "Flip vertical" in Review model.
- Not yet checked on the platform: that a sloped `ground_*` object keeps its heights.

## 7. Change the script for the user

The code has three layers. Keep logic out of the `.dyn` file.

| Layer | Holds | Tested |
|---|---|---|
| `dynamo/IR_Analysis.dyn` | Inputs and one Python node of a few lines (the stub). The stub puts the libs folder on `sys.path`, removes the loaded `ir_*` modules, calls `ir_revit.entry.run` and writes a traceback to the log | No |
| `ir_revit/` | Revit API code: location, geometry, display, legend view, key dialog, `entry.py` | Only in Revit |
| `ir_dynamo/` | SDK calls, payloads, frame, targets, colours, legend layout, summary. No Revit import | `pytest` in a normal Python |

Rules:

- Write Python 3.9 syntax in all three layers (no `match`, no `X | Y` types at run time).
- Put new logic in `ir_dynamo/` with a test. Keep `ir_revit/` to Revit API calls.
- A new analysis is a row in `ir_dynamo/settings.py` (`ANALYSES`: label, SDK type, unit, targets, period, weather, wind) and, if it needs a new request type, a branch in `ir_dynamo/payloads.py`.
- A new input is a new Dynamo input node, a new `IN[n]` in the stub, and a new parameter of `entry.run`. Change the `.dyn` in Dynamo, not by hand-editing its JSON. Give the user the exact stub text to paste when the stub changes.
- Do not copy colour, legend or grid rules from other hosts. Use the SDK renderer and the SDK result fields.

## 8. Work from an agent

The agent cannot press Run in Revit. The loop is:

1. Change the files in the repo. Run `pytest tests` in the app folder and check the exit code, not only the last lines of the output.
2. Copy the changed files into the libs folder (`%APPDATA%\Infrared\revit-dynamo`). Revit runs that copy, not the repo.
3. Ask the user to press Run (preview first).
4. Read the end of `~/.infrared/revit-dynamo-runs.log`. Each run appends its status lines, or the traceback. Live progress lines show the seconds since the run started.
5. If the log has no new lines, the run did not reach the script: see the pitfalls page.

Ask the user for a paid run before you set `preview_only` to `False`. Keep paid test runs small: one building, one target.
