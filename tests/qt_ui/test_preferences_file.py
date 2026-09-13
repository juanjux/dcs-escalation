"""Where the player's own settings are read from.

The rename to Escalation went through every occurrence of the old name and kept the
ones that were contracts with something already on his disk. This one got through:
his DCS paths, his theme and his server port live in a file under
%LOCALAPPDATA%\DCSRetribution, and a renamed file is a first-start dialog on a
machine that has been set up for a year.
"""

from __future__ import annotations


def test_the_preferences_keep_the_name_they_were_written_under() -> None:
    from qt_ui.liberation_install import PREFERENCES_PATH, USER_PATH

    assert PREFERENCES_PATH.name == "retribution_preferences.json"
    assert PREFERENCES_PATH.parent == USER_PATH
    # The folder was never renamed either: the whole location is where it was.
    assert USER_PATH.name == "DCSRetribution"
