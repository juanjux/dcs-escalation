/**
 * A factory, a warehouse and a fuel depot are three different things on the map.
 *
 * APP-6(D) letters all three STOR and draws them the same, which hides the one
 * distinction worth having: a base recruits ground units only while it has a factory.
 */
import { Tgo as TgoModel } from "../../api/liberationApi";
import { iconForTgo, isStore } from "./shared";

// The store symbol: land installations, warehouse/storage facility (112000).
const STORE_SIDC = "10032020001120000000";

function store(category: string, sidc: string = STORE_SIDC): TgoModel {
  return {
    id: "id",
    name: "SILKWORM",
    control_point_name: "Creech",
    category,
    blue: true,
    position: { lat: 0, lng: 0 },
    units: [],
    threat_ranges: [],
    detection_ranges: [],
    dead: false,
    purchasable: true,
    repairing: false,
    sidc,
    task: [],
    mobile: false,
  } as unknown as TgoModel;
}

function svgFor(tgo: TgoModel): string {
  const url = iconForTgo(tgo).options.iconUrl ?? "";
  return decodeURIComponent(url.slice(url.indexOf(",") + 1));
}

describe("the three kinds of store", () => {
  it("letters a factory FTRY and keeps the shed with chimneys", () => {
    const svg = svgFor(store("factory"));
    expect(svg).toContain(">FTRY</text>");
    expect(svg).not.toContain(">STOR</text>");
    // The stock shape, drawn larger: two chimneys over a shed.
    expect(svg).toContain("M105,70 H111 V86 H122 V70 H128 V86 H136 V130 H64");
    expect(svg).not.toContain("m 104,75");
  });

  it("draws the letters large enough to read on the map", () => {
    // milsymbol sizes them for the stock four letters and leaves the frame half
    // empty; these are four letters too, with the same room to fill.
    expect(svgFor(store("ware"))).toContain('font-size="28"');
  });

  it("letters a warehouse WARE and draws it a crate", () => {
    const svg = svgFor(store("ware"));
    expect(svg).toContain(">WARE</text>");
    expect(svg).toContain("M64,78 h72 v52 h-72 z");
    expect(svg).not.toContain("m 104,75");
  });

  it("letters a fuel depot FUEL and draws it a drum", () => {
    const svg = svgFor(store("fuel"));
    expect(svg).toContain(">FUEL</text>");
    expect(svg).toContain("a27,10 0 0,1 54,0");
    expect(svg).not.toContain("m 104,75");
  });

  it("leaves every other building alone", () => {
    expect(isStore(store("ammo"))).toBe(false);
    expect(isStore(store("power"))).toBe(false);
    // An ammo cache has no STOR letters to swap in the first place.
    expect(svgFor(store("ammo", "10032020001103000000"))).not.toContain("FTRY");
  });

  it("keeps the health bar it was given", () => {
    // Destroyed: status digit 4, milsymbol's red bar. The swap must not touch it.
    const dead = store("ware", "10032040001120000000");
    expect(svgFor(dead)).toContain("rgb(255,0,0)");
  });
});
