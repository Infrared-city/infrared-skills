"""Revit-side code for the Dynamo scripts.

Import these modules only inside Dynamo in Revit: they load the Revit API.
They must run on Python 3.9 (the engine of Dynamo in Revit 2026).

    revit.entry            the one function a Dynamo node calls
    revit.revit_location   site lon/lat and true north from the project
    revit.revit_geometry   selected elements to triangles in the Revit frame
    revit.revit_display    show the result in the active view (AVF)
    revit.revit_apikey     password dialog that saves the API key
"""

from __future__ import annotations
