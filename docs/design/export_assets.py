"""Export the approved artwork without regenerating or retouching it.

Run from any directory with the project's Pillow dependency installed.
"""

from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/design"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def main() -> None:
    with Image.open(DESIGN / "escalation-icons/04-simple-jet-outlined.png") as source:
        icon = source.convert("RGBA")
    if icon.getchannel("A").getextrema() != (0, 255):
        raise ValueError("The approved icon must have real alpha transparency")

    for filename, size in (
        ("resources/icon.png", 256),
        ("client/public/logo192.png", 192),
        ("client/public/logo512.png", 512),
    ):
        icon.resize((size, size), Image.Resampling.LANCZOS).save(ROOT / filename)
    for filename in ("resources/icon.ico", "client/public/favicon.ico"):
        icon.save(
            ROOT / filename,
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )

    with Image.open(DESIGN / "escalation-splash/02-dawn-slava-ukraini.png") as source:
        splash = ImageOps.pad(
            source.convert("RGB"),
            (647, 458),
            method=Image.Resampling.LANCZOS,
            color="#101D35",
        )
        splash.save(ROOT / "resources/ui/splash_screen.png")


if __name__ == "__main__":
    main()
