"""External community links belong to Help, not the toolbar."""

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QToolButton

from qt_ui.windows.QLiberationWindow import QLiberationWindow


def test_community_links_are_only_in_help() -> None:
    app = QApplication.instance() or QApplication([])
    window: Any = QMainWindow()
    window.game_model = SimpleNamespace(game=None)
    window.open_campaign_notice = lambda notice: None
    opened = []
    window.showPayloadsEditor = lambda: opened.append("payloads")
    for name in (
        "newGameAction",
        "openAction",
        "saveGameAction",
        "saveAsAction",
        "openDiscordAction",
        "openGithubAction",
        "ukraineAction",
        "openSettingsAction",
        "openStatsAction",
        "openNotesAction",
        "commandPaletteAction",
        "showLiberationPrefDialogAction",
        "openLogsAction",
        "showAboutDialogAction",
    ):
        setattr(window, name, QAction(name, window))
    QLiberationWindow.initToolbar(window)
    QLiberationWindow.initMenuBar(window)
    assert (
        window.menu_strip.layout()
        .itemAt(window.menu_strip.layout().count() - 1)
        .widget()
        is window.notification_bell
    )
    assert window.notification_bell.accessibleName() == "Campaign alerts: 0"
    toolbar_actions = [
        button.defaultAction() for button in window.menu_strip.findChildren(QToolButton)
    ]
    help_menu = next(
        action.menu()
        for action in window.menu_bar.actions()
        if action.text() == "&Help"
    )
    assert [action.text() for action in window.menu_bar.actions()] == [
        "&File",
        "&Edit",
        "&Settings",
        "&Help",
    ]
    edit_menu = next(
        action.menu()
        for action in window.menu_bar.actions()
        if action.text() == "&Edit"
    )
    assert [action.text() for action in edit_menu.actions()] == ["Payloads"]
    edit_menu.actions()[0].trigger()
    assert opened == ["payloads"]
    for action in (window.openGithubAction, window.openDiscordAction):
        assert action not in toolbar_actions
        assert action in help_menu.actions()
    assert window.openStatsAction not in toolbar_actions
    assert window.openNotesAction not in toolbar_actions
    window.close()
    app.processEvents()
