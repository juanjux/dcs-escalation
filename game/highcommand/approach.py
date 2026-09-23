"""What it costs our aircraft to get a weapon within reach of a point.

The theater is laid out as a grid, and a cell costs what flying a mile through it
costs: the mile itself, plus a penalty for every enemy ring the cell is inside, heavier
the further that site reaches and the closer the cell is to it. The cheapest route
from any of our bases to every cell is worked out once, so an objective is judged by
the cheapest cell a weapon can reach it from, plus the weapon's own flight from there:
a missile flying over a ring can be shot down too. A battery on the coast hit from
outside its own ring by a missile coming in over the sea is cheap; an objective behind
two rings costs the detour or the rings, whichever is less, and a missile fired at it
from outside them still has to cross them.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Sequence

import numpy as np
import numpy.typing as npt

from game.utils import nautical_miles

if TYPE_CHECKING:
    from dcs import Point

#: The side of a grid cell.
CELL = nautical_miles(5)

#: How far past the outermost base or objective the grid goes, for routes that go
#: round a ring rather than through it.
MARGIN = nautical_miles(100)

#: What a mile inside a ring costs on top of the mile, per point of ring weight, in
#: miles of flying outside every ring. At the centre of a long-range SAM, weighing 4, a
#: mile costs seventeen.
RING_COST = 4.0

#: The same for a mile of a weapon's own flight after release, far less than an
#: aircraft's: a weapon is harder to hit, cheaper to lose, and fired from outside a
#: ring precisely so that the aircraft does not have to go in.
WEAPON_RING_COST = 0.5

#: How many points along a weapon's flight are looked at.
WEAPON_SAMPLES = 12

#: Release points are looked for every this many cells.
RELEASE_STRIDE = 2


@dataclass(frozen=True)
class Ring:
    """A site's threat ring: how far it reaches and what it weighs at its centre."""

    #: Whatever the ring belongs to, handed back in a route's rings.
    site: Any
    x: float
    y: float
    reach: float
    weight: float

    def weight_at(self, x: float, y: float) -> float:
        distance = math.hypot(x - self.x, y - self.y)
        if distance > self.reach:
            return 0.0
        return self.weight * (self.reach - distance) / self.reach


@dataclass(frozen=True)
class Release:
    """How close a weapon has to be brought to an objective, and what needing that
    weapon adds to the route, in miles."""

    radius: float
    penalty: float = 0.0


@dataclass(frozen=True)
class Route:
    """The cheapest way to put a weapon on an objective."""

    #: In miles of flying outside every ring: the aircraft's route and the weapon's
    #: flight, without what needing the weapon adds.
    cost: float
    #: The miles actually flown, from the base to the release point.
    length: float
    #: Where it starts; None when there is nowhere to start from.
    base: Any
    release: Release
    #: What each ring along the route or the weapon's flight adds to its cost, the
    #: worst first.
    rings: tuple[tuple[float, Ring], ...]
    #: The route's points, from the base to the release point, as (x, y).
    path: tuple[tuple[float, float], ...] = ()


