from fastapi import APIRouter, Depends

from game import Game
from game.server import GameContext
from .models import GameJs, MapLayersJs, WindLevelJs

router: APIRouter = APIRouter(prefix="/game")


@router.get("/", operation_id="get_game_state", response_model=GameJs)
def game_state(game: Game | None = Depends(GameContext.get)) -> GameJs | None:
    if game is None:
        return None
    return GameJs.from_game(game)


@router.get("/wind", operation_id="get_wind", response_model=list[WindLevelJs])
def get_wind(game: Game | None = Depends(GameContext.get)) -> list[WindLevelJs]:
    if game is None:
        return []
    return WindLevelJs.for_game(game)


@router.get("/map-layers", operation_id="get_map_layers", response_model=MapLayersJs)
def get_map_layers(game: Game | None = Depends(GameContext.get)) -> MapLayersJs:
    if game is None:
        return MapLayersJs()
    return MapLayersJs(state=getattr(game, "client_map_layers", None))


@router.put("/map-layers", operation_id="set_map_layers", response_model=MapLayersJs)
def set_map_layers(
    payload: MapLayersJs, game: Game | None = Depends(GameContext.get)
) -> MapLayersJs:
    if game is not None:
        game.client_map_layers = payload.state
    return payload
