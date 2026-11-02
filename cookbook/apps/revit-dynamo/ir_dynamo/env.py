"""Set up the SDK in Dynamo: libs folder, SDK import, API key."""

from __future__ import annotations

import os
import sys
from typing import Optional

PINNED_SDK = "1.0.0"
KEY_ENV = "INFRARED_API_KEY"
# The key file is written by the Revit-side password dialog.
KEY_FILE = os.path.join(os.path.expanduser("~"), ".infrared", "api_key.txt")


class _FlushableStream:
    """Wraps a stream that has write() but no flush() (Dynamo's stdout)."""

    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        self._stream.write(text)
        return len(text)

    def flush(self) -> None:
        pass

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def setup(libs_dir: Optional[str] = None) -> str:
    """Put the libs folder first on ``sys.path`` and import the SDK.

    Parameters
    ----------
    libs_dir : str, optional
        Folder with the unzipped SDK and ``ir_dynamo``. Leave it out if the
        folder is already on ``sys.path``.

    Returns
    -------
    str
        The SDK version that was loaded.

    Raises
    ------
    RuntimeError
        When the SDK is missing or is not the pinned version.
    """
    # Dynamo has no console, and its stdout object has no flush(): the SDK's
    # progress lines (print(..., flush=True)) raise AttributeError there.
    # Status reaches the user through on_status and the Watch node instead.
    os.environ["INFRARED_QUIET"] = "1"
    if not hasattr(sys.stdout, "flush"):
        sys.stdout = _FlushableStream(sys.stdout)
    if libs_dir:
        if libs_dir in sys.path:
            sys.path.remove(libs_dir)
        sys.path.insert(0, libs_dir)
    try:
        import infrared_sdk
    except ImportError as exc:
        raise RuntimeError(
            "infrared_sdk is not found. Unzip the libs folder and give its path (%s)."
            % exc
        )
    version = str(getattr(infrared_sdk, "__version__", "?"))
    if version != PINNED_SDK:
        raise RuntimeError(
            "infrared-sdk %s is loaded from %s. This script needs %s."
            % (version, getattr(infrared_sdk, "__file__", "?"), PINNED_SDK)
        )
    return version


def read_api_key() -> str:
    """The API key: the ``INFRARED_API_KEY`` variable first, then the key file.

    Raises
    ------
    RuntimeError
        When there is no key. The text never contains the key.
    """
    key = (os.environ.get(KEY_ENV) or "").strip()
    if not key and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, "r") as handle:
            key = handle.read().strip()
    if not key:
        raise RuntimeError(
            "No API key. Set %s or save it with the key dialog." % KEY_ENV
        )
    return key
