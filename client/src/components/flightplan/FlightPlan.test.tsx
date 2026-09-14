import { Waypoint } from "../../api/liberationApi";
import { legUnderPointer } from "./FlightPlan";
import { LeafletMouseEvent } from "leaflet";

// Only the projection is used, and a flat one keeps the arithmetic readable: x is
// longitude, y is latitude, so the points below are the picture they look like.
const map = {
  latLngToLayerPoint: ({ lat, lng }: { lat: number; lng: number }) => ({
    x: lng,
    y: lat,
  }),
} as any;

function waypoint(index: number, lat: number, lng: number): Waypoint {
  return {
    name: `WP${index}`,
    position: { lat: lat, lng: lng },
    altitude_ft: 0,
    altitude_reference: "MSL",
    is_movable: true,
    should_mark: true,
    include_in_path: true,
    timing: "",
    index: index,
    can_delete: true,
    speed_kts: 0,
    is_target: false,
    shows_altitude: true,
  };
}

function clickAt(lat: number, lng: number): LeafletMouseEvent {
  return { latlng: { lat: lat, lng: lng } } as any;
}

describe("legUnderPointer", () => {
  it("puts a new point into the leg the pointer is over", () => {
    // 0 -- 1 -- 2 along the equator; the pointer sits between 1 and 2.
    const drawn = [waypoint(0, 0, 0), waypoint(1, 0, 10), waypoint(2, 0, 20)];
    expect(legUnderPointer(map, drawn, clickAt(0, 15))).toEqual(1);
  });

  it("puts it after the waypoints the leg hides, not before them", () => {
    // An ingress at index 3 and a split at index 6, with two targets between them
    // that are not drawn. Alt-clicking the line you can see should bend the run out
    // of the target and into the split, which means going in at 5 -- after the last
    // target -- rather than at 3, which would put a nav point in front of the run.
    const ingress = waypoint(3, 0, 0);
    const split = { ...waypoint(6, 0, 30), index: 6 };
    expect(legUnderPointer(map, [ingress, split], clickAt(0, 15))).toEqual(5);
  });

  it("has nowhere to put one on a route with a single point", () => {
    expect(legUnderPointer(map, [waypoint(0, 0, 0)], clickAt(0, 5))).toBeNull();
  });

  it("has nowhere to put one on an empty route", () => {
    expect(legUnderPointer(map, [], clickAt(0, 5))).toBeNull();
  });

  it("measures to the nearest leg, not the nearest waypoint", () => {
    // The pointer is closest to waypoint 0, but it is sitting on the leg from 1 to 2.
    const drawn = [waypoint(0, 0, 0), waypoint(1, 20, 0), waypoint(2, 20, 20)];
    expect(legUnderPointer(map, drawn, clickAt(20, 10))).toEqual(1);
  });
});
