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
const GPS = "N36°35.316' W115°40.416'";

function openNameEditor() {
  fireEvent.click(screen.getByRole("button", { name: "Save as waypoint" }));
  return screen.getByRole("textbox", { name: "Waypoint name" });
}

function confirmName() {
  fireEvent.click(screen.getByRole("button", { name: "Save", exact: true }));
}

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: "global-point" }),
  });
});

it.each([
  [GPS, GPS],
  ["  WAREHOUSE  ", "WAREHOUSE"],
  [" ", GPS],
])("saves the chosen name globally (%s)", async (entered, expected) => {
  const changed = jest.fn();
  window.addEventListener("saved-points-changed", changed);
  render(<SavePoint at={AT} defaultName={GPS} elevationFt={123} />);
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  const name = openNameEditor();
  expect(name).toHaveValue(GPS);
  expect(name).toHaveFocus();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(name, { target: { value: entered } });
  confirmName();
  expect(await screen.findByText("Saved to campaign")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/saved-points/campaign"),
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        kind: "waypoint",
        name: expected,
        lat: AT.lat,
        lng: AT.lng,
        altitude_ft: 123,
      }),
    }),
  );
  expect(changed).toHaveBeenCalledTimes(1);
  window.removeEventListener("saved-points-changed", changed);
});

it("cancels without saving and restores the coordinate default on reopening", () => {
  render(<SavePoint at={AT} defaultName={GPS} />);
  fireEvent.change(openNameEditor(), { target: { value: "Discarded" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  expect(openNameEditor()).toHaveValue(GPS);
});

it("shows server errors without reporting success", async () => {
  (fetch as jest.Mock).mockResolvedValue({
    ok: false,
    json: async () => ({ detail: "No campaign loaded" }),
  });
  render(<SavePoint at={AT} defaultName={GPS} />);
  const name = openNameEditor();
  fireEvent.change(name, { target: { value: "Retry name" } });
  confirmName();
  expect(await screen.findByText("No campaign loaded")).toBeInTheDocument();
  expect(screen.queryByText("Saved to campaign")).not.toBeInTheDocument();
  expect(name).toHaveValue("Retry name");
});

it("prevents duplicate submissions while saving", async () => {
  let resolve!: (value: unknown) => void;
  (fetch as jest.Mock).mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  render(<SavePoint at={AT} defaultName={GPS} />);
  openNameEditor();
  confirmName();
  expect(
    screen.getByRole("button", { name: "Save", exact: true }),
  ).toBeDisabled();
  confirmName();
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () =>
    resolve({ ok: true, json: async () => ({ id: "point" }) }),
  );
  await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
});
