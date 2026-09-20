// The control hangs off a popup on the map, so whatever the server says back it has
// to stay quiet rather than throw inside a render. It did throw: the picker's own
// tests answer every fetch with the coordinates of the clicked point, this asked for
// a list of aircraft and got that object, and `receivers.find` took the whole popup
// down with it.
import SavePoint, { insteadOf } from "./SavePoint";
import { render, screen, waitFor } from "@testing-library/react";
import { LatLng } from "leaflet";

function answerWith(body: unknown, ok = true) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: ok,
    json: async () => body,
  }) as unknown as typeof fetch;
}

const AT = new LatLng(36.5886, -115.6736);

describe("saving a point to an aircraft", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it("offers the aircraft the server lists", async () => {
    answerWith([
      {
        id: "1",
        callsign: "SEAD",
        aircraft: "AV-8B",
        departure: "Mount Pleasant",
        kinds: ["waypoint"],
        room: { waypoint: 3 },
      },
    ]);

    render(<SavePoint at={AT} name="N36 W115" />);

    expect(await screen.findByText(/Save as waypoint/)).toBeInTheDocument();
    // A flight with no name of its own is called after its task, never "None".
    expect(screen.getByRole("option").textContent).toMatch(/^SEAD/);
  });

  it("says so when nobody is flying anything", async () => {
    answerWith([]);

    render(<SavePoint at={AT} name="N36 W115" />);

    expect(await screen.findByText(/No player aircraft/)).toBeInTheDocument();
  });

  it("stays quiet when the answer is not a list of aircraft", async () => {
    // What the picker's own tests answer with, and what an error page would be.
    answerWith({ text: "N36 W115", all: {} });

    render(<SavePoint at={AT} name="N36 W115" />);

    await waitFor(() => {
      expect(screen.queryByText(/Save as/)).not.toBeInTheDocument();
    });
  });

  it("stays quiet when the server refuses", async () => {
    answerWith({ detail: "no" }, false);

    render(<SavePoint at={AT} name="N36 W115" />);

    await waitFor(() => {
      expect(screen.queryByText(/Save as/)).not.toBeInTheDocument();
    });
  });
});

// ------------------- the kind the aircraft cannot actually be given

function receiver(into: Record<string, boolean>): any {
  return {
    id: "1",
    callsign: "TARSIER",
    aircraft: "F/A-18C Hornet",
    departure: "Nellis",
    kinds: ["waypoint", "markpoint"],
    room: { waypoint: 57, markpoint: 50 },
    into_aircraft: into,
  };
}

it("offers a waypoint in place of a markpoint the aircraft cannot take", () => {
  const hornet = receiver({ waypoint: true, markpoint: false });
  expect(insteadOf(hornet, "markpoint")).toBe("waypoint");
});

it("asks nothing about a kind the aircraft does take", () => {
  const hog = receiver({ waypoint: true, markpoint: true });
  expect(insteadOf(hog, "markpoint")).toBeUndefined();
  expect(insteadOf(hog, "waypoint")).toBeUndefined();
});

it("asks nothing when neither kind reaches the aircraft", () => {
  const unmeasured = receiver({ waypoint: false, markpoint: false });
  expect(insteadOf(unmeasured, "markpoint")).toBeUndefined();
});

it("asks nothing when an older server never said", () => {
  const older = receiver(undefined as any);
  expect(insteadOf(older, "markpoint")).toBeUndefined();
});
