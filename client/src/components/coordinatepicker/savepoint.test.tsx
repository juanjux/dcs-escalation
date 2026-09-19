// The control hangs off a popup on the map, so whatever the server says back it has
// to stay quiet rather than throw inside a render. It did throw: the picker's own
// tests answer every fetch with the coordinates of the clicked point, this asked for
// a list of aircraft and got that object, and `receivers.find` took the whole popup
// down with it.
import SavePoint from "./SavePoint";
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
        callsign: "TARSIER",
        aircraft: "AV-8B",
        kinds: ["waypoint"],
        room: { waypoint: 3 },
      },
    ]);

    render(<SavePoint at={AT} name="N36 W115" />);

    expect(await screen.findByText(/Save as waypoint/)).toBeInTheDocument();
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
