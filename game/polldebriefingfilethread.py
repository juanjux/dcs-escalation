from __future__ import annotations

import json
import logging
import os
import time
from glob import glob
from pathlib import Path
from threading import Event, Thread
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game.debriefing import Debriefing
    from game.sim import MissionSimulation

#: How often (seconds) we look for a fresh state.json. The DCS export hook
#: rewrites the file every second once the mission has ended, so a short
#: interval keeps end-of-mission detection responsive without burning CPU.
POLL_INTERVAL_SECONDS = 2


def _candidate_state_dirs() -> list[Path]:
    """Directories the DCS export hook may write ``state.json`` into.

    Mirrors the discovery order of ``resources/plugins/base/
    dcs_retribution.lua`` so the Python side looks wherever the Lua side
    actually managed to write. DCS' mission-scripting sandbox frequently
    blocks writing to the install/TEMP paths, so the file commonly lands in
    the DCS "Saved Games" ``Missions`` folder instead — which the old
    CWD-only check never saw, causing end-of-mission detection to silently
    fail.
    """
    dirs: list[Path] = []
    export_dir = os.getenv("ESCALATION_EXPORT_DIR")
    if export_dir:
        dirs.append(Path(export_dir))
    # The install dir is what the app passes to the mission as
    # dcsRetribution.installPath (game/missiongenerator/luagenerator.py).
    dirs.append(Path(os.path.abspath(".")))
    for tmp_var in ("TEMP", "TMP"):
        tmp = os.getenv(tmp_var)
        if tmp:
            dirs.append(Path(tmp))
    try:
        from game.persistency import base_path

        dirs.append(Path(base_path()) / "Missions")
    except Exception:  # pragma: no cover - persistency not set up yet
        logging.debug(
            "Could not resolve DCS Missions dir for state.json", exc_info=True
        )

    seen: set[str] = set()
    unique: list[Path] = []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _candidate_state_files() -> list[Path]:
    """Every plausible state file across all candidate directories.

    Handles both the normal ``state.json`` and the timestamped
    ``state-<n>.json`` variant produced when the
    ``ESCALATION_EXPORT_STAMPED_STATE`` env var is set on the DCS side.
    """
    files: list[Path] = []
    for d in _candidate_state_dirs():
        files.append(d / "state.json")
        try:
            files.extend(Path(p) for p in glob(str(d / "state-*.json")))
        except OSError:
            pass
    return files


def _newest_existing(files: list[Path]) -> Optional[tuple[Path, float]]:
    """Return the existing state file with the most recent mtime, if any."""
    best: Optional[tuple[Path, float]] = None
    for f in files:
        try:
            mtime = os.path.getmtime(f)
        except OSError:
            continue
        if best is None or mtime > best[1]:
            best = (f, mtime)
    return best


class PollDebriefingFileThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(
        self,
        callback: Callable[[Debriefing], None],
        mission_sim: MissionSimulation,
    ) -> None:
        super().__init__()
        self._stop_event = Event()
        self.callback = callback
        self.mission_sim = mission_sim

    def stop(self) -> None:
        self._stop_event.set()

    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        logging.info(
            "Watching for DCS state.json in: %s",
            ", ".join(str(d) for d in _candidate_state_dirs()),
        )
        # Only react to state files written after this mission's .miz was
        # generated. This ignores a stale file left over from a previous
        # mission, yet still picks up THIS mission's result even if DCS
        # finished writing it (mission_ended) before we started watching —
        # the previous code seeded from the existing file's mtime and only
        # reacted to a strictly-newer write, so an already-finished mission
        # was frequently never auto-detected.
        last_modified = self.mission_sim.miz_generated_at
        logging.info(
            "Ignoring state files older than mission launch (mtime <= %s)",
            last_modified,
        )

        while not self.stopped():
            try:
                # Re-scan every tick: the stamped variant creates new files,
                # and the Lua hook may only manage to write partway through.
                newest = _newest_existing(_candidate_state_files())
                if newest is not None and newest[1] > last_modified:
                    state_path, mtime = newest
                    logging.info("Reading DCS state from %s", state_path)
                    debriefing = self.mission_sim.debrief_current_state(state_path)
                    self.callback(debriefing)
                    last_modified = mtime
                    if debriefing.state_data.mission_ended:
                        logging.info(
                            "Mission end detected from %s; stopping poll",
                            state_path,
                        )
                        break
            except (json.JSONDecodeError, OSError, ValueError, KeyError):
                logging.error(
                    "Failed to read DCS state.json (likely read while DCS was "
                    "still writing it); will retry in %ss.",
                    POLL_INTERVAL_SECONDS,
                    exc_info=True,
                )
            time.sleep(POLL_INTERVAL_SECONDS)
