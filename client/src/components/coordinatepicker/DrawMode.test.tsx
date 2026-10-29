import { DrawPanel } from "./DrawMode";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LatLng } from "leaflet";

jest.mock("react-leaflet", () => ({
  useMap: jest.fn(),
  useMapEvent: jest.fn(),
}));

const receivers = [
  { id: "flight", callsign: "Hawg", aircraft: "A-10C", departure: "Base" },
];
const response = (body: unknown, ok = true) => ({ ok, json: async () => body });
beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue(response(receivers));
});

it("saves a line with map vertices and announces the shared change", async () => {
  const close = jest.fn();
  const changed = jest.fn();
  window.addEventListener("saved-points-changed", changed);
  render(
    <DrawPanel
      points={[new LatLng(42, 42), new LatLng(43, 43)]}
      undo={jest.fn()}
      close={close}
    />,
  );
  await screen.findByText("Hawg · A-10C · Base");
  expect(screen.getByText("Save area")).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Drawing name"), {
    target: { value: "LINE" },
  });
  fireEvent.click(screen.getByText("Save line"));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  expect(fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("saved-points/flight/drawings"),
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        name: "LINE",
        closed: false,
        points: [
          { lat: 42, lng: 42 },
          { lat: 43, lng: 43 },
        ],
      }),
    }),
  );
  expect(changed).toHaveBeenCalledTimes(1);
  window.removeEventListener("saved-points-changed", changed);
});

it("retains a failed drawing for retry and disables duplicate submissions", async () => {
  let finish!: (value: unknown) => void;
  const close = jest.fn();
  render(
    <DrawPanel
      points={[new LatLng(42, 42), new LatLng(43, 43), new LatLng(44, 42)]}
      undo={jest.fn()}
      close={close}
    />,
  );
  await screen.findByText("Hawg · A-10C · Base");
  (fetch as jest.Mock).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.click(screen.getByText("Save area"));
  expect(screen.getByText("Save line")).toBeDisabled();
  expect(screen.getByText("Cancel")).toBeDisabled();
  finish(response({ detail: "Flight cancelled" }, false));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Flight cancelled",
  );
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByText("Save area")).not.toBeDisabled();
});
