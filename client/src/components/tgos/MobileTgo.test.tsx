// Dragging a ship used to let go on its own, over and over, as if the mouse
// button had been released.
//
// It was the marker being put back. react-leaflet answers a changed `position`
// prop with marker.setLatLng(), and the position came from an effect watching
// `props.tgo.position` -- an object, so a fresh identity every time the event
// stream touched that ship for any reason at all. Mid-drag that yanked the icon
// out from under the cursor, which is indistinguishable from letting go.
import { Tgo as TgoModel } from "../../api/liberationApi";
import { renderWithProviders } from "../../testutils";
import MobileTgo from "./MobileTgo";
import { PropsWithChildren } from "react";

const mockMarker = jest.fn();

jest.mock("react-leaflet", () => ({
  Marker: (props: PropsWithChildren<any>) => {
    mockMarker(props);
    return null;
  },
  Tooltip: () => null,
}));

jest.mock("../controlpoints/MovementPath", () => ({
  MovementPath: () => null,
}));

jest.mock("../../api/backend", () => ({
  __esModule: true,
  default: { get: () => Promise.resolve({ data: true }) },
}));

const noop = () => Promise.resolve({ unwrap: () => Promise.resolve() });
jest.mock("../../api/liberationApi", () => ({
  useSetTgoDestinationMutation: () => [
    () => ({ unwrap: () => Promise.resolve() }),
    { isLoading: false },
  ],
  useClearTgoDestinationMutation: () => [noop],
  useOpenTgoInfoDialogMutation: () => [noop],
  useOpenNewTgoPackageDialogMutation: () => [noop],
}));

function ship(lat: number, lng: number): TgoModel {
  // A new object every call, which is what the event stream hands out.
  return {
    id: "ship-1",
    name: "CARRIER GROUP",
    control_point_name: "CP",
    category: "ship",
    blue: true,
    position: { lat: lat, lng: lng },
    units: [],
    threat_ranges: [],
    detection_ranges: [],
    dead: false,
    purchasable: false,
    sidc: "",
    mobile: true,
  } as TgoModel;
}

/** The position the last rendered Marker was given. */
function shownAt(): { lat: number; lng: number } {
  return mockMarker.mock.calls[mockMarker.mock.calls.length - 1][0].position;
}

function handlers(): Record<string, (event?: any) => void> {
  return mockMarker.mock.calls[mockMarker.mock.calls.length - 1][0].eventHandlers;
}

beforeEach(() => {
  mockMarker.mockClear();
});

it("moves the ship when an update arrives and nobody is dragging", () => {
  const { rerender } = renderWithProviders(<MobileTgo tgo={ship(10, 20)} />);

  rerender(<MobileTgo tgo={ship(11, 21)} />);

  expect(shownAt()).toEqual({ lat: 11, lng: 21 });
});

it("leaves it alone while it is being dragged", () => {
  // The whole bug: an update arriving mid-drag put the marker back, and the
  // drag ended there.
  const { rerender } = renderWithProviders(<MobileTgo tgo={ship(10, 20)} />);
  handlers().dragstart();

  rerender(<MobileTgo tgo={ship(11, 21)} />);

  expect(shownAt()).toEqual({ lat: 10, lng: 20 });
});

it("takes updates again once the drag is over", () => {
  const { rerender } = renderWithProviders(<MobileTgo tgo={ship(10, 20)} />);
  handlers().dragstart();
  handlers().dragend({ target: { getLatLng: () => ({ lat: 12, lng: 22 }) } });

  rerender(<MobileTgo tgo={ship(13, 23)} />);

  expect(shownAt()).toEqual({ lat: 13, lng: 23 });
});

it("does not ask whether the point is in range on every pixel", () => {
  // Leaflet fires `drag` several times a frame; one HTTP round trip each is a
  // request storm for an answer that changes once, at the range ring.
  const backend = require("../../api/backend").default;
  const asked = jest.spyOn(backend, "get");
  renderWithProviders(<MobileTgo tgo={ship(10, 20)} />);
  handlers().dragstart();

  for (let n = 0; n < 20; n++) {
    handlers().drag({ target: { getLatLng: () => ({ lat: 10, lng: 20 + n }) } });
  }

  expect(asked.mock.calls.length).toBe(1);
  asked.mockRestore();
});
