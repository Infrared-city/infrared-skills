"""PWC criteria and TCS subtypes in the colour registry, and class scales. No Revit import.

The platform colour registry keeps one scale per criterion (``pedestrian-wind-comfort``)
or per subtype (``thermal-comfort-statistics``), nested under the analysis. This app
names such a scale with a colour key, ``"<SDK analysis type>/<variant>"``, for example
``"pedestrian-wind-comfort/lawson-lddc"``. ``flatten`` puts the scale under that key in
a copy of the registry, so the SDK renderer and every function of ``colors`` and
``cell_colors`` work on it as on any other analysis.

A scale whose ``steps`` are text (the PWC class letters) is a class scale: the result
holds a class code per cell (0, 1, 2, ...), and the renderer gives code ``k`` the
colour of class ``k``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

SEP = "/"


def colour_key(sdk_type: str, variant: str = "") -> str:
    """``"pedestrian-wind-comfort/lawson-lddc"``; the SDK type alone without a variant."""
    return "%s%s%s" % (sdk_type, SEP, variant) if variant else sdk_type


def split_key(key: str) -> Tuple[str, str]:
    """``(sdk_type, variant)`` of a colour key; ``variant`` is empty for a plain type."""
    base, _, variant = str(key).partition(SEP)
    return base, variant


def flatten(configs: Dict[str, Any], key: str) -> Dict[str, Any]:
    """A copy of the registry with the variant scale of ``key`` under ``key``.

    The registry is returned as it is for a plain analysis type, or when it does not
    know the variant (the caller then finds no entry and uses its fallback).
    """
    base, variant = split_key(key)
    if not variant or key in configs:
        return configs
    nested = configs.get(base)
    if not isinstance(nested, dict) or not isinstance(nested.get(variant), dict):
        return configs
    return dict(configs, **{key: nested[variant]})


def is_class_scale(configs: Dict[str, Any], key: str) -> bool:
    """True when the scale of ``key`` has text ``steps`` (class letters)."""
    config = configs.get(key)
    steps = config.get("steps") if isinstance(config, dict) else None
    return bool(steps) and all(isinstance(s, str) for s in steps)


def class_colours(key: str, configs: Dict[str, Any]) -> Tuple[List[Tuple[int, int, int]], List[str]]:
    """``(colours, labels)`` of a class scale: one per class code, from the SDK renderer.

    The label is the letter and the registry name, for example ``"A Frequent Sitting"``.
    """
    from infrared_sdk.layers.image_local import render_grid_image_local

    from .png import decode_png

    config = configs[key]
    steps = [str(s) for s in config["steps"]]
    names = [str(n) for n in (config.get("stepsNames") or [])]
    png = render_grid_image_local(
        grid=[[float(k) for k in range(len(steps))]],
        analysis_type=key,
        visual_configurations=configs,
        max_long_axis_px=0,
    )
    rgb = decode_png(png)[0, :, :3].astype(int)
    colours = [tuple(int(c) for c in rgb[k]) for k in range(len(steps))]
    labels = [s if k >= len(names) else "%s %s" % (s, names[k]) for k, s in enumerate(steps)]
    return colours, labels


def label_check(result_labels: Sequence[Any], legend_labels: Sequence[str]) -> List[str]:
    """A line when the class letters of the result differ from the registry's.

    The result gives its classes in code order (``AreaResult.legend``). The colours
    follow the registry order, so both must agree.
    """
    got = [str(x) for x in result_labels or []]
    letters = [label.split(" ")[0] for label in legend_labels]
    if not got or got == letters[: len(got)]:
        return []
    return [
        "Class check: the result has the classes %s, the colour registry %s. "
        "The colours can be wrong; report this to Infrared." % (", ".join(got), ", ".join(letters))
    ]
