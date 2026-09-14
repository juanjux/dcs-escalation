import { Tgo as TgoModel } from "../../api/liberationApi";
import { iadsBarColor, iconForTgo, isJammer, isRepairing } from "./shared";

// APP-6(D) SIDC with the status/condition digit (index 6) parameterised.
function sidc(status: string): string {
  return "100310" + status + "0001301000000";
}

function fakeTgo(dead: boolean, status: string, repairing: boolean): TgoModel {
  return {
    id: "id",
    name: "SAM",
    control_point_name: "CP",
    category: "aa",
    blue: true,
    position: { lat: 0, lng: 0 },
    units: [],
    threat_ranges: [],
    detection_ranges: [],
    dead,
    purchasable: true,
    repairing,
    sidc: sidc(status),
    task: [],
    mobile: false,
  } as unknown as TgoModel;
}

describe("isRepairing", () => {
  it("is true whenever repairs are pending and the bar is 'damaged'", () => {
    expect(isRepairing(fakeTgo(true, "3", true))).toBe(true); // fully dead + repairing
    expect(isRepairing(fakeTgo(false, "3", true))).toBe(true); // partial damage + repairing
    expect(isRepairing(fakeTgo(false, "3", false))).toBe(false); // damaged, not repairing (yellow)
    expect(isRepairing(fakeTgo(true, "4", false))).toBe(false); // dead, unrepaired (red)
    expect(isRepairing(fakeTgo(false, "2", false))).toBe(false); // fully capable (green)
  });
});

describe("iconForTgo health-bar colour", () => {
  it("recolours the yellow damaged bar to orange for a fully-dead repairing group", () => {
    const url = iconForTgo(fakeTgo(true, "3", true)).options.iconUrl ?? "";
    const svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    expect(svg).toContain("rgb(255,140,0)"); // orange bar
    expect(svg).not.toContain("rgb(255,255,0)"); // no leftover yellow
  });

  it("recolours to orange for a PARTIALLY damaged repairing group too", () => {
    const url = iconForTgo(fakeTgo(false, "3", true)).options.iconUrl ?? "";
    const svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    expect(svg).toContain("rgb(255,140,0)");
    expect(svg).not.toContain("rgb(255,255,0)");
  });

  it("keeps the yellow bar for damage with no repairs pending", () => {
    const url = iconForTgo(fakeTgo(false, "3", false)).options.iconUrl ?? "";
    // No repairs pending: milsymbol's default icon, not recoloured.
    const svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    expect(svg).toContain("rgb(255,255,0)"); // still yellow
    expect(svg).not.toContain("rgb(255,140,0)");
  });
});

// The health bar is the one thing on the map that says how well a site is working, so
// what the IADS will do with it goes there -- and nowhere else: the range rings are left
// in their own colours, because a recoloured or dashed ring reads as a jamming bubble.
describe("iadsBarColor", () => {
  const withState = (status: string, state: string | null) =>
    ({ ...fakeTgo(false, status, false), iads_state: state }) as TgoModel;

  it("greys the bar of a site with no power", () => {
    expect(iadsBarColor(withState("2", "dark"))).toBe("rgb(130,140,150)");
  });

  it("paints a site cut off from its network violet", () => {
    expect(iadsBarColor(withState("2", "autonomous"))).toBe("rgb(178,120,255)");
  });

  it("leaves a working site alone", () => {
    expect(iadsBarColor(withState("2", "networked"))).toBeNull();
    expect(iadsBarColor(withState("2", null))).toBeNull();
  });

  it("leaves a destroyed site red", () => {
    // It is dark, of course it is -- but "destroyed" is the more useful of the two
    // things to be told, and the red bar is the only place the map says it.
    expect(iadsBarColor(withState("4", "dark"))).toBeNull();
  });

  it("wins over the repair orange", () => {
    const tgo = {
      ...fakeTgo(false, "3", true),
      iads_state: "dark",
    } as TgoModel;
    const url = iconForTgo(tgo).options.iconUrl ?? "";
    const svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    expect(svg).toContain("rgb(130,140,150)");
    expect(svg).not.toContain("rgb(255,140,0)");
  });

  it("paints the bar of an intact autonomous site", () => {
    const tgo = {
      ...fakeTgo(false, "2", false),
      iads_state: "autonomous",
    } as TgoModel;
    const url = iconForTgo(tgo).options.iconUrl ?? "";
    const svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    expect(svg).toContain("rgb(178,120,255)");
    expect(svg).not.toContain("rgb(0,255,0)");
  });
});

// The standard symbol for these letters "EW", which is true but not the useful half:
// what they jam is GPS, and nothing else on the map does.
describe("isJammer", () => {
  const jammer = {
    ...fakeTgo(false, "0", false),
    sidc: "10061020001505040000",
  } as TgoModel;

  it("recognises the jamming entity", () => {
    expect(isJammer(jammer)).toBe(true);
    expect(isJammer(fakeTgo(false, "0", false))).toBe(false);
  });

  it("labels the icon GPS", () => {
    const svg = decodeURIComponent(
      iconForTgo(jammer).options.iconUrl!.split(",").slice(1).join(","),
    );
    expect(svg).toContain(">GPS</text>");
    expect(svg).not.toContain(">EW</text>");
  });
});
