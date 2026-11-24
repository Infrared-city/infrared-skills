"""Infrared in Rhino: the same command line as the Revit app, on Rhino objects.

``ir_rhino.entry.run("svf run")`` analyses the selected objects and adds the
result to the document. The Rhino 9 AI panel calls it through ``run_python``;
the ScriptEditor and (later) a Grasshopper component call the same function.

The host-free work (the command, the payload, terrain, colours) is done by
``ir_dynamo`` of the Revit app: this package only reads Rhino and draws in it.

    ir_rhino.entry       run(command, objects): the one function to call
    ir_rhino.site        lon/lat, true north and units: model <-> site metres (pure)
    ir_rhino.core        preview or run on plain data, the lines of the log (pure)
    ir_rhino.shapes      a result as coloured triangles (pure)
    ir_rhino.rhino_doc   Rhino objects in, a coloured mesh out (Rhino only)

Python 3.9 syntax: it runs in Rhino 9 (CPython 3.13) and Rhino 8 (CPython 3.9).
"""

from __future__ import annotations
