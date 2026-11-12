# Pitfalls: Revit 2026 Dynamo + Infrared SDK

Read this when something is wrong, or before you change the script. The recipe is in [`revit-dynamo.md`](revit-dynamo.md).

Most expensive failures return a plausible result. Look at the picture and the value lines before you trust a number.

## Install and load

1. **Dynamo's Python has no pip.** Revit 2026 embeds CPython 3.9.12. Build the wheels outside Revit with `build_libs.py` (`pip --target --python-version 3.9 --platform win_amd64 --only-binary=:all:`). Do not try to install into Revit.
2. **The libs zip is Windows x64 only.** Wheels for macOS or Linux do not load.
3. **An edited module does not load again.** Dynamo keeps imported modules for the whole Revit session, and `importlib.reload` can leave an old submodule in place. The symptom is an `AttributeError` for a name that is in the file. The stub removes every `ir_dynamo` and `ir_revit` module from `sys.modules` before the import. A `.dyn` saved before that stub still has the old stub: restart Revit and open the new `.dyn`.
4. **Revit runs the libs folder, not the repo.** Copy each changed file into `%APPDATA%\Infrared\revit-dynamo`.
5. **Manual run mode caches.** Dynamo runs a node only when an input changed, so the same command did not run twice. The script now marks its Python node as modified on each run (`ir_revit/dynamo_rerun.py`); the log has a `rerun:` line that says if it worked. If it says `not set`, the user changes the command to run again.
6. **"Run started" and nothing more.** The run did not reach the script, or Revit waits on a dialog behind its window. Look for a dialog first. If there is none, restart Revit.
7. **The run blocks Revit** for 30 seconds to 5 minutes. Tell the user before a paid run. Do not close Revit while it runs.

## Revit API from CPython 3

8. **`ElementType.Name` raises "property cannot be read".** The type declares only a setter. The getter of the base class, `Element.Name.__get__(element)`, can give `None` without an error. Try the property, the base getter and the name parameters in turn, and treat `None` as a failure. A name that reads as `None` makes a find-by-name miss and the next create fail.
9. **.NET types need explicit generics.** Use `List[GeometryObject]()` from `System.Collections.Generic` and `clr.GetClrType(cls)` for `OfClass`.
10. **Copy a collector to a list before you delete.** Deleting while a `FilteredElementCollector` runs breaks the iterator.
11. **Use Dynamo's transaction.** `TransactionManager.Instance.EnsureInTransaction(doc)`, then `TransactionTaskDone()`. On an error call `ForceCloseTransaction()`.
12. **A failed legend must not lose a paid result.** Draw the shape first, then the legend in its own `try`.

## Geometry in

13. **A box can be a Mesh, not a Solid.** The default template's masses, DirectShapes and imports give `Mesh` objects. Read both.
14. **A selection of levels and scope boxes has no 3D geometry.** The Watch text names the category and class of each skipped element. Ask the user to select model elements.
15. **Skip your own result shapes.** A selection that holds an old result would send it as a building. The script skips DirectShapes with its `ApplicationId`.
16. **Revit internal units are feet.** Convert to metres and turn by the true north angle before you build the payload. Turn the result back the same way.
17. **The project location is the internal origin.** Not the Project Base Point, not the Survey Point.
18. **The ground is a flat plane at elevation 0.** The script found no terrain ("Terrain: 0 element(s)"). Architects often model the site as a floor, a mass, an import or a linked model. Only Toposolids and Topography surfaces are terrain: ask the user to model the site as a Toposolid, and not to select a floor used as ground (it is analysed as a building). Read the "Selection" line for the categories. The Toposolids of a loaded linked model are read; a link that is not loaded is not.
19. **Wind and PWC refuse terrain.** Lower the buildings to their base and draw the result on the terrain.

## What gets a result

