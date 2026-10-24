"""Marking options are validated before campaign injection and retain defaults."""

import json
from pathlib import Path
from typing import Any

import pytest

from game.missiongenerator.realisticcasluadata import afac_marking_config


def test_marking_defaults_and_manifest_agree() -> None:
    manifest = json.loads(
        Path("resources/plugins/realisticcas/plugin.json").read_text()
    )
    options = {o["mnemonic"]: o["defaultValue"] for o in manifest["specificOptions"]}
    expected = {
        "markSeconds": 300,
        "messageSeconds": 15,
        "laserCode": 1688,
        "coordinateFormat": 0,
    }
    assert afac_marking_config({}) == afac_marking_config(options) == expected
    for option in manifest["specificOptions"]:
        if (
            option["mnemonic"].startswith("afac")
            and option["mnemonic"] != "afacEnabled"
        ):
            assert option["enabledBy"] == "afacEnabled"


@pytest.mark.parametrize(
    "key,value",
    [
        ("afacMarkMinutes", 0),
        ("afacMarkMinutes", 61),
        ("afacMarkMinutes", True),
        ("afacMarkMinutes", 1.5),
        ("afacMessageSeconds", 0),
        ("afacMessageSeconds", "15"),
        ("afacMessageSeconds", 301),
        ("afacLaserCode", 1488),
        ("afacLaserCode", 1689),
        ("afacLaserCode", 1698),
        ("afacLaserCode", 1600),
        ("afacCoordinateFormat", -1),
        ("afacCoordinateFormat", 3),
        ("afacCoordinateFormat", False),
    ],
)
def test_invalid_saved_marking_options_are_rejected(key: str, value: Any) -> None:
    with pytest.raises(ValueError, match="Realistic CAS"):
        afac_marking_config({key: value})


def test_custom_marking_configuration_is_exported() -> None:
    assert afac_marking_config(
        {
            "afacMarkMinutes": 2,
            "afacMessageSeconds": 25,
            "afacLaserCode": 1677,
            "afacCoordinateFormat": 2,
        }
    ) == {
        "markSeconds": 120,
        "messageSeconds": 25,
        "laserCode": 1677,
        "coordinateFormat": 2,
    }
