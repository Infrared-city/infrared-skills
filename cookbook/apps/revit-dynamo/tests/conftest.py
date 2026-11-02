"""Put the app folder and the tests folder on sys.path."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (os.path.dirname(HERE), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("INFRARED_QUIET", "1")