35. **The results look like another city's.** The project location is the Revit default (the Boston area). The sun, the weather and the public buildings come from it. The Watch text starts with a warning; the user sets Manage > Location or adds `lat` and `lon`.
36. **Only one building can be selected, but others stand around it.** They are in a linked model (the Snowdon Towers sample: the site and the facades are links). The script reads the loaded links: their building elements shade the result. For a result on them, pick an element inside the link with Tab, select the whole link, or use `model`.
37. **A building that was not selected has a result.** With `context` the result covers the public buildings inside the run area: this is intended, and the Watch text says so. Without `context`, only the selection (or the whole model with `model`) gets a result; the other elements shade.
38. **A tile starts at the south-west corner of the run polygon.** A small polygon sits in that corner of its 512 m tile, and the SDK reads the public buildings around the tile centre, so they lie mostly north and east of the selection. With `context` the script grows the margin until the polygon fills the tile (`frame.fill_buffer`): same cost, the selection in the middle, the ground result over the whole area. Do not shrink that margin to "save" cost: it costs nothing.
39. **The grid alignment check read 100 % for every shift.** It counted buildings outside the run area, where the server gives no value. It now counts only the buildings inside the area.
40. **A run on a large model is slow before it reaches the server.** The script reads the geometry of every building element near the selection to let it shade. `alone` skips that.

## Results and colours

20. **Everything is one colour.** The colour range is much wider than the values. Wind speed and UTCI have a fixed platform range (0 to 20 m/s, -40 to 46 °C), and `platform` is the default. Use the word `trimmed`. Compare the value lines (min, max, percentiles) with the "Legend range used" line.
21. **The SDK renderer chooses its own range.** A colour scale without `steps` is drawn over the 2nd to 98th percentile of the cells, and SDK 1.0.0 ignores `infraredRange`. To pin a range, the script adds pad cells with the low and high value to the rendered grid and does not read them back.
22. **Do not shift the ground grid.** Row 0 is the south edge, `bounds` gives the place, the cell centre is at `(col + 0.5, row + 0.5)` cells. The "Grid alignment check" line shows the share of cells under buildings with no value. Change the placement only if a shift wins clearly, and report it to Infrared.
23. **UTCI shows one colour on the platform scale.** This is correct: a summer afternoon fits in one or two platform bins. Use `trimmed gradient` to see the variation.

## Drawing in Revit

24. **One `TessellatedShapeBuilder` gives one mesh with one material**, also with several face sets. Use one builder per colour and put all meshes into one DirectShape. Check the "Revit built N mesh(es) with N material(s)" line.
25. **Tag what you draw and delete only your own.** DirectShape `ApplicationId` = the app name, `ApplicationDataId` = the target.
26. **The API cannot create a Legend view.** Draw the legend in a drafting view (`ViewDrafting.Create`, solid `FilledRegion` per colour, `TextNote` per line). Find the view by name and clear it on the next run, so a viewport on a sheet stays.
27. **Colours do not show in Hidden Line or Wireframe.** Use a Shaded or Realistic 3D view.
28. **Materials stay after you delete a shape.** Purge Unused removes them.

## Export to the platform

29. **The platform does not read RVT or IFC.** Use the command `export-obj` (OBJ, metres, named objects). Do not export FBX or IFC and convert by hand: the unit and the names get lost.
30. **A basement lifts the building on the platform.** The platform puts the lowest point on its ground. The export leaves out the parts below the terrain; without terrain, below Revit elevation 0.
31. **A whole architectural model is above 40 MB.** The platform refuses the file ("file exceeds the Wavefront OBJ size limit"). The export keeps only the building categories; read the "Triangles by category" line and select the outer shell.
32. **The model is upside down on the platform.** The platform takes the denser end of the model as the ground. A detailed roof over a base cut at the ground is denser at the top. Clear "Flip vertical" in Review model. Write Z up: a Y-up file of a tall building lies on its side.
33. **The OBJ sits on the site centre.** It has no georeference. Give the user the longitude and latitude from the Watch text, and tell them to drag the model there before Save.
34. **Outlines on the ground in front of the building, but nothing there in Revit.** The platform made them. It splits each OBJ object into connected parts and gives a raised building-like part with nothing under it a floor at z = 0 (for buildings on a slope). A bay window that starts on an upper floor, in its own object, is such a part. Write all building elements into one object: the bay then joins the walls below it. Removing low elements does not help.

## Habits that find bugs early

- **Preview first.** A command without the word `run` shows tiles, jobs and tokens, free.
- **Read the log after every Run:** `~/.infrared/revit-dynamo-runs.log`. The stub writes each traceback there too.
- **Log the numbers that hid the last bug:** element count and categories, triangle count, value min, max and percentiles, legend range, distinct colours, meshes and materials built.
- **Test `ir_dynamo` offline** with pytest. Check the exit code: a pipe to `tail` hides a failure.
- **Use `show-last` to test colours.** It redraws the saved result, free.
