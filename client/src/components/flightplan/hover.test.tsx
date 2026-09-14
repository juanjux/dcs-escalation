/**
 * Pointing at a plan lights the whole plan up.
 *
 * The route goes yellow, and its runs in to the target go red -- what they are for the
 * flight being worked on. Only while the pointer is on it: they go back to the flight's
 * own colour on the way out, unless the click landed.
 */
import { renderWithProviders } from "../../testutils";
import FlightPlan from "./FlightPlan";
import { TARGET_PATH } from "./legs";
import { act } from "@testing-library/react";
import { PropsWithChildren } from "react";

const mockPolyline = jest.fn();

jest.mock("react-leaflet", () => ({
  Polyline: (props: PropsWithChildren<any>) => {
    mockPolyline(props);
    return null;
  },
  Marker: () => null,
  Tooltip: () => null,
  useMap: () => ({
    latLngToLayerPoint: ({ lat, lng }: { lat: number; lng: number }) => ({
      x: lng,
      y: lat,
    }),
  }),
  useMapEvent: () => undefined,
}));

const BLUE = "#0084ff";

function waypoint(over: object = {}) {
  return {
    name: "WP",
    position: { lat: 0, lng: 0 },
    altitude_ft: 0,
    altitude_reference: "MSL",
    is_movable: true,
    should_mark: false,
    include_in_path: true,
    is_target: false,
    shows_altitude: true,
    timing: "",
    index: 0,
    can_delete: false,
    speed_kts: 0,
    ...over,
  };
}

const flight = {
  id: "flight",
  blue: true,
  sidc: "",
  waypoints: [
    waypoint({ name: "INGRESS", index: 3 }),
    waypoint({
      name: "STRIKE",
      index: 4,
      is_target: true,
      include_in_path: false,
      position: { lat: 1, lng: 1 },
    }),
  ],
};

/** Every polyline drawn, in the order they were drawn. */
function drawn(): any[] {
  return mockPolyline.mock.calls.map((call) => call[0]).filter(Boolean);
}

/** The dashed run's colour, from the last time it was drawn. */
function runColor(): string {
  const runs = drawn().filter(
    (props) => props.pathOptions?.dashArray === "7 6",
  );
  return runs[runs.length - 1].pathOptions.color;
}

/** The wide invisible twin that catches the mouse. */
function grab(): any {
  return drawn().find((props) => props.pathOptions?.weight === 16);
}

beforeEach(() => {
  mockPolyline.mockClear();
  renderWithProviders(
    <FlightPlan flight={flight as any} selected={false} />,
    {},
  );
});

it("draws the run in the flight's own colour to start with", () => {
  expect(runColor()).toBe(BLUE);
});

it("turns the run red while the pointer is on the plan", () => {
  act(() => grab().eventHandlers.mouseover());

  expect(runColor()).toBe(TARGET_PATH);
});

it("puts it back when the pointer leaves", () => {
  act(() => grab().eventHandlers.mouseover());
  act(() => grab().eventHandlers.mouseout());

  expect(runColor()).toBe(BLUE);
});
