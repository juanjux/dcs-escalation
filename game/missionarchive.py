"""Archive every generated mission so the flown ``.miz`` is never lost.

Escalation generates each turn to one fixed path -- ``retribution_nextturn.miz``,
the name the wiki, the bug-report template and every dedicated-server workflow
tell you to load -- so each **Take off** silently overwrites the mission that was
just flown. That is fine for flying and lossy for everything after it: a bug found in a
flown mission is routinely diagnosed from that mission alongside its debrief log,
and by then the next turn has already overwritten it.

The fixed output is left exactly as it is -- nothing downstream moves, because
nothing downstream ever depended on the name (DCS writes ``state.json`` to a fixed
path, and the debrief poll decides "is this result mine?" by comparing mtime
against ``miz_generated_at``, never by filename). Each generated mission is
*additionally* copied to
``Missions/Retribution Archive/<campaign>_turn<NN>_<stamp>.miz``.

Two properties this module is built around:

* **It never breaks Take off.** Archiving is best-effort: every failure is logged
  and swallowed. A full disk must not cost the user the mission they just
  generated -- by the time we run, it is already written and flyable.
* **It only ever prunes its own output.** Retention is scoped to files matching
  :data:`_ARCHIVED_MISSION` inside the archive directory, so a hand-named miz that
  ends up in there is never deleted.

There is no ``Settings`` toggle: the archive is a bounded ring buffer in an
obvious folder, and a toggle you can forget to switch on defeats the one thing it
is for -- the copy has to already exist by the time you want it.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from game.persistency import mission_archive_dir

if TYPE_CHECKING:
    from game import Game

#: How many archived missions to keep. Mission size is dominated by kneeboard
#: images and so scales with the number of player-crewed airframes: a solo turn is
#: ~1 MB, a fully-crewed multiplayer mission ~9 MB. Sized off the larger case, this
#: stays under 200 MB at worst and still covers a campaign's worth of turns. Note a
#: turn re-generated while replanning writes its own entry, so this is not 20 turns.
KEEP_ARCHIVED_MISSIONS = 20

#: Matches only what :func:`archive_name_for` produces. The prune is scoped to this
#: so nothing else in the archive directory can ever be deleted.
_ARCHIVED_MISSION = re.compile(r".+_turn\d+_\d{8}-\d{6}\.miz$")

_UNSAFE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """A filesystem-safe stem for a campaign name, e.g. ``germany_1980_red_tide``."""
    return _UNSAFE.sub("_", name.lower()).strip("_") or "campaign"


def archive_name_for(game: Game, when: datetime) -> str:
    """The archive filename for ``game``'s current turn, generated at ``when``.

    The turn is the raw ``game.turn`` -- the same 0-indexed number the kneeboard shows, so the archived file and the deck in it agree
    on which mission this is. The timestamp keeps a re-generated turn from
    clobbering the copy of the one that was actually flown.
    """
    campaign = _slugify(game.campaign_name or "campaign")
    return f"{campaign}_turn{game.turn:02d}_{when:%Y%m%d-%H%M%S}.miz"


def archive_mission(game: Game, miz: Path) -> Optional[Path]:
    """Copy the just-generated ``miz`` into the archive and prune old entries.

    Returns the archived path, or ``None`` if archiving failed -- which is never
    fatal, and deliberately not raised: ``miz`` itself is already written.
    """
    try:
        directory = mission_archive_dir()
        archived = directory / archive_name_for(game, datetime.now())
        shutil.copy2(miz, archived)
    except (OSError, AssertionError):
        # AssertionError: persistency.setup() was never called (headless tests,
        # dev scripts). Either way the generated mission is untouched.
        logging.warning(
            "Could not archive %s (mission itself is fine)", miz, exc_info=True
        )
        return None
    logging.info("Archived generated mission to %s", archived)
    _prune(directory)
    return archived


def _prune(directory: Path) -> None:
    """Delete archived missions beyond the newest :data:`KEEP_ARCHIVED_MISSIONS`."""
    try:
        archived = sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and _ARCHIVED_MISSION.match(path.name)
            ),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        logging.warning(
            "Could not read %s to prune old missions", directory, exc_info=True
        )
        return
    for path in archived[: max(0, len(archived) - KEEP_ARCHIVED_MISSIONS)]:
        try:
            path.unlink()
        except OSError:
            logging.warning("Could not prune archived mission %s", path, exc_info=True)
        else:
            logging.info(
                "Pruned archived mission %s (keeping the newest %d)",
                path,
                KEEP_ARCHIVED_MISSIONS,
            )
