import SavePoint from "./SavePoint";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { LatLng } from "leaflet";

const AT = new LatLng(36.5886, -115.6736);

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: "global-point" }),
  });
});

it("saves globally without player flights or an aircraft selector", async () => {
  const changed = jest.fn();
  window.addEventListener("saved-points-changed", changed);
  render(<SavePoint at={AT} name="WAREHOUSE" elevationFt={123} />);
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Save as waypoint"));
  expect(await screen.findByText("Saved to campaign")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/saved-points/campaign"),
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        kind: "waypoint",
        name: "WAREHOUSE",
        lat: AT.lat,
        lng: AT.lng,
        altitude_ft: 123,
      }),
    }),
  );
  expect(changed).toHaveBeenCalledTimes(1);
  window.removeEventListener("saved-points-changed", changed);
});

it("shows server errors without reporting success", async () => {
  (fetch as jest.Mock).mockResolvedValue({
    ok: false,
    json: async () => ({ detail: "No campaign loaded" }),
  });
  render(<SavePoint at={AT} name="Point" />);
  fireEvent.click(screen.getByText("Save as waypoint"));
  expect(await screen.findByText("No campaign loaded")).toBeInTheDocument();
  expect(screen.queryByText("Saved to campaign")).not.toBeInTheDocument();
});

it("prevents duplicate submissions while saving", async () => {
  let resolve!: (value: unknown) => void;
  (fetch as jest.Mock).mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  render(<SavePoint at={AT} name="Point" />);
  fireEvent.click(screen.getByText("Save as waypoint"));
  expect(screen.getByRole("button")).toBeDisabled();
  fireEvent.click(screen.getByText("Save as waypoint"));
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () =>
    resolve({ ok: true, json: async () => ({ id: "point" }) }),
  );
  await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
});
