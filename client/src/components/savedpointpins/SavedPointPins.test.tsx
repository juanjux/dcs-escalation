import SavedPointPins, {
  PIN,
  SavedPoint,
  SavedPointPin,
} from "./SavedPointPins";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import React from "react";

const mockSetLatLng = jest.fn();
const mockOpenPopup = jest.fn();
jest.mock("react-leaflet", () => {
  const React = require("react");
  return {
    Marker: React.forwardRef((props: any, ref: any) => {
      React.useImperativeHandle(ref, () => ({
        setLatLng: mockSetLatLng,
        openPopup: mockOpenPopup,
      }));
      return (
        <section data-testid="pin">
          <button
            disabled={!props.draggable}
            onClick={() =>
              props.eventHandlers.dragend({
                target: { getLatLng: () => ({ lat: 43, lng: 44 }) },
              })
            }
          >
            Drag
          </button>
          {props.children}
        </section>
      );
    }),
    Popup: ({ children }: any) => <div>{children}</div>,
    Tooltip: ({ children }: any) => <div role="tooltip">{children}</div>,
  };
});

const point: SavedPoint = {
  id: "point-1",
  name: "TARGET",
  kind: "waypoint",
  position: { lat: 42, lng: 42 },
  coordinates: "42N 42E",
  altitude_ft: 123,
};
const receiver = {
  id: "flight-1",
  callsign: "Hawg",
  aircraft: "A-10C",
  points: [point],
};
const response = (body: unknown, ok = true) => ({ ok, json: async () => body });
function deferred() {
  let resolve!: (value: any) => void;
  const promise = new Promise<any>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function changed(detail?: object) {
  window.dispatchEvent(new CustomEvent("saved-points-changed", { detail }));
}

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn().mockResolvedValue(response([receiver]));
});

it("uses a yellow pin and shows one tooltip for shared squadron points", async () => {
  (fetch as jest.Mock).mockResolvedValue(
    response([receiver, { ...receiver, id: "flight-2" }]),
  );
  render(<SavedPointPins />);
  expect(await screen.findAllByTestId("pin")).toHaveLength(1);
  expect(screen.getByRole("tooltip")).toHaveTextContent("TARGET");
  expect(PIN.options.html).toContain('fill="#ffdf32"');
});

it("renames and deletes by persistent ID and announces each successful edit", async () => {
  const notify = jest.fn();
  window.addEventListener("saved-points-changed", notify);
  render(<SavedPointPin point={point} receiver={receiver} />);
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "BRIDGE" },
  });
  fireEvent.click(screen.getByText("Rename"));
  await waitFor(() => expect(notify).toHaveBeenCalledTimes(1));
  expect(fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("/flight-1/points/point-1"),
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ name: "BRIDGE" }),
    }),
  );
  fireEvent.click(screen.getByText("Delete"));
  await waitFor(() => expect(notify).toHaveBeenCalledTimes(2));
  expect(fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("/flight-1/points/point-1"),
    expect.objectContaining({ method: "DELETE" }),
  );
  window.removeEventListener("saved-points-changed", notify);
});

it("locks edits during a move and restores the old position on failure", async () => {
  const pending = deferred();
  (fetch as jest.Mock).mockReturnValue(pending.promise);
  render(<SavedPointPin point={point} receiver={receiver} />);
  fireEvent.click(screen.getByText("Drag"));
  expect(screen.getByText("Delete")).toBeDisabled();
  expect(screen.getByText("Drag")).toBeDisabled();
  expect(fetch).toHaveBeenLastCalledWith(
    expect.any(String),
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ position: { lat: 43, lng: 44 } }),
    }),
  );
  await act(async () => {
    pending.resolve(response({ detail: "No such point" }, false));
  });
  expect(screen.getByRole("alert")).toHaveTextContent("No such point");
  expect(mockSetLatLng).toHaveBeenCalledWith(point.position);
  expect(mockOpenPopup).toHaveBeenCalled();
  expect(screen.getByText("Drag")).toBeEnabled();
});

it("refreshes renamed points and removes deleted or cancelled-flight points", async () => {
  render(<SavedPointPins />);
  await screen.findByText("TARGET");
  (fetch as jest.Mock).mockResolvedValue(
    response([{ ...receiver, points: [{ ...point, name: "NEW" }] }]),
  );
  act(() => changed());
  await waitFor(() =>
    expect(screen.getByRole("tooltip")).toHaveTextContent("NEW"),
  );
  (fetch as jest.Mock).mockResolvedValue(response([]));
  act(() => changed());
  await waitFor(() =>
    expect(screen.queryByTestId("pin")).not.toBeInTheDocument(),
  );
});

it("ignores late responses after a newer refresh", async () => {
  const old = deferred();
  (fetch as jest.Mock).mockReturnValueOnce(old.promise);
  render(<SavedPointPins />);
  (fetch as jest.Mock).mockResolvedValue(response([]));
  await act(async () => changed());
  await act(async () => old.resolve(response([receiver])));
  expect(screen.queryByTestId("pin")).not.toBeInTheDocument();
});

it.each(["unloaded", "reset"])(
  "clears pins on campaign %s and ignores pending old data",
  async (event) => {
    render(<SavedPointPins />);
    await screen.findByTestId("pin");
    const old = deferred();
    (fetch as jest.Mock)
      .mockReturnValueOnce(old.promise)
      .mockResolvedValue(response([]));
    act(() => changed());
    await act(async () => changed({ [event]: true }));
    expect(screen.queryByTestId("pin")).not.toBeInTheDocument();
    await act(async () => old.resolve(response([receiver])));
    expect(screen.queryByTestId("pin")).not.toBeInTheDocument();
  },
);

it("removes its listener and aborts requests on unmount", () => {
  const pending = deferred();
  (fetch as jest.Mock).mockReturnValue(pending.promise);
  const view = render(<SavedPointPins />);
  const signal = (fetch as jest.Mock).mock.calls[0][1].signal;
  view.unmount();
  expect(signal.aborted).toBe(true);
  changed();
  expect(fetch).toHaveBeenCalledTimes(1);
});
