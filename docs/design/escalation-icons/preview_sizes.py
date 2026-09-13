"""Render unchanged icon proposals at exact pixel sizes for comparison."""

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SOURCES = ["01-dawn-falcon", "02-escalation-e", "03-ukraine-insignia"]
LABELS = ["1 · F-16", "2 · E", "3 · Escudo"]
OUTPUT = "icon-size-comparison.png"
if "--minimal" in sys.argv:
    SOURCES = ["04-simple-jet", "05-simple-e", "06-simple-formation"]
    LABELS = ["4 · Caza", "5 · E", "6 · Trío"]
    OUTPUT = "minimal-size-comparison.png"
if "--outlined" in sys.argv:
    SOURCES = ["04-simple-jet", "04-simple-jet-outlined"]
    LABELS = ["Original", "Con borde"]
    OUTPUT = "outlined-size-comparison.png"
SIZES = [16, 24, 32, 48, 64]
font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
heading = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 15)
canvas = Image.new("RGB", (720, 462), "#ffffff")
draw = ImageDraw.Draw(canvas)
images = [Image.open(ROOT / f"{name}.png").convert("RGBA") for name in SOURCES]

for offset, background, foreground, title in [
    (0, "#202329", "#f1f4f8", "Fondo oscuro"),
    (360, "#f0f2f5", "#18202a", "Fondo claro"),
]:
    draw.rectangle((offset, 0, offset + 359, 461), fill=background)
    draw.text((offset + 20, 14), title, fill=foreground, font=heading)
    for index, label in enumerate(LABELS):
        draw.text((offset + 78 + index * 92, 46), label, fill=foreground, font=font)
    for row, size in enumerate(SIZES):
        center_y = 95 + row * 76
        draw.text((offset + 14, center_y - 9), f"{size} px", fill=foreground, font=font)
        for index, source in enumerate(images):
            resized = source.resize((size, size), Image.Resampling.LANCZOS)
            center_x = offset + 104 + index * 92
            canvas.paste(resized, (center_x - size // 2, center_y - size // 2), resized)

output = ROOT / OUTPUT
canvas.save(output)
print(output)
for name, source in zip(SOURCES, images):
    print(f"{name}: {source.size}, alpha extrema={source.getchannel('A').getextrema()}")
