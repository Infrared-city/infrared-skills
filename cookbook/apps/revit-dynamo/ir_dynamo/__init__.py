"""Infrared SDK helpers for Dynamo scripts in Revit.

No Revit import here: the code takes plain data (metres, lists, dicts) and
returns plain data, so it runs under pytest. It must also run on Python 3.9,
the engine of Dynamo in Revit 2026.

Main entry points:
    ir_dynamo.run.run_analysis    preview or run one analysis
    ir_dynamo.env.setup           put the libs folder on sys.path, load the SDK
    ir_dynamo.settings.ANALYSES   the analyses a script can offer
"""

from __future__ import annotations

__all__ = ["env", "frame", "meshes", "payloads", "results", "run", "settings"]
