"""Check packaged artwork without importing the game or starting DCS."""

import json
from pathlib import Path

import pytest
from PIL import Image
from PIL.IcoImagePlugin import IcoImageFile

ROOT = Path(__file__).resolve().parents[1]
ICON_SIZES = {16, 20, 24, 32, 40, 48, 64, 96, 128, 256}


@pytest.mark.parametrize(
    "filename,size",
    [
        ("resources/icon.png", 256),
        ("client/public/logo192.png", 192),
        ("client/public/logo512.png", 512),
    ],
)
def test_icon_png_dimensions_and_transparency(filename: str, size: int) -> None:
    with Image.open(ROOT / filename) as icon:
        assert icon.size == (size, size)
        assert icon.mode == "RGBA"
        assert icon.getchannel("A").getextrema() == (0, 255)
        assert icon.getpixel((0, 0))[3] == 0


@pytest.mark.parametrize(
    "filename", ["resources/icon.ico", "client/public/favicon.ico"]
)
def test_icon_contains_windows_sizes(filename: str) -> None:
    with Image.open(ROOT / filename) as icon:
        assert isinstance(icon, IcoImageFile)
        assert icon.info["sizes"] == {(size, size) for size in ICON_SIZES}
        for size in ICON_SIZES:
            icon.size = (size, size)
            icon.load()
            frame = icon.convert("RGBA")
            assert frame.size == (size, size)
            assert frame.convert("RGBA").getpixel((0, 0))[3] == 0


def test_splash_retains_original_window_dimensions() -> None:
    with Image.open(ROOT / "resources/ui/splash_screen.png") as splash:
        assert splash.size == (647, 458)
        splash.verify()


def test_web_manifest_matches_packaged_icons() -> None:
    manifest = json.loads(
        (ROOT / "client/public/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "DCS Escalation"
    for entry in manifest["icons"]:
        assert (ROOT / "client/public" / entry["src"]).is_file()
    sizes = manifest["icons"][0]["sizes"].split()
    assert set(sizes) == {f"{size}x{size}" for size in ICON_SIZES}
