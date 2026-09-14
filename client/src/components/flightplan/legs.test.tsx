import { Waypoint } from "../../api/liberationApi";
import { tooltipFor } from "../waypointmarker/WaypointMarker";
import { distanceNm, labelOffset, legLabel } from "./legs";

function waypoint(over: Partial<Waypoint> = {}): Waypoint {
  return {
    name: "NAV",
    position: { lat: 0, lng: 0 },
    altitude_ft: 20000,
    altitude_reference: "BARO",
    is_movable: true,
    should_mark: true,
    include_in_path: true,
    timing: "TOT 06:26:02",
    index: 3,
    can_delete: true,
    speed_kts: 350,
    is_target: false,
    shows_altitude: true,
    ...over,
  };
}

describe("leg distances", () => {
  it("measures a leg in nautical miles", () => {
    // One degree of latitude is 60 NM by definition.
    const nm = distanceNm({ lat: 0, lng: 0 }, { lat: 1, lng: 0 });
    expect(nm).toBeGreaterThan(59.5);
    expect(nm).toBeLessThan(60.5);
  });

  it("keeps a tenth of a mile on a short run and drops it on a long one", () => {
    expect(legLabel(4.26)).toBe("4.3 NM");
    expect(legLabel(43.6)).toBe("44 NM");
  });

  it("steps sideways off a steep leg and upwards off a shallow one", () => {
    expect(labelOffset(2, 40)).toEqual([13, 0]);
    expect(labelOffset(40, 2)).toEqual([0, -13]);
  });

  it("treats a leg at exactly 45 degrees as shallow rather than crashing", () => {
    expect(labelOffset(30, 30)).toEqual([0, -13]);
  });
});

describe("waypoint tooltips", () => {
  it("gives the number, the name, the altitude and the timing", () => {
    expect(tooltipFor(waypoint(), 4)).toBe(
      "3 NAV<br />20000 ft BARO<br />TOT 06:26:02",
    );
  });

  it("leaves out an altitude that is the ground rather than a height flown at", () => {
    const target = waypoint({
      name: "STRIKE Static Tech combine-2-8 #7",
      altitude_ft: 0,
      altitude_reference: "RADIO",
      is_target: true,
      shows_altitude: false,
    });
    expect(tooltipFor(target, 12)).toBe(
      "11 STRIKE Static Tech combine-2-8 #7<br />TOT 06:26:02",
    );
  });

  it("leaves out timing there is none of", () => {
    expect(tooltipFor(waypoint({ timing: "" }), 1)).toBe(
      "0 NAV<br />20000 ft BARO",
    );
  });
});
