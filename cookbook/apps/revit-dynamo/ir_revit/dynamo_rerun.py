"""Let the next Run start again when the command did not change.

Dynamo in Manual run mode runs a node only when one of its inputs changed. So
after ``select`` and a cancel, a second Run with the same command did nothing:
the log had no "run started" line (live run 2026-11-12). This module marks the
Python node as modified during its own run, so the next Run executes it again.

A marked node has a price: when the command text changed, the next Run executes
the node two times, first with the earlier text and then with the new text (live
run 2026-11-12: ``select``, then ``svf both run`` typed, gave ``select`` again and
then ``svf both run``). So ``live_command`` reads the text of the command node from
the graph, and ``ir_revit.entry.run`` skips an execution whose text is not that
text. ``entry`` marks the node only when ``live_command`` gave a text.

Only in Manual mode: in Automatic mode a node that marks itself would run in a
loop. A failure here stops nothing; ``mark`` returns a short text for the log.

Dynamo API used: ``Dynamo.Applications.DynamoRevit.RevitDynamoModel``,
``CurrentWorkspace`` (``Nodes``, ``RunSettings.RunType``),
``NodeModel.MarkNodeAsModified``, ``NodeModel.Name``, ``StringInput.Value``.
"""

from __future__ import annotations

from typing import Any, Optional


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


def live_command() -> Optional[str]:
    """The text in the command node of the open graph now. None when it cannot be read.

    The command node is the String node with the name ``command``, or the only
    String node of the graph.
    """
    try:
        strings = [n for n in list(_model().CurrentWorkspace.Nodes) if n.GetType().Name == "StringInput"]
        named = [n for n in strings if str(n.Name).strip().lower() == "command"]
        nodes = named or strings
        if len(nodes) != 1:
            return None
        value = nodes[0].Value
        return None if value is None else str(value)
    except Exception:
        return None


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
