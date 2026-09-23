"""The High Command's orders on the map: one mark for each point an order is about."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dcs import Point
from pydantic import BaseModel

from game.highcommand.orders import Order, tier_name
from game.server.leaflet import LeafletPoint

if TYPE_CHECKING:
    from game import Game


class HighCommandMarkJs(BaseModel):
    name: str
    position: LeafletPoint
    #: How many open orders are about this point: a base can be asked for its
    #: aircraft and its runway at once.
    orders: int
    #: The fewest turns left among those orders.
    soonest: int
    last_turn: bool
    tooltip: str

    class Config:
        title = "HighCommandMark"

    @staticmethod
    def all_in_game(game: Game) -> list[HighCommandMarkJs]:
        if not game.settings.high_command_enabled:
            return []
        points: dict[str, list[Order]] = {}
        where: dict[str, Point] = {}
        for order in game.high_command.orders:
            position = _position(game, order)
            if position is None:
                continue
            name = order.base if order.task is not None else order.objective
            points.setdefault(name, []).append(order)
            where[name] = position
        count = game.settings.high_command_orders
        marks = []
        for name, orders in points.items():
            soonest = min(order.turns_left(game.turn) for order in orders)
            marks.append(
                HighCommandMarkJs(
                    name=name,
                    position=LeafletPoint.from_latlng(where[name].latlng()),
                    orders=len(orders),
                    soonest=soonest,
                    last_turn=soonest <= 1,
                    tooltip=_tooltip(orders, count, game.turn),
                )
            )
        return marks


def _position(game: Game, order: Order) -> Optional[Point]:
    if order.task is not None:
        base = next(
            (cp for cp in game.theater.controlpoints if cp.name == order.base), None
        )
        return base.position if base is not None else None
    tgo = next(
        (tgo for tgo in game.theater.ground_objects if tgo.name == order.objective),
        None,
    )
    return tgo.position if tgo is not None else None


def _tooltip(orders: list[Order], count: int, turn: int) -> str:
    if len(orders) == 1:
        order = orders[0]
        prize = f" · {order.prize.line}" if order.prize is not None else ""
        return f"High Command order · {tier_name(order.tier, count)} tier{prize}"
    asked = "; ".join(
        f"{order.task.value if order.task else order.objective}:"
        f" {order.turns_left(turn)} turns left"
        for order in orders
    )
    return f"{len(orders)} High Command orders · {asked}"
