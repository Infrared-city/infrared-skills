"""Let the next Run start again when the command did not change.

Dynamo in Manual run mode runs a node only when one of its inputs changed. So
after ``select`` and a cancel, a second Run with the same command did nothing:
the log had no "run started" line (live run 2026-11-12). This module marks the
Python node as modified during its own run, so the next Run executes it again.

Only in Manual mode: in Automatic mode a node that marks itself would run in a
loop. A failure here stops nothing; ``mark`` returns a short text for the log.

Dynamo API used: ``Dynamo.Applications.DynamoRevit.RevitDynamoModel``,
``CurrentWorkspace`` (``Nodes``, ``RunSettings.RunType``),
``NodeModel.MarkNodeAsModified``.
"""

from __future__ import annotations

from typing import Any


def _model() -> Any:
    import clr  # type: ignore

    clr.AddReference("DynamoRevitDS")
    from Dynamo.Applications import DynamoRevit  # type: ignore

    try:
        model = DynamoRevit.RevitDynamoModel
    except Exception:
        model = None
    if model is None:
        model = DynamoRevit().RevitDynamoModel
    return model


def mark() -> str:
    """Mark the Python nodes of the open graph as modified. Returns a text for the log."""
    try:
        workspace = _model().CurrentWorkspace
        # The enum prints as its number in CPython3: Manual is 0 (live run 2026-11-12).
        run_type = str(workspace.RunSettings.RunType)
        if run_type not in ("Manual", "0"):
            return "rerun: not set (run mode %s)" % run_type
        marked = 0
        for node in list(workspace.Nodes):
            if "Python" in node.GetType().Name:
                node.MarkNodeAsModified(True)
                marked += 1
        return "rerun: %d node(s) marked, the same command can run again" % marked
    except Exception as error:
        return "rerun: not set (%s: %s)" % (type(error).__name__, error)
