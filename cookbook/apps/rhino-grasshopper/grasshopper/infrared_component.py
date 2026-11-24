#! python3
# The code of the Infrared component (a Grasshopper "Script" component, Python 3).
# Inputs: geometry (List Access), command (Item Access).
# Optional inputs (List Access): trees, ground, material. Leave out any you do not need.
# Outputs: mesh, context, values, legend, log, vegetation, materials.
# Development version: the code runs from a clone of infrared-skills (APPS) and the SDK
# from the libs folder (see the recipe rhino.md).
import os
import sys

import scriptcontext as sc

LIBS = os.path.join(os.environ["APPDATA"], "Infrared", "rhino-grasshopper", "py313")
APPS = os.environ.get("INFRARED_APPS", r"C:\path\to\infrared-skills\cookbook\apps")
for p in (os.path.join(APPS, "revit-dynamo"), os.path.join(APPS, "rhino-grasshopper"), LIBS):
    if p not in sys.path:
        sys.path.insert(0, p)
busy = any(isinstance(v, dict) and v.get("running") for k, v in sc.sticky.items() if str(k).startswith("infrared-gh"))
if not busy:  # development: load the current code on each solve, never during a run
    for m in [m for m in sys.modules if m.split(".")[0] in ("ir_rhino", "ir_dynamo", "ir_revit")]:
        del sys.modules[m]

from ir_rhino import gh  # noqa: E402

_inputs = globals()  # an input that is not on the component is not defined
mesh, context, values, legend, log, vegetation, materials = gh.solve(
    ghenv, geometry, command,  # noqa: F821
    _inputs.get("trees"), _inputs.get("ground"), _inputs.get("material"),
)
