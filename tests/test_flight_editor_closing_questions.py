"""Closing the flight editor asks about what was just edited.

Two questions hang off closing it: whether the ingress point should move now that the
package's stand-off range has changed (swap a JDAM for a JSOW and the launch range
goes from nothing to 40 nm), and whether a tanker should be sent. Both live in
on_close, which was connected to `finished` inside the "Go to package" handler --
one of four ways out of the dialog, and there only after the accept() that would have
fired it. So neither question was ever asked on the way out.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("qt_ui/windows/mission/QEditFlightDialog.py")


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from {SOURCE}")


def _connects_on_close(node: ast.AST) -> bool:
    """Whether this function wires `finished` to on_close."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute) or func.attr != "connect":
            continue
        target = func.value
        if isinstance(target, ast.Attribute) and target.attr == "finished":
            return True
    return False


def test_the_close_hook_is_wired_when_the_dialog_is_built() -> None:
    assert _connects_on_close(_function("__init__"))


def test_it_is_not_wired_from_a_button_handler() -> None:
    """Where it was: one path out of four, and after the accept() that fires it."""
    assert not _connects_on_close(_function("on_go_to_package"))


def test_closing_still_asks_both_questions() -> None:
    """on_close is the only thing `finished` reaches, so the two questions have to be
    what it runs."""
    body = ast.unparse(_function("_apply_pending_changes"))
    assert "_recreate_package_if_standoff_changed" in body
    assert "_offer_to_move_the_refuelling_waypoint" in body
    assert "_apply_pending_changes" in ast.unparse(_function("on_close"))
