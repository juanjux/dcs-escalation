import { Waypoint } from "../../api/liberationApi";
import { iconFor, tintFor } from "./WaypointMarker";

function waypoint(pin: string, isTarget = false): Waypoint {
  return {
    name: "WP",
    position: { lat: 0, lng: 0 },
    altitude_ft: 0,
    altitude_reference: "BARO",
    is_movable: true,
    should_mark: true,
    include_in_path: true,
    timing: "",
    index: 1,
    can_delete: true,
    speed_kts: 0,
    is_target: isTarget,
    shows_altitude: true,
    pin: pin,
  };
}

describe("tintFor", () => {
  it("colours each pin by what the waypoint is for", () => {
    expect(tintFor(waypoint("track"))).toBe("red");
    expect(tintFor(waypoint("ingress"))).toBe("red");
    expect(tintFor(waypoint("refuel"))).toBe("green");
    expect(tintFor(waypoint("hold"))).toBe("orange");
  });

  it("keeps the rest blue, and every target red", () => {
    expect(tintFor(waypoint(""))).toBeNull();
    expect(tintFor(waypoint("", true))).toBe("red");
  });
});

describe("iconFor", () => {
  it("gives the pin its colour and, when selected, its glow", () => {
    expect(iconFor(waypoint("hold"), true).options.className).toBe(
      "wp-pin wp-pin-orange wp-pin-selected",
    );
    expect(iconFor(waypoint(""), false).options.className).toBe("wp-pin");
  });

  it("makes each icon once", () => {
    expect(iconFor(waypoint("refuel"), false)).toBe(
      iconFor(waypoint("refuel"), false),
    );
  });
});
