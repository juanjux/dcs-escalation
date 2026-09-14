"""Kept as the import path the rest of the app already uses.

The dialog grew three panes and a mode header and became a package; this is the
one name anything outside it ever asked for.
"""

from qt_ui.windows.airwingconfig import AirWingConfigurationDialog

__all__ = ["AirWingConfigurationDialog"]
