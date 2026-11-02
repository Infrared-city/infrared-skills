"""A small password dialog that saves the Infrared API key to the key file.

``ir_dynamo.env.read_api_key`` reads that file. The key text is never logged,
printed or returned from this file. It is only written to the key file.
The key file is in your user profile folder: keep that folder private.
"""

from __future__ import annotations

import os


def ask_and_save() -> bool:
    """Show the dialog. Save the key if the user presses Save.

    Returns
    -------
    bool
        True if a key was saved, False if the user cancelled or left it empty.
    """
    import clr  # type: ignore

    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System.Drawing import Point, Size  # type: ignore
    from System.Windows.Forms import (  # type: ignore
        Button,
        DialogResult,
        Form,
        FormBorderStyle,
        FormStartPosition,
        Label,
        TextBox,
    )

    from ir_dynamo.env import KEY_FILE

    form = Form()
    form.Text = "Infrared API key"
    form.FormBorderStyle = FormBorderStyle.FixedDialog
    form.StartPosition = FormStartPosition.CenterScreen
    form.ClientSize = Size(380, 110)
    form.MinimizeBox = False
    form.MaximizeBox = False
    form.TopMost = True  # keep it above the Revit window

    label = Label()
    label.Text = "Paste your Infrared API key:"
    label.Location = Point(12, 12)
    label.Size = Size(356, 18)
    box = TextBox()
    box.UseSystemPasswordChar = True  # shows dots, not the key
    box.Location = Point(12, 36)
    box.Size = Size(356, 22)
    ok = Button()
    ok.Text = "Save"
    ok.Location = Point(212, 72)
    ok.DialogResult = DialogResult.OK
    cancel = Button()
    cancel.Text = "Cancel"
    cancel.Location = Point(293, 72)
    cancel.DialogResult = DialogResult.Cancel
    for control in (label, box, ok, cancel):
        form.Controls.Add(control)
    form.AcceptButton = ok
    form.CancelButton = cancel

    saved = False
    if form.ShowDialog() == DialogResult.OK:
        key = (box.Text or "").strip()
        if key:
            folder = os.path.dirname(KEY_FILE)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with open(KEY_FILE, "w") as handle:
                handle.write(key)
            saved = True
    box.Text = ""
    form.Dispose()
    return saved
