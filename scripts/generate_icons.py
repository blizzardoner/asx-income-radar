from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "public" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def make_icon(size: int, name: str):
    image = Image.new("RGB", (size, size), "#080b13")
    draw = ImageDraw.Draw(image)
    center = size / 2
    for ratio, color, width in [(0.34, "#232d3f", 0.012), (0.25, "#36405a", 0.01), (0.14, "#8b5cf6", 0.025)]:
        radius = size * ratio
        draw.ellipse((center - radius, center - radius, center + radius, center + radius), outline=color, width=max(2, int(size * width)))
    draw.line((center, center, size * 0.77, size * 0.27), fill="#32d3c7", width=max(4, int(size * 0.035)))
    dot = size * 0.035
    draw.ellipse((size * 0.74 - dot, size * 0.27 - dot, size * 0.74 + dot, size * 0.27 + dot), fill="#f3c969")
    core = size * 0.055
    draw.ellipse((center - core, center - core, center + core, center + core), fill="#8b5cf6")
    image.save(OUT / name, optimize=True)


make_icon(192, "icon-192.png")
make_icon(512, "icon-512.png")
make_icon(180, "apple-touch-icon.png")
print(OUT)
