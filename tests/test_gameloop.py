from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from game.sim.gameloop import GameLoop


def test_failed_simulation_start_can_be_retried(tmp_path: Path) -> None:
    loop = GameLoop.__new__(GameLoop)
    loop.started = False
    simulation: Any = Mock()
    simulation.begin_simulation.side_effect = [OverflowError("bad flight time"), None]
    loop.sim = simulation
    output = tmp_path / "mission.miz"

    with pytest.raises(OverflowError, match="bad flight time"):
        loop.generate_miz(output)
    assert not bool(loop.started)
    simulation.generate_miz.assert_not_called()

    loop.generate_miz(output)
    assert loop.started
    assert simulation.begin_simulation.call_count == 2
    simulation.generate_miz.assert_called_once_with(output)
