"""Composite a fixed-domain colour legend onto the Blender renders (Blender has no PIL)."""

import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
L = json.load(open(os.path.join(OUT, "legend.json")))
stops = np.array(L["stops"])
font = next(
    (
        ImageFont.truetype(f, 26)
        for f in (
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
        )
        if os.path.exists(f)
    ),
    ImageFont.load_default(),
)
for fn in glob.glob(os.path.join(OUT, "*.png")):
    if "_legend" in fn or "atlas" in fn:
        continue
    im = Image.open(fn).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    x0, y0, w, h = 40, im.height - 120, 520, 22
    d.rounded_rectangle(
        (x0 - 20, y0 - 56, x0 + w + 20, y0 + h + 48), 14, fill=(20, 22, 28, 200)
    )
    for i in range(w):
        t = i / (w - 1) * (len(stops) - 1)
        k = min(int(t), len(stops) - 2)
        f = t - k
        c = stops[k] * (1 - f) + stops[k + 1] * f
        d.line((x0 + i, y0, x0 + i, y0 + h), fill=tuple(int(v * 255) for v in c))
    d.text((x0, y0 - 44), L["label"] + "  ·  facades + roofs", font=font, fill="white")
    for v in np.linspace(L["vmin"], L["vmax"], 5):
        xx = x0 + (v - L["vmin"]) / (L["vmax"] - L["vmin"]) * w
        d.text((xx - 12, y0 + h + 8), f"{v:.0f}", font=font, fill=(220, 220, 220))
    im.save(fn.replace(".png", "_legend.png"))
print("ok")
