import { windLabel } from "./WindLayer";

describe("windLabel", () => {
  it("says where the wind comes from, as pilots read it", () => {
    // DCS keeps where it blows to: 308 means from 128.
    expect(windLabel({ altitude_m: 0, blows_to: 308, speed_mps: 11.7 })).toBe(
      "SFC from 128° 23 kt"
    );
    expect(windLabel({ altitude_m: 8000, blows_to: 9, speed_mps: 39.1 })).toBe(
      "8000 m from 189° 76 kt"
    );
  });

  it("calls a still level calm", () => {
    expect(windLabel({ altitude_m: 0, blows_to: 215, speed_mps: 0 })).toBe(
      "SFC calm"
    );
  });
});
