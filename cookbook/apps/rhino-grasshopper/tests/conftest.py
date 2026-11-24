"""Put this app, the Revit app (ir_dynamo) and its tests (boxes) on sys.path."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REVIT_APP = os.path.join(os.path.dirname(APP), "revit-dynamo")
for path in (os.path.join(REVIT_APP, "tests"), REVIT_APP, APP, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("INFRARED_QUIET", "1")
