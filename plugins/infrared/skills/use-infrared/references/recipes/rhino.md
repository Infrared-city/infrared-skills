# Recipe: Infrared in Rhino 9 (Python, AI, no Grasshopper)

Run an Infrared analysis on Rhino objects with one call: `ir_rhino.entry.run("svf")`. It reads the selected objects, previews or runs the analysis with the SDK, and adds the result to the document as a coloured mesh on the layer `Infrared`. No Grasshopper and no plugin.

Use it from the Rhino ScriptEditor (Python 3), from the Rhino 9 AI panel, or from Claude Code connected to Rhino with `MCPConnect` (the Rhino MCP tool `run_python`). Do not write your own SDK code in Rhino for these analyses: the library already handles units, the site frame, true north, ground sheets, foundations, terrain rules, the platform colours and the warnings. It is the Rhino twin of the Revit app ([`revit-dynamo.md`](revit-dynamo.md)) and takes the same command line.

Status (November 2026): first version, Rhino 9 (CPython 3.13). It runs from a clone of this repo: [`cookbook/apps/rhino-grasshopper`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/rhino-grasshopper) and the shared core `ir_dynamo` in `cookbook/apps/revit-dynamo`. A self-installing release, Rhino 8 and a Grasshopper component come later.

## 1. Install (development)

1. Rhino 9: open `ScriptEditor` once and run any Python 3 script. That installs Rhino's Python (`~/.rhinocode/py313-rh9`).
2. Install the SDK into the libs folder with Rhino's own Python:

   ```text
   "%USERPROFILE%\.rhinocode\py313-rh9\python.exe" -m pip install --target "%APPDATA%\Infrared\rhino-grasshopper\py313" "infrared-sdk[geodata]==1.0.0"
   ```

3. The API key: `~/.infrared/api_key.txt` (shared with the Revit app) or the `INFRARED_API_KEY` environment variable. Never put the key in code, in the log or in the chat.

## 2. The call

Run this with `run_python` (or in the ScriptEditor). Change only `REPO` (the clone of infrared-skills) and `COMMAND`:

```python
import os, sys
REPO = r"C:\path\to\infrared-skills"
COMMAND = "svf"
LIBS = os.path.join(os.environ["APPDATA"], "Infrared", "rhino-grasshopper", "py313")
APPS = os.path.join(REPO, "cookbook", "apps")
for p in (os.path.join(APPS, "revit-dynamo"), os.path.join(APPS, "rhino-grasshopper"), LIBS):
    if p not in sys.path:
        sys.path.insert(0, p)
for m in [m for m in sys.modules if m.split(".")[0] in ("ir_rhino", "ir_dynamo", "ir_revit")]:
    del sys.modules[m]  # load the current code on each call
from ir_rhino import entry
print("\n".join(entry.run(COMMAND)))
```

- It sends the **selected** objects (solids, polysurfaces, extrusions, SubDs, meshes) as SDK `buildings`. Nothing else of the model is sent; the surroundings come from `context`. Select first, with the Rhino tools of the MCP server or by asking the user.
- The word `model` sends every object of the model.
- Every call writes its lines to `~/.infrared/rhino-runs.log`, with live progress lines.

### Grasshopper component (development)

A Python 3 Script component with the code of [`grasshopper/infrared_component.py`](https://github.com/Infrared-city/infrared-skills/tree/main/cookbook/apps/rhino-grasshopper/grasshopper). Inputs: `geometry` (List, the SDK `buildings`), `command` (Item). The surroundings come from the word `context` (the public buildings), as on the platform. Optional, List Access, add only the ones you need:

- `trees`: points (6 m high, 4 m crown), circles (crown = the diameter) or solids (height and crown from the bounding box).
- `ground` + `material`: closed curves, surfaces or meshes, and `asphalt`, `concrete`, `soil`, `vegetation` or `water` (one text for all, or one per item). Holes are filled. Only `utci` and `tcs` read them; other analyses warn.

Without these inputs no trees and no ground materials are sent: the result is the same as before.

## 3. Commands

The same command line as the Revit app. Words in any order:

- Analysis: `svf`, `solar`, `sun-hours`, `daylight`, `wind 5 270` (m/s, the direction it comes from), `pwc` (+ criterion), `tcs` (+ subtype), `utci`.
- Target: `ground`, `facades` or `both`. Values: `months 6-8`, `hours 8-18`, `legend exact`, `gradient`.
- The area is always the default: the selection and 30 m (ground) or 5 m (facades); with `context`, about 500 m wide for the same cost. `margin` is not in the Rhino version: it gives a warning and the default area.
- `context`: add the public buildings around the site. `help`: every word.
- Location: the EarthAnchorPoint of the model (`EarthAnchorPoint` command). Without it, add `lat 48.2085 lon 16.3721` (the position of the model origin).
- **Without the word `run` it is a free preview.** It prints the cost and the warnings.

## 4. Rules for the agent

1. **Preview first.** Tell the user the cost (`Preview only: … about N tokens`) and the warnings. Add `run` only after the user agrees: it costs tokens.
2. **Check the area line** (`Area: 75 x 75 m`). An area of only `60 x 60 m` with the margin of 30 m means the selection is close to 0 m wide: the model is likely in millimetres and the object was drawn as if in metres. Ask the user.
3. **Read the warnings and say them.** They come first in the output: the location, flat ground sheets left out, a ground covered by buildings, far weather stations.
4. After a run, the mesh is on the layer `Infrared`, and earlier results of the same target are hidden. Explain the values from the lines `Result values on …` and the legend bins. Interpretation: [`../interpretation/`](../interpretation/).
5. Not in this version: `show-last`, `export-obj`, `clear`, `select`, `set-key`, terrain input, a legend object. Do not offer them.

## 5. Where it runs

| Way | Skills load? | Notes |
|---|---|---|
| Rhino ScriptEditor | not needed | the snippet above |
| Rhino 9 AI panel | **no**: the panel starts Claude Code with `--disable-slash-commands` | paste a short text with the snippet and these rules into the panel's Prompt setting |
| Claude Code + `MCPConnect` | **yes**: this recipe is read | run `MCPConnect` in Rhino, paste its text into Claude Code; then use `run_python` |
