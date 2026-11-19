"""Free previews of the commands in Dynamo's own Python, without Revit.

pytest runs in a clean venv, but Dynamo's Python has its own packages, for example a
pandas built for numpy 1. Such a clash shows only here. Real example: the libs folder
brings numpy 2, and ``context`` failed on Dynamo's pandas. It failed only where the
public buildings come from Overture (Graz), not in a city with its own source (Vienna).
pytest found nothing, because it ran in its own venv with Vienna coordinates.

Every command runs as a preview: the API key is needed, tokens are not. A command
with the word ``run`` is refused. Run it before a libs zip goes out::

    "%LOCALAPPDATA%\\python-3.9.12-embed-amd64\\python.exe" tests\\smoke_dynamo.py

Options::

    --libs DIR      the libs folder (default: INFRARED_DYNAMO_LIBS, else
                    %APPDATA%\\Infrared\\revit-dynamo); for example an unzipped zip
    --installed     test the ir_dynamo of the libs folder, not the one of this repo
    "svf both" ...  other commands than the default list

Exit code 0: every preview gave a cost. 1: one or more failed.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
DYNAMO_PYTHON = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "python-3.9.12-embed-amd64", "python.exe"
)

# A place with its own city source, and one where the public buildings come from Overture.
PLACES: List[Tuple[str, float, float]] = [
    ("Vienna (city source)", 16.3701, 48.1983),
    ("Graz (Overture)", 15.4395, 47.0707),
]
COMMANDS = [
    "svf both",
    "solar both months 6-8 hours 8-18 context",
    "sun-hours both",
    "daylight both",
    "wind 5 270 ground context",
    "pwc",
    "tcs",
    "utci",
]


def _libs_dir(args: List[str]) -> str:
    if "--libs" in args:
        return os.path.abspath(args[args.index("--libs") + 1])
    default = os.path.join(os.environ.get("APPDATA", ""), "Infrared", "revit-dynamo")
    return os.environ.get("INFRARED_DYNAMO_LIBS") or default


def _commands(args: List[str]) -> List[str]:
    skip = {"--installed"}
    if "--libs" in args:
        skip |= {"--libs", args[args.index("--libs") + 1]}
    own = [a for a in args if a not in skip]
    return own or COMMANDS


def _scene() -> Tuple[dict, dict]:
    """One building of the selection; a shade building and a ground sheet around it."""
    from boxes import box_soup

    own = {"b1": box_soup(-10, -10, 0, 20, 20, 15)}
    shade = {
        "s1": box_soup(40, 0, 0, 10, 10, 30),
        "sheet": box_soup(-100, -100, 0, 200, 200, 0.3),  # flat: left out
    }
    return own, shade


def main(args: List[str]) -> int:
    libs = _libs_dir(args)
    if not os.path.isdir(os.path.join(libs, "infrared_sdk")):
        print("No infrared_sdk in %s. Unzip the libs zip there, or give --libs DIR." % libs)
        return 1
    # The libs folder before Dynamo's Lib, as in Revit. This repo's ir_dynamo before
    # the libs folder, unless --installed: the code under test.
    sys.path.insert(0, libs)
    if "--installed" not in args:
        sys.path.insert(0, APP)
    sys.path.insert(0, HERE)
    import ir_dynamo
    from ir_dynamo import command, env, targets
    from ir_dynamo.run import run_analysis

    version = env.setup()  # the libs folder is on sys.path already: it stays second
    hidden = any(getattr(f, "_infrared_hides", None) == "pandas" for f in sys.meta_path)
    print("Python:     %s (%s)" % (sys.version.split()[0], sys.executable))
    if os.path.normcase(sys.executable) != os.path.normcase(DYNAMO_PYTHON):
        print("Warning:    this is not Dynamo's Python; it proves less. Use %s" % DYNAMO_PYTHON)
    print("Libs:       %s" % libs)
    print("ir_dynamo:  %s" % os.path.dirname(ir_dynamo.__file__))
    print("SDK:        %s; a broken pandas is hidden: %s" % (version, hidden))

    from infrared_sdk import InfraredClient

    client = InfraredClient(api_key=env.read_api_key())
    own, shade = _scene()
    failed = 0
    try:
        for place, lon, lat in PLACES:
            print("\n== %s" % place)
            for line in _commands(args):
                cmd = command.parse(line)
                if cmd.action != "analysis" or cmd.paid:
                    print("REFUSED  %s: only analysis previews, without the word run." % line)
                    failed += 1
                    continue
                surfaces, _skipped = targets.plan_runs(cmd.target, cmd.analysis)
                for surface in surfaces:
                    started = time.time()
                    name = "%s [%s]" % (cmd.text, surface)
                    try:
                        out = run_analysis(
                            surface, cmd.analysis, own, lon, lat,
                            preview_only=True, months=cmd.months, hours=cmd.hours,
                            fetch_context=cmd.fetch_context, shade_m=shade,
                            wind_speed=float(cmd.wind_speed),
                            wind_direction=int(round(float(cmd.wind_direction))),
                            surfaces=cmd.surfaces, client=client,
                        )  # fmt: skip
                    except Exception as error:  # noqa: BLE001 - every failure is a line
                        failed += 1
                        print("FAIL     %s: %s: %s" % (name, type(error).__name__, error))
                        traceback.print_exc(limit=-3)
                        continue
                    context = [w for w in out["warnings"] if "public building(s) added" in w]
                    print("ok %4.0fs %s: %s%s" % (
                        time.time() - started, name, out["cost"],
                        "; " + context[0].split(" public")[0] + " context building(s)" if context else "",
                    ))  # fmt: skip
    finally:
        client.close()
    print("\n%s" % ("All previews ran." if not failed else "%d failed." % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
