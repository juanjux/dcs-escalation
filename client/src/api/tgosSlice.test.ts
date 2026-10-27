import reducer, { deleteTgo, updateTgo } from "./tgosSlice";
import { Tgo } from "./liberationApi";

it("removes absorbed reserve markers without removing other objectives", () => {
  const reserve = { id: "reserve" } as Tgo;
  const sam = { id: "sam" } as Tgo;
  const initial = reducer(undefined, updateTgo([reserve, sam]));
  const next = reducer(initial, deleteTgo(["reserve"]));
  expect(next.tgos).toEqual({ sam });
  expect(initial.tgos).toEqual({ reserve, sam });
});

it("repeating deletion of an absorbed marker is harmless", () => {
  const reserve = { id: "reserve" } as Tgo;
  const initial = reducer(undefined, updateTgo([reserve]));
  const deleted = reducer(initial, deleteTgo(["reserve"]));
  expect(reducer(deleted, deleteTgo(["reserve", "unknown"])).tgos).toEqual({});
});
