import { handleStreamedEvents } from "./eventstream";

jest.mock("./gamestate", () => ({ __esModule: true, default: jest.fn() }));

const emptyEvents = {
  updated_flight_positions: {},
  new_combats: [],
  updated_combats: [],
  ended_combats: [],
  navmesh_updates: [],
  updated_unculled_zones: [],
  threat_zones_updated: [],
  new_flights: [],
  updated_flights: [],
  deleted_flights: [],
  selected_flight: null,
  deselected_flight: false,
  updated_front_lines: [],
  deleted_front_lines: [],
  updated_tgos: [],
  updated_control_points: [],
  updated_iads: [],
  deleted_iads: [],
  updated_supply_routes: [],
  reset_on_map_center: null,
  fly_to: null,
  fly_to_zoom: null,
  game_unloaded: false,
  new_turn: false,
};

it.each([
  { saved_points_updated: true },
  { deleted_flights: ["flight-1"] },
  { new_turn: true },
  { game_unloaded: true },
])("notifies map pins about relevant streamed changes: %j", (changes) => {
  const listener = jest.fn();
  window.addEventListener("saved-points-changed", listener);
  handleStreamedEvents(jest.fn(), { ...emptyEvents, ...changes });
  expect(listener).toHaveBeenCalledTimes(1);
  expect(listener.mock.calls[0][0].detail).toEqual({
    unloaded: "game_unloaded" in changes,
    reset: "new_turn" in changes,
  });
  window.removeEventListener("saved-points-changed", listener);
});

it("does not refresh pins on unrelated simulation updates", () => {
  const listener = jest.fn();
  window.addEventListener("saved-points-changed", listener);
  handleStreamedEvents(jest.fn(), emptyEvents);
  expect(listener).not.toHaveBeenCalled();
  window.removeEventListener("saved-points-changed", listener);
});