class Approach:
    """The cheapest route from our bases to every point of the theater."""

    def __init__(
        self,
        rings: Sequence[Ring],
        bases: Sequence[tuple[Any, Point]],
        points: Sequence[Point],
        cell: float = CELL.meters,
    ) -> None:
        self.rings = list(rings)
        self.cell = cell
        where = [p for _, p in bases] + list(points)
        margin = MARGIN.meters
        self.x0 = min(p.x for p in where) - margin
        self.y0 = min(p.y for p in where) - margin
        nx = int((max(p.x for p in where) + margin - self.x0) / cell) + 1
        ny = int((max(p.y for p in where) + margin - self.y0) / cell) + 1
        self.shape = (nx, ny)
        self.xs, self.ys = np.meshgrid(
            self.x0 + np.arange(nx) * cell,
            self.y0 + np.arange(ny) * cell,
            indexing="ij",
        )
        threat = np.zeros(self.shape)
        for ring in self.rings:
            distance = np.hypot(self.xs - ring.x, self.ys - ring.y)
            threat += ring.weight * np.clip(
                (ring.reach - distance) / ring.reach, 0, None
            )
        self.per_mile = 1.0 + RING_COST * threat
        self.release_cells = (np.arange(nx)[:, None] % RELEASE_STRIDE == 0) & (
            np.arange(ny)[None, :] % RELEASE_STRIDE == 0
        )

        self.sources: dict[int, Any] = {}
        for base, position in bases:
            self.sources.setdefault(self._index(position), base)
        self.cost, self.came_from = self._cheapest()

    def _index(self, position: Point) -> int:
        nx, ny = self.shape
        i = min(nx - 1, max(0, round((position.x - self.x0) / self.cell)))
        j = min(ny - 1, max(0, round((position.y - self.y0) / self.cell)))
        return i * ny + j

    def _cheapest(self) -> tuple[npt.NDArray[np.float64], list[int]]:
        """Dijkstra over the grid, from every base at once."""
        nx, ny = self.shape
        per_mile = self.per_mile.ravel().tolist()
        miles = self.cell / nautical_miles(1).meters
        cost = [math.inf] * (nx * ny)
        came_from = [-1] * (nx * ny)
        frontier = [(0.0, index) for index in self.sources]
        for _, index in frontier:
            cost[index] = 0.0
        heapq.heapify(frontier)
        steps = [
            (di, dj, miles * math.hypot(di, dj))
            for di in (-1, 0, 1)
            for dj in (-1, 0, 1)
            if di or dj
        ]
        while frontier:
            here_cost, here = heapq.heappop(frontier)
            if here_cost > cost[here]:
                continue
            i, j = divmod(here, ny)
            here_per_mile = per_mile[here]
            for di, dj, length in steps:
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny):
                    continue
                there = ni * ny + nj
                there_cost = here_cost + length * (here_per_mile + per_mile[there]) / 2
                if there_cost < cost[there]:
                    cost[there] = there_cost
                    came_from[there] = here
                    heapq.heappush(frontier, (there_cost, there))
        return np.array(cost).reshape(self.shape), came_from

    def route(self, target: Point, releases: Sequence[Release]) -> Route:
        """The cheapest release on the objective, of the ones our weapons allow."""
        distance = np.hypot(self.xs - target.x, self.ys - target.y)
        rings = self.rings
        best: Optional[tuple[float, int, Release]] = None
        for release in releases:
            inside = (distance <= release.radius) & self.release_cells
            cells = np.flatnonzero(inside)
            if cells.size == 0:
                cells = np.array([int(np.argmin(distance))])
            totals = (
                self.cost.flat[cells]
                + self._flight_cost(cells, target, rings)
                + release.penalty
            )
            pick = int(np.argmin(totals))
            if best is None or float(totals[pick]) < best[0]:
                best = (float(totals[pick]), int(cells[pick]), release)
        assert best is not None
        _, index, release = best
        return self._route_to(index, release, target, rings)

    def _flight_cost(
        self, cells: npt.NDArray[np.int64], target: Point, rings: Sequence[Ring]
    ) -> npt.NDArray[np.float64]:
        """What a weapon's flight from each of these cells to the target costs."""
        return WEAPON_RING_COST * self._flight_exposure(cells, target, rings).sum(
            axis=0
        )

    def _flight_exposure(
        self, cells: npt.NDArray[np.int64], target: Point, rings: Sequence[Ring]
    ) -> npt.NDArray[np.float64]:
        """Each ring's weight along a weapon's flight from each cell, in miles of ring
        weight: one row per ring, one column per cell."""
        x = self.xs.flat[cells][:, None]
        y = self.ys.flat[cells][:, None]
        along = np.linspace(0.0, 1.0, WEAPON_SAMPLES)[None, :]
        xs = x + (target.x - x) * along
        ys = y + (target.y - y) * along
        miles = (
            np.hypot(target.x - x[:, 0], target.y - y[:, 0]) / nautical_miles(1).meters
        )
        exposure = np.zeros((len(rings), cells.size))
        for n, ring in enumerate(rings):
            weight = ring.weight * np.clip(
                (ring.reach - np.hypot(xs - ring.x, ys - ring.y)) / ring.reach, 0, None
            )
            exposure[n] = weight.mean(axis=1) * miles
        return exposure

    def _route_to(
        self, index: int, release: Release, target: Point, rings: Sequence[Ring]
    ) -> Route:
        path = [index]
        while self.came_from[path[-1]] >= 0:
            path.append(self.came_from[path[-1]])
        cells = [divmod(cell, self.shape[1]) for cell in path]
        xs = [float(self.xs[i, j]) for i, j in cells]
        ys = [float(self.ys[i, j]) for i, j in cells]
        length = (
            sum(
                math.hypot(xs[n + 1] - xs[n], ys[n + 1] - ys[n])
                for n in range(len(xs) - 1)
            )
            / nautical_miles(1).meters
        )
        miles = self.cell / nautical_miles(1).meters
        flight = self._flight_exposure(np.array([index]), target, rings)[:, 0]
        in_flight = {id(ring): float(weight) for ring, weight in zip(rings, flight)}
        exposure = [
            (
                RING_COST * sum(ring.weight_at(x, y) for x, y in zip(xs, ys)) * miles
                + WEAPON_RING_COST * in_flight.get(id(ring), 0.0),
                ring,
            )
            for ring in self.rings
        ]
        return Route(
            cost=float(self.cost.flat[index]) + WEAPON_RING_COST * float(flight.sum()),
            length=length,
            base=self.sources.get(path[-1]),
            release=release,
            rings=tuple(
                sorted(
                    ((weight, ring) for weight, ring in exposure if weight > 0),
                    key=lambda pair: -pair[0],
                )
            ),
            path=tuple(zip(reversed(xs), reversed(ys))),
        )
