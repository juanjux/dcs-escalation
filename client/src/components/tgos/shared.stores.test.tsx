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
  it("letters a factory FTRY and leaves it the shed with chimneys", () => {
    const svg = svgFor(store("factory"));
    expect(svg).toContain(">FTRY</text>");
    expect(svg).not.toContain(">STOR</text>");
    // The stock icon: the chimneys are already the right picture for a factory.
    expect(svg).toContain("m 104,75");
  });

  it("letters a warehouse WARE and draws it a crate", () => {
    const svg = svgFor(store("ware"));
    expect(svg).toContain(">WARE</text>");
    expect(svg).toContain("M74,80 h52 v44 h-52 z");
    expect(svg).not.toContain("m 104,75");
  });

  it("letters a fuel depot FUEL and draws it a drum", () => {
    const svg = svgFor(store("fuel"));
    expect(svg).toContain(">FUEL</text>");
    expect(svg).toContain("a20,9 0 0,1 40,0");
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
