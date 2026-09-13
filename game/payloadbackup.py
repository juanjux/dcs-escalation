"""Snapshots of the user's DCS payload library.

The custom loadouts a player builds -- in the Mission Editor or in Escalation's own
payload editor -- live as one ``.lua`` per airframe under
``Saved Games/DCS/MissionEditor/UnitPayloads``. Two things make that directory worth
protecting:

* it sits inside ``MissionEditor``, the folder people are routinely told to delete when
  the Mission Editor misbehaves. Everything else in there is a setting or a cache that
  DCS regenerates on the next launch, so the advice circulates without a warning
  attached;
* nothing else holds a copy. The loadouts are not in the campaign save, not in the
  generated ``.miz``, and DCS keeps no backup of its own. A library built over years is
  gone the moment that folder is.

So take a snapshot on startup, before anything can write to the directory, and keep the
last few.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

#: How many snapshots to keep. They are a few hundred KB each, but there is no reason
#: to hoard them either.
MAX_BACKUPS = 10

MANIFEST_NAME = "manifest.json"


def _fingerprint(directory: Path) -> str:
    """What the directory holds right now: name, size and mtime for each file.

    Enough to tell "nothing has changed since the last snapshot" from "someone edited a
    loadout" without reading a single .lua. Serialized rather than compared as objects
    so a round trip through JSON cannot change the answer.
    """
    entries = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append([path.name, stat.st_size, stat.st_mtime_ns])
    return json.dumps(entries)


def _read_manifest(snapshot: Path) -> Optional[tuple[int, str]]:
    """A snapshot's ``(sequence, fingerprint)``, or None if it is not a usable snapshot.

    Anything unreadable, half-written or simply not ours reads as None so it is neither
    compared against nor rotated away.
    """
    try:
        manifest = json.loads((snapshot / MANIFEST_NAME).read_text(encoding="utf-8"))
        return int(manifest["seq"]), json.dumps(manifest["files"])
    except Exception:
        return None


def _ordered(backups: Path) -> list[tuple[int, str, Path]]:
    """Existing snapshots as ``(sequence, name, path)``, oldest first.

    Ordered by a sequence number each snapshot records for itself, not by its directory
    name and not by a wall clock. Names are not a safe clock -- rotation frees one, and
    the next snapshot would take the freed name back and sort itself *before* the older
    snapshots that outlived it, so rotation would then delete the newest backups and
    keep the oldest, the one thing this must never do. A timestamp is no safer: it is
    only as monotonic as the machine's clock, which can be adjusted backwards.
    """
    if not backups.is_dir():
        return []
    found = []
    for path in backups.iterdir():
        if not path.is_dir():
            continue
        manifest = _read_manifest(path)
        if manifest is not None:
            found.append((manifest[0], path.name, path))
    return sorted(found)


def _snapshots(backups: Path) -> list[Path]:
    return [path for _, _, path in _ordered(backups)]


def _destination(backups: Path, stamp: str) -> Path:
    """A snapshot directory for ``stamp``, uniquified if the name is already taken."""
    candidate = backups / stamp
    suffix = 2
    while candidate.exists():
        candidate = backups / f"{stamp}-{suffix}"
        suffix += 1
    return candidate


def _rotate(backups: Path, keep: int) -> None:
    snapshots = _snapshots(backups)
    for stale in snapshots[: max(len(snapshots) - keep, 0)]:
        shutil.rmtree(stale, ignore_errors=True)


def backup_payloads(
    payloads: Path, backups: Path, keep: int = MAX_BACKUPS
) -> Optional[Path]:
    """Snapshot ``payloads`` into ``backups``. Returns the snapshot, or None.

    None means no snapshot was needed or none could be taken: the library is missing or
    empty, it is byte-for-byte what the last snapshot already holds, or something went
    wrong. Never raises -- failing to take a backup is not a reason to refuse to start.
    """
    try:
        return _backup_payloads(payloads, backups, keep)
    except Exception:
        logging.exception("Could not back up the payload library at %s", payloads)
        return None


def _backup_payloads(payloads: Path, backups: Path, keep: int) -> Optional[Path]:
    if not payloads.is_dir():
        return None
    fingerprint = _fingerprint(payloads)
    if fingerprint == "[]":
        # An empty library is not worth a snapshot, and taking one would push a real
        # snapshot out of the rotation on every launch after the directory is wiped --
        # destroying the backups precisely when they are the only remaining copy.
        return None
    existing = _ordered(backups)
    if existing:
        newest = _read_manifest(existing[-1][2])
        if newest is not None and newest[1] == fingerprint:
            return None
    sequence = existing[-1][0] + 1 if existing else 1
    taken = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = _destination(backups, taken)
    destination.mkdir(parents=True)
    for path in sorted(payloads.iterdir()):
        if path.is_file():
            shutil.copy2(path, destination / path.name)
    # Written last, so a snapshot interrupted half-way is not mistaken for a complete
    # one -- neither by the rotation nor by the next launch's comparison. `taken` is
    # for the human reading the folder; `seq` is what the code orders by.
    (destination / MANIFEST_NAME).write_text(
        json.dumps({"seq": sequence, "taken": taken, "files": json.loads(fingerprint)}),
        encoding="utf-8",
    )
    _rotate(backups, keep)
    return destination
