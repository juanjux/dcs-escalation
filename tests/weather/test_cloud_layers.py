"""Installed cloud geometry is optional, pack-specific and clearly estimated."""

from pathlib import Path

from dcs.weather import CloudPreset, Weather
import pytest

from game.weather.cloudlayers import CloudLayer, estimated_layers
from game.weather.clouds import Clouds

PRESET = """
clouds = { presets = {
 Preset82 = {
  readableNameShort = _('Cumulus & Altocumulus 2 [ATMOS-X]'),
  readableName = 'a brace } in a label', -- another }
  layers = {
   { altitudeMin = 620, altitudeMax = 2349, density = 0.5, coverage = 0.55 },
   { altitudeMin = 7560, altitudeMax = 8561, density = 0, coverage = 0 },
   { altitudeMin = 6706, altitudeMax = 7316, density = 0.4, coverage = 0.6 },
  },
 },
} }
"""


def _clouds(name: str = "Cumulus & Altocumulus 2 [ATMOS-X]") -> Clouds:
    return Clouds(
        4364,
        0,
        0,
        Weather.Preceptions.None_,
        CloudPreset("Preset82", name, "82 ##2 layers, low/mid", 620, 8561),
    )


def _install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str = PRESET
) -> Path:
    # Test fixture writes do not modify an installed DCS tree.
    path = tmp_path / "Config" / "Effects" / "clouds.lua"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(
        "qt_ui.liberation_install.get_dcs_install_directory", lambda: str(tmp_path)
    )
    return tmp_path


def test_active_layers_are_translated_and_disabled_layer_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = _install(tmp_path, monkeypatch)
    assert estimated_layers(_clouds(), install) == [
        CloudLayer(4364, 6093),
        CloudLayer(10450, 11060),
    ]


def test_same_identifier_in_another_pack_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        estimated_layers(_clouds("A different pack"), _install(tmp_path, monkeypatch))
        == []
    )


@pytest.mark.parametrize(
    "text", ["", "Preset82 = {", PRESET.replace("620,", "unknown(),")]
)
def test_missing_or_unsupported_geometry_does_not_break_forecast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    assert estimated_layers(_clouds(), _install(tmp_path, monkeypatch, text)) == []


def test_no_installation_or_nonpreset_clouds(tmp_path: Path) -> None:
    assert estimated_layers(_clouds(), tmp_path) == []
    assert (
        estimated_layers(Clouds(1000, 5, 200, Weather.Preceptions.None_), tmp_path)
        == []
    )
