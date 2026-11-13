# tests/test_support_page_pagination.py
"""SupportPage.paginate: splits by measured height so nothing is cut off.

The single-page SupportPage.write incremented y without bounds, so a long
flights comm-ladder pushed the AEW&C / Tankers tables off the bottom of
the fixed 960x1080 page. paginate() must spill onto extra pages instead, keeping
every section reachable, while a mission that fits on one page renders with no
``(1/1)`` suffix.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from game.missiongenerator.kneeboard import SupportPage

# --- Minimal fakes -----------------------------------------------------------
#
# We avoid the heavy FlightData / AwacsInfo / TankerInfo / CommInfo
# machinery: SupportPage only touches a handful of attributes, and by making
# channels_for() return [] the frequency formatting degrades to str(freq),
# which sidesteps needing real radio/channel objects.


@dataclass
class FakeAircraftType:
    name: str = "F/A-18C"

    def __str__(self) -> str:
        return self.name

    def channel_name(self, radio_id: int, channel: int) -> str:
        return f"COMM{radio_id} Ch {channel}"


@dataclass
class FakePackage:
    package_description: str = "STRIKE"
    custom_name: str = ""
    frequency: str = "251.000 MHz"
    time_over_target: datetime.datetime | None = None


@dataclass
class FakeFlight:
    callsign: str
    custom_name: str = ""
    intra_flight_channel: str = "305.000 MHz"
    flight_type: str = "STRIKE"
    aircraft_type: FakeAircraftType = field(default_factory=FakeAircraftType)
    units: List[object] = field(default_factory=lambda: [object(), object()])
    package: FakePackage = field(default_factory=FakePackage)

    def channels_for(self, frequency: object) -> List[object]:
        # No named channels -> format_frequency falls back to str(frequency).
        return []


@dataclass
class FakeComm:
    name: str
    freq: str = "251.000 MHz"


@dataclass
class FakeAwacs:
    callsign: str
    freq: str = "251.000 MHz"
    depature_location: str | None = "Departure Field"
    start_time: datetime.datetime = datetime.datetime(2020, 1, 1, 8, 0, 0)
    end_time: datetime.datetime = datetime.datetime(2020, 1, 1, 12, 0, 0)


@dataclass
class FakeTanker:
    callsign: str
    variant: str = "KC-135"
    tacan: object | None = None
    freq: str = "251.000 MHz"
    start_time: datetime.datetime = datetime.datetime(2020, 1, 1, 8, 0, 0)
    end_time: datetime.datetime = datetime.datetime(2020, 1, 1, 12, 0, 0)


def _paginate(
    flight: FakeFlight,
    package_flights: List[FakeFlight],
    awacs: List[FakeAwacs],
    tankers: List[FakeTanker],
) -> List[SupportPage]:
    return SupportPage.paginate(
        flight,  # type: ignore[arg-type]
        package_flights,  # type: ignore[arg-type]
        [],  # comms (paginate appends the intra-flight entry itself)
        awacs,  # type: ignore[arg-type]
        tankers,  # type: ignore[arg-type]
        datetime.datetime(2020, 1, 1, 8, 0, 0),
        dark_kneeboard=False,
    )


def _sidecar_text(page: SupportPage, tmp_path: Path, idx: int) -> str:
    png = tmp_path / f"support{idx:02}.png"
    page.write(png)
    return png.with_suffix(".txt").read_text("utf8")


def test_small_mission_fits_on_one_page(tmp_path: Path) -> None:
    flight = FakeFlight("Colt 1-1")
    package_flights = [FakeFlight(f"Package {i}") for i in range(3)]
    awacs = [FakeAwacs("Overlord")]
    tankers = [FakeTanker("Texaco")]

    pages = _paginate(flight, package_flights, awacs, tankers)

    assert len(pages) == 1
    text = _sidecar_text(pages[0], tmp_path, 0)
    # Every section present on the single page.
    for token in ("STRIKE Package", "AEW&C", "Tankers", "Overlord", "Texaco"):
        assert token in text


def test_single_page_has_no_pagination_suffix(tmp_path: Path) -> None:
    flight = FakeFlight("Colt 1-1")
    pages = _paginate(flight, [], [FakeAwacs("Overlord")], [])

    assert len(pages) == 1
    assert pages[0].total_pages == 1
    text = _sidecar_text(pages[0], tmp_path, 0)
    # Title line is present, without a "(1/1)" page suffix.
    assert "Colt 1-1 Support Info" in text
    assert "(1/1)" not in text


def test_many_flights_paginate_without_losing_support_tables(tmp_path: Path) -> None:
    flight = FakeFlight("Colt 1-1")
    # 40+ package flights is enough to blow past a single page's comm-ladder.
    package_flights = [FakeFlight(f"Package {i}") for i in range(48)]
    awacs = [FakeAwacs("Overlord"), FakeAwacs("Magic")]
    tankers = [FakeTanker("Texaco"), FakeTanker("Arco")]

    pages = _paginate(flight, package_flights, awacs, tankers)

    assert len(pages) > 1, "many flights must spill onto multiple pages"

    # Every support section must survive somewhere across the pages -- the bug
    # was that these got pushed off the bottom of the single page and lost.
    all_text = "\n".join(
        _sidecar_text(page, tmp_path, idx) for idx, page in enumerate(pages)
    )
    for token in (
        "AEW&C",
        "Overlord",
        "Magic",
        "Tankers",
        "Texaco",
        "Arco",
    ):
        assert token in all_text, f"{token!r} was lost during pagination"

    # Multi-page => pages carry a running "(n/N)" suffix in their title text.
    assert all(page.total_pages == len(pages) for page in pages)
    assert f"(1/{len(pages)})" in _sidecar_text(pages[0], tmp_path, 0)


def test_pagination_never_overflows_page_height(tmp_path: Path) -> None:
    """Rendered content must stay within the 1080px page on every page."""
    from game.missiongenerator.kneeboard import KneeboardPageWriter

    flight = FakeFlight("Colt 1-1")
    package_flights = [FakeFlight(f"Package {i}") for i in range(60)]
    awacs = [FakeAwacs("Overlord")]
    tankers = [FakeTanker("Texaco")]

    pages = _paginate(flight, package_flights, awacs, tankers)
    assert len(pages) > 1

    proto = KneeboardPageWriter()
    max_y = proto.max_content_y
    margin = proto.page_margin
    for idx, page in enumerate(pages):
        # Re-measure this page's committed content the same way write() draws it:
        # title + each assigned section (title_render once + its table). measure()
        # reports height from the top margin, so add the margin back for the
        # absolute lowest y the page reaches.
        def render(w: KneeboardPageWriter, page: SupportPage = page) -> None:
            w.title("X")
            for section in page.sections:
                section.title_render(w)
                w.table(section.rows, headers=section.headers)

        used = margin + KneeboardPageWriter.measure(render)
        assert used <= max_y, f"page {idx} overflowed: {used} > {max_y}"
