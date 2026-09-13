import { renderWithProviders } from "../../testutils";
import MapSearch from "./MapSearch";
import { fireEvent, screen } from "@testing-library/react";

// The control mounts itself into a Leaflet control corner. Neither of those exists
// here, so the corner becomes a div on the body and the portal renders into that --
// which is all the queries below need.
// One stable object: a fresh one per render would change the effect's dependency and
// re-mount the control for ever.
const mockMap = {};
jest.mock("react-leaflet", () => ({
  useMap: () => mockMap,
}));

jest.mock("leaflet", () => {
  class FakeControl {
    onAdd: (() => HTMLElement) | undefined;
    addTo() {
      return this;
    }
    remove() {}
  }
  const fake = {
    Control: FakeControl,
    DomUtil: {
      create: (tag: string) => {
        // `document` cannot be named inside a jest.mock factory, and global is the
        // same object here.
        const doc = (global as any).document;
        const el = doc.createElement(tag);
        doc.body.appendChild(el);
        return el;
      },
    },
    DomEvent: {
      disableClickPropagation: () => {},
      disableScrollPropagation: () => {},
    },
  };
  return { __esModule: true, default: fake, ...fake };
});

const tgo = (
  id: string,
  name: string,
  category: string,
  units: string[],
  blue = false,
  dead = false,
) => ({
  id,
  name,
  control_point_name: "Somewhere",
  category,
  blue,
  position: { lat: 1, lng: 2 },
  units,
  threat_ranges: [],
  detection_ranges: [],
  dead,
  purchasable: true,
  sidc: "10061030001301000000",
  task: [],
  mobile: false,
});

const state = {
  tgos: {
    tgos: {
      mink: tgo("mink", "MINK", "aa", ["SAM Patriot STR", "SAM Patriot LN"]),
      hare: tgo("hare", "HARE", "aa", ["M6 Linebacker"]),
      sunbear: tgo("sunbear", "SUNBEAR", "commandcenter", ["Command Center"]),
      wreck: tgo("wreck", "AARDVARK", "aa", ["SAM Patriot LN"], false, true),
      ours: tgo("ours", "BADGER", "aa", ["SAM Patriot LN"], true),
      silkworm: tgo("silkworm", "SILKWORM", "factory", ["Workshop A"], true),
      arapaima: tgo("arapaima", "ARAPAIMA", "ware", ["Warehouse"]),
      lobster: tgo("lobster", "LOBSTER", "fuel", ["Fuel tank"]),
    },
  },
  controlPoints: {
    controlPoints: {
      creech: {
        id: "creech",
        name: "Creech AFB",
        blue: true,
        position: { lat: 3, lng: 4 },
        mobile: false,
        sidc: "",
        units: [],
        threat_ranges: [],
        detection_ranges: [],
      },
    },
  },
};

function open() {
  renderWithProviders(<MapSearch />, { preloadedState: state as any });
  fireEvent.click(screen.getByTitle("Find a place on the map"));
}

function names(): string[] {
  return screen
    .getAllByRole("button")
    .map((button) => button.querySelector(".ms-name")?.textContent)
    .filter((text): text is string => Boolean(text));
}

function type(text: string) {
  fireEvent.change(
    screen.getByPlaceholderText("Find a place, or what is parked there…"),
    { target: { value: text } },
  );
}

describe("MapSearch", () => {
  it("lists everything on the map before anything is typed", () => {
    open();
    expect(names()).toEqual(
      expect.arrayContaining(["MINK", "HARE", "SUNBEAR", "Creech AFB"]),
    );
  });

  it("finds a site by its code name", () => {
    open();
    type("mink");
    expect(names()).toEqual(["MINK"]);
  });

  // The half of this that matters: a log or the OPFOR planner names the system, not
  // the code name, and "which of these two hundred is the Patriot" was the question.
  it("finds a site by what is parked there", () => {
    open();
    type("linebacker");
    expect(names()).toEqual(["HARE"]);
  });

  it("says which unit put a site in the list", () => {
    open();
    type("patriot");
    expect(screen.getAllByText("SAM Patriot STR").length).toBe(1);
  });

  it("finds a site by what kind of thing it is", () => {
    open();
    type("command");
    expect(names()).toEqual(["SUNBEAR"]);
  });

  it("filters to one side", () => {
    open();
    type("patriot");
    fireEvent.click(screen.getByText("Enemy"));
    expect(names()).not.toContain("BADGER");
    expect(names()).toContain("MINK");
  });

  it("filters to one kind", () => {
    open();
    fireEvent.click(screen.getByText("Bases"));
    expect(names()).toEqual(["Creech AFB"]);
  });

  it("tells the three kinds of stores apart", () => {
    // A factory is what lets a base recruit ground units, so finding one is worth a
    // chip of its own rather than a rummage through every building on the map.
    open();
    fireEvent.click(screen.getByText("Factories"));
    expect(names()).toEqual(["SILKWORM"]);

    fireEvent.click(screen.getByText("Factories"));
    fireEvent.click(screen.getByText("Warehouses"));
    expect(names()).toEqual(["ARAPAIMA"]);

    fireEvent.click(screen.getByText("Warehouses"));
    fireEvent.click(screen.getByText("Fuel depots"));
    expect(names()).toEqual(["LOBSTER"]);
  });

  it("puts the wrecks last", () => {
    open();
    type("patriot");
    expect(names()[names().length - 1]).toBe("AARDVARK");
  });

  it("says so when nothing matches", () => {
    open();
    type("zzzz");
    expect(screen.getByText("Nothing on the map matches that.")).toBeTruthy();
  });
});
