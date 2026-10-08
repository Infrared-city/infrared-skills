# Pitfalls: Rhino/Grasshopper + Infrared SDK

Read this when something is wrong, or before you trust a number. The recipes are in [`grasshopper.md`](grasshopper.md) and [`grasshopper-geometry-and-drawing.md`](grasshopper-geometry-and-drawing.md).

Most expensive failures return HTTP 200 and a plausible result. Look at the picture before you trust a number.

## Install and load

1. **First import wins.** One old SDK in one component of the file breaks all new components. Use the bootstrap in `grasshopper.md`. Check what is loaded with a probe component.
2. **Install with Rhino's pip.** System Python gives wheels that Rhino cannot load. `uv` can pick x86_64 wheels on an ARM Mac.
3. **A changed `# r:` line may not resolve again.** Pin the version. For many components, use one shared folder.
4. **Version your saved state.** Version your `sticky` keys and put `infrared_sdk.__version__` into every fingerprint.

## Threads and the canvas

5. **A saved toggle that is ON must not run on open.** Run on the rising edge only.
6. **Never block the UI thread** and never touch the Rhino document from a worker thread.
7. **One heavy draw at a time** across all Infrared components. Two draws at the same time can crash Rhino on macOS.
8. **A progress tick must not re-solve the canvas.** Update the label and repaint. Solve once at the end.
9. **`Layers.Modify` in code can crash Rhino on macOS.** Do not change layers in a loop. Tell the user that a layer is hidden.
10. **`RhinoDoc.ActiveDoc` can be `None`** for a new, unsaved file. Use `RhinoDoc.OpenDocuments()[0]`.
11. **Do not patch SDK functions inside Rhino.** Other components share the process.
12. **Outputs in SDK mode must be `ScriptVariableParam`.** A standard `Param_Mesh` throws "Unable to cast". Change inputs and outputs only in `BeforeRunScript` or outside a solve. Build the new parameters first, then remove the old ones, or Grasshopper deletes wires.
13. **A `DisplayConduit` subclass must call `super().__init__()`.** An orphaned conduit keeps drawing old results and holds its meshes. Empty it when you replace it.
14. **A Boolean Toggle is a level, not an event.** Latch the edge in `sticky`.

## Results

15. **Never read the raw grid.** Use `physical_grid()`, `has_value(i)` and `render_buffers()`. The raw array keeps the wire dtype and is read-only.
16. **Do maths in float32.** Do not widen to float64 for display.
17. **Read `render_buffers()` before `client.close()`.**
18. **A failed tile raises `AreaRunError`.** There is no partial map. Show the error and keep the other paid results.
19. **`min_legend` and `max_legend` are `None` for PWC class codes.** Check for `None` before you use them.
20. **A legend over all cells makes walls dark** (roofs are brighter). Use a percentile of the wall cells. Use one legend for all variants.
21. **One colour ramp over two groups of very different values** makes everything one colour. Print the data range and the ramp range before you trust a map.
22. **Daylight factor reads near zero on every floor.** First check `analysis_height` against your sill height. The wall does not need a hole: a window in the plane of a solid wall lets light through. Check that `openings` is not empty.
23. **Daylight factor reads very high** (tens of percent). The room is not closed. Seal walls from floor to slab, so that no open strip is left.

## Geometry

24. **A mesh with inward winding gives a paid, wrong result.** Clean each building on its own with `clean_mesh`. Do not weld touching buildings together.
25. **Clean once.** After `clean_mesh`, set `mesh_cleaning="off"` on the payload.
26. **Open shells stay open.** Do not "fix" them by welding and baking them back into the model.
27. **Check the units and the axes.** The SDK reads numbers as metres, z up. A Y-up or centimetre model gives a billed, wrong result. The origin is the south-west corner of the polygon bounding box, not the centre.
28. **Wind and PWC on terrain:** set `terrain_alignment="to-ground"`. These models refuse `ground_geometry`.
29. **A single building above about 250,000 sensors** cannot be split. The server can refuse the job. Use a coarser `surface_grid_size` for it.
30. **Send only context that can change the result.** A large `context_geometry` raises payload size. Do not cut context vertically: upper floors of a neighbour shade a low floor.
31. **Mesh a flat shape by hand.** `MeshingParameters.Default` can split a flat quad into many triangles. Log triangle counts: they show a slow job that nothing else shows.
32. **`FindByLayer(str)` matches the layer name, not the path.** For nested layers pass the `Layer` object.
33. **Geometry inputs without a type hint arrive as Guids** in `ghdoc`. Look them up in `scriptcontext.doc`, then in `RhinoDoc.ActiveDoc`.

## Drawing and baking

34. **Never loop over vertices, faces or colours in Python.** Use numpy and one `memmove`.
35. **`AddVertices(Point3f[])` can bind the wrong overload.** Name it: `AddVertices.Overloads[IEnumerable[rg.Point3f]]`.
36. **Check the counts after a bulk add.** A partial mesh renders as spikes.
37. **Do not call `Mesh.Compact()`** on a mesh with vertex colours. It re-indexes vertices and the colours shift.
38. **The Grasshopper preview cannot show textures.** Use a `DisplayConduit` or bake. Rhino Shaded mode does not show textures by default: use Rendered mode.
39. **Texture pages are powers of two.** Linear filtering and mip levels are not under your control. Keep a border, group blocks by orientation, fill empty texels with the page mean colour, and keep alpha at 255.
40. **Put the atlas PNGs next to the `.gh` file.** A baked material needs them later. Delete old PNGs. A 1 m facade run writes tens of MB.
41. **Bake with tags and delete only your own tagged objects.** Never delete other objects.
42. **Keep the result before you bake.** A bake error must not lose a paid result.
43. **`AddMesh` returns `Guid.Empty`** for an invalid mesh. One degenerate face is enough. Check the result and call `IsValidWithLog()`.
44. **`Cmd+S` in Rhino saves the `.3dm`, not the `.gh`.**

## Habits that find bugs early

- **Call `preview_area` before every paid run.** Read `would_bill_jobs` and `estimated_cost_tokens`.
- **Log the numbers that hid the last bug:** triangle counts, payload size, entity counts, cache hits, elapsed seconds for each step.
- **Write job IDs to a file** when the server accepts them. After a crash you still know what was billed.
- **When an error names a quantity, measure your input against it.** A limit in an error text is a number you can check.
- **When the symptom is an absence** (empty message, zero objects, no batching), suspect a layer that swallowed a value.
- **Test offline first.** Save the render buffers once (`np.savez`). Test the packer, colours and mapping in a normal Python. Then confirm in Rhino.
- **Test the real path.** A green test suite proves your logic, not the integration. A stub of the function under test proves nothing.
- **Render the inputs and look at them before you quote a number.** A correct simulation with a wrong colour scale looks like a broken one.
