/**
 * Every flight on the map shows what it is going in against.
 *
 * The run is red for the flight being worked on and the flight's own colour in the
 * crowd, so a glance at the map says which targets already have somebody on them.
 */
import { Waypoint } from "../../api/liberationApi";
import { TARGET_PATH, TargetRuns } from "./legs";
import { render } from "@testing-library/react";

const mockPolyline = jest.fn();
const mockMarker = jest.fn();

jest.mock("react-leaflet", () => ({
  Polyline: (props: any) => {
    mockPolyline(props);
    return null;
  },
  Marker: (props: any) => {
    mockMarker(props);
    return null;
  },
  // The distance label works in screen space, so it asks the map to project.
  useMap: () => ({
    latLngToLayerPoint: ({ lat, lng }: { lat: number; lng: number }) => ({
      x: lng * 100,
      y: lat * 100,
    }),
  }),
  useMapEvent: () => undefined,
}));

function waypoint(over: Partial<Waypoint> = {}): Waypoint {
  return {
    name: "NAV",
    position: { lat: 0, lng: 0 },
    altitude_ft: 20000,
    altitude_reference: "BARO",
    is_movable: true,
    should_mark: true,
    include_in_path: true,
    timing: "",
    index: 0,
    can_delete: true,
    speed_kts: 350,
    is_target: false,
    shows_altitude: true,
    ...over,
  };
}

/** An ingress with two target points after it, the shape of a strike. */
const ingress = waypoint({
  name: "INGRESS",
  index: 3,
  position: { lat: 0, lng: 0 },
});
const targets = [
  waypoint({
    name: "STRIKE #0",
    index: 4,
    is_target: true,
    position: { lat: 0, lng: 1 },
  }),
  waypoint({
    name: "STRIKE #1",
    index: 5,
    is_target: true,
    position: { lat: 1, lng: 1 },
  }),
];
const waypoints = [ingress, ...targets];

beforeEach(() => {
  mockPolyline.mockClear();
  mockMarker.mockClear();
});

it("draws a run from the ingress to each target", () => {
  render(<TargetRuns waypoints={waypoints} drawn={[ingress]} />);

  expect(mockPolyline).toHaveBeenCalledTimes(2);
  for (const call of mockPolyline.mock.calls) {
    expect(call[0].positions[0]).toEqual(ingress.position);
    expect(call[0].pathOptions.dashArray).toBe("7 6");
  }
});

it("paints the run red when it belongs to the flight being worked on", () => {
  render(<TargetRuns waypoints={waypoints} drawn={[ingress]} labelled />);

  expect(mockPolyline.mock.calls[0][0].pathOptions.color).toBe(TARGET_PATH);
});

it("paints it the flight's own colour when the plan is part of the crowd", () => {
  render(
    <TargetRuns waypoints={waypoints} drawn={[ingress]} color="#0084ff" />,
  );

  expect(mockPolyline.mock.calls[0][0].pathOptions.color).toBe("#0084ff");
});

it("says how long the run is only for the flight being worked on", () => {
  render(<TargetRuns waypoints={waypoints} drawn={[ingress]} labelled />);
  expect(mockMarker).toHaveBeenCalled();

  mockMarker.mockClear();
  render(
    <TargetRuns waypoints={waypoints} drawn={[ingress]} color="#0084ff" />,
  );
  expect(mockMarker).not.toHaveBeenCalled();
});

it("draws nothing for a flight with no target waypoint", () => {
  render(<TargetRuns waypoints={[ingress]} drawn={[ingress]} />);

  expect(mockPolyline).not.toHaveBeenCalled();
});

it("gives the run a wide invisible twin to catch the mouse", () => {
  const click = jest.fn();
  render(
    <TargetRuns
      waypoints={waypoints}
      drawn={[ingress]}
      color="#0084ff"
      handlers={{ click }}
    />,
  );

  // One drawn run and one grab overlay per target.
  expect(mockPolyline).toHaveBeenCalledTimes(4);
  const grabs = mockPolyline.mock.calls
    .map((call) => call[0])
    .filter((props) => props.pathOptions.weight === 16);
  expect(grabs.length).toBe(2);
  for (const grab of grabs) {
    expect(grab.pathOptions.opacity).toBe(0);
    expect(grab.pathOptions.interactive).toBe(true);
    expect(grab.eventHandlers.click).toBe(click);
  }
});

it("draws no twin for a plan nothing can be done with", () => {
  render(
    <TargetRuns waypoints={waypoints} drawn={[ingress]} color="#c85050" />,
  );

  expect(mockPolyline).toHaveBeenCalledTimes(2);
  for (const call of mockPolyline.mock.calls) {
    expect(call[0].pathOptions.interactive).toBe(false);
  }
});
