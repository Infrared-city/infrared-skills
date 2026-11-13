"""Revit-side code for the Dynamo scripts.

Import these modules only inside Dynamo in Revit: they load the Revit API.
They must run on Python 3.9 (the engine of Dynamo in Revit 2026).

    ir_revit.entry            the one function a Dynamo node calls
    ir_revit.revit_location   site lon/lat and true north from the project
    ir_revit.revit_geometry   selected elements to triangles in the Revit frame
    ir_revit.revit_display    show the result in the active view (AVF)
    ir_revit.revit_results    the result shapes of the model, and the command clear
    ir_revit.revit_filters   one view filter per result, to hide and show it
    ir_revit.revit_apikey    password dialog that saves the API key
"""

from __future__ import annotations
