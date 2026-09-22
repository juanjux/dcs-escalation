// Dragging a carrier or an LHA stopped on its own: the same symptom as the ship
// markers, with a different cause.
//
// The icon was built inline. iconForControlPoint() returns a new Leaflet Icon on
// every call, so every render passed react-leaflet a new reference and it
// answered with marker.setIcon(). setIcon replaces the marker's DOM element,
// which Leaflet's drag handler is bound to, so any re-render during a drag
// ended it.
import { ControlPoint } from "../../api/_liberationApi";
import { renderWithProviders } from "../../testutils";
import { MobileControlPoint } from "./MobileControlPoint";
import { PropsWithChildren } from "react";

const mockMarker = jest.fn();

jest.mock("react-leaflet", () => ({
  Marker: (props: PropsWithChildren<any>) => {
    mockMarker(props);
    return null;
  },
  Tooltip: () => null,
}));

jest.mock("./MovementPath", () => ({ MovementPath: () => null }));
jest.mock("./StaticControlPoint", () => ({ StaticControlPoint: () => null }));
jest.mock("./LocationTooltipText", () => () => null);
jest.mock("./EventHandlers", () => ({
  makeLocationMarkerEventHandlers: () => ({
    click: () => {},
    contextmenu: () => {},
  }),
}));

jest.mock("../../api/backend", () => ({
  __esModule: true,
  default: { get: () => Promise.resolve({ data: true }) },
}));

const noop = () => Promise.resolve();
jest.mock("../../api/liberationApi", () => ({
  useSetControlPointDestinationMutation: () => [
    () => ({ unwrap: () => Promise.resolve() }),
    { isLoading: false },
  ],
  useClearControlPointDestinationMutation: () => [noop],
}));

function carrier(name: string): ControlPoint {
  // A new object on every call, as the event stream produces.
  return {
    id: "cp-1",
    name: name,
    position: { lat: 10, lng: 20 },
    mobile: true,
    destination: null,
    sidc: "30031500001200000000",
    units: [],
  } as unknown as ControlPoint;
}

function lastProps(): any {
  return mockMarker.mock.calls[mockMarker.mock.calls.length - 1][0];
}

beforeEach(() => {
  mockMarker.mockClear();
});

it("keeps the same icon across a re-render", () => {
  // The bug: a new icon reference makes react-leaflet replace the marker's
  // element, and the drag handler bound to it goes with it.
  const { rerender } = renderWithProviders(
    <MobileControlPoint controlPoint={carrier("CVN-72")} />,
  );

  // Two updates, so the comparison is between two renders rather than against
  // the very first one.
  rerender(<MobileControlPoint controlPoint={carrier("CVN-72 Lincoln")} />);
  rerender(<MobileControlPoint controlPoint={carrier("CVN-72 Abraham")} />);

  const calls = mockMarker.mock.calls;
  expect(calls[calls.length - 1][0].icon).toBe(calls[calls.length - 2][0].icon);
});

it("builds a new icon when the symbol really changes", () => {
  const { rerender } = renderWithProviders(
    <MobileControlPoint controlPoint={carrier("CVN-72")} />,
  );
  const first = lastProps().icon;
  const damaged = carrier("CVN-72");
  (damaged as any).sidc = "30031500001200000001";

  rerender(<MobileControlPoint controlPoint={damaged} />);

  expect(lastProps().icon).not.toBe(first);
});

it("does not ask whether the point is in range on every pixel", () => {
  // Leaflet fires `drag` several times a frame; one HTTP request each is
  // wasteful for an answer that only changes at the range ring.
  const backend = require("../../api/backend").default;
  const asked = jest.spyOn(backend, "get");
  renderWithProviders(<MobileControlPoint controlPoint={carrier("CVN-72")} />);
  const handlers = lastProps().eventHandlers;
  handlers.dragstart();

  for (let n = 0; n < 20; n++) {
    handlers.drag({ target: { getLatLng: () => ({ lat: 10, lng: 20 + n }) } });
  }

  expect(asked.mock.calls.length).toBe(1);
  asked.mockRestore();
});
