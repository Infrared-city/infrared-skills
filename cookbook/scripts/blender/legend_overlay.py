"""Draw the fixed-domain legend onto the renders of `blender_facade_results.py`.

Run with a normal Python (Blender has no PIL):  python legend_overlay.py renders/
Reads `legend_<slug>.json` for every `<slug>_<view>.png`, writes `<slug>_<view>_legend.png`.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_legend(
    image: Image.Image, legend: dict, font: ImageFont.ImageFont
) -> Image.Image:
    stops = np.array(legend["stops"])
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out, "RGBA")
    x0, y0, width, height = 40, out.height - 120, 520, 22
    draw.rounded_rectangle(
        (x0 - 20, y0 - 56, x0 + width + 20, y0 + height + 48),
        14,
        fill=(20, 22, 28, 200),
    )
    for i in range(width):
        t = i / (width - 1) * (len(stops) - 1)
        k = min(int(t), len(stops) - 2)
        colour = stops[k] + (stops[k + 1] - stops[k]) * (t - k)
        draw.line(
            (x0 + i, y0, x0 + i, y0 + height), fill=tuple(int(c * 255) for c in colour)
        )
    draw.text(
        (x0, y0 - 44), f"{legend['label']}  ·  facades + roofs", font=font, fill="white"
    )
    vmin, vmax = legend["vmin"], legend["vmax"]
    for value in np.linspace(vmin, vmax, 5):
        x = x0 + (value - vmin) / (vmax - vmin) * width
        draw.text(
            (x - 12, y0 + height + 8), f"{value:.0f}", font=font, fill=(220, 220, 220)
        )
    return out


def main(folder: Path) -> None:
    font = load_font(26)
    for png in sorted(folder.glob("*_*.png")):
        if png.stem.endswith("_legend"):
            continue
        slug = png.stem.rsplit("_", 1)[0]
        legend_file = folder / f"legend_{slug}.json"
        if legend_file.exists():
            legend = json.loads(legend_file.read_text())
            draw_legend(Image.open(png), legend, font).save(
                png.with_name(f"{png.stem}_legend.png")
            )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
