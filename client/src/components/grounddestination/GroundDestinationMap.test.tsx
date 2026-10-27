import { act, render, screen } from "@testing-library/react";
import { DestinationInteraction } from "./GroundDestinationMap";
import { DestinationBridge } from "./bridge";

const mockContainer = document.createElement("div");
const mockMap = { getContainer: () => mockContainer };
let mockHandlers: Record<string, (event: any) => void>;
jest.mock("react-leaflet", () => ({
  Pane: ({ children, style }: any) => (
    <div data-testid="route-overlay" style={style}>
      {children}
    </div>
  ),
  useMap: () => mockMap,
  useMapEvents: (handlers: typeof mockHandlers) => {
    mockHandlers = handlers;
  },
  Polyline: (props: any) => (
    <div
      data-testid="route"
      data-points={JSON.stringify(props.positions)}
      data-dashed={props.pathOptions.dashArray}
    />
  ),
  CircleMarker: () => null,
}));

function event(lat = 42, lng = 41) {
  return { latlng: { lat, lng }, originalEvent: { target: mockContainer } };
}
function setup() {
  const bridge: DestinationBridge = {
    initial: jest.fn(),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  const view = render(
    <DestinationInteraction
      bridge={bridge}
      origin={{ origin: { lat: 42, lng: 41 }, name: "Reserve Alpha" }}
    />,
  );
  return { bridge, ...view };
}
beforeEach(() => jest.useFakeTimers());
afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
});

it("shows the requested instruction and cancels with Escape", () => {
  const { bridge } = setup();
  expect(
    screen.getByText("Choose the armor group/SAM destination and click"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Selecting a position does not dispatch units/),
  ).toBeInTheDocument();
  act(() =>
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })),
  );
  expect(bridge.dismiss).toHaveBeenCalledTimes(1);
});

it("shows distance, ETA and a highlighted road/off-road route for a valid position", async () => {
  const { bridge } = setup();
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  expect(mockContainer.dataset.destinationStatus).toBe("pending");
  await act(async () => {
    (bridge.preview as jest.Mock).mock.calls[0][2](
      JSON.stringify({
        valid: true,
        road_distance_m: 20000,
        offroad_distance_m: 3000,
        arrival_in_turns: 2,
        segments: [
          {
            start: { lat: 42, lng: 41 },
            end: { lat: 42.1, lng: 41 },
            on_road: true,
          },
          {
            start: { lat: 42.1, lng: 41 },
            end: { lat: 42.1, lng: 41.1 },
            on_road: false,
          },
        ],
      }),
    );
  });
  expect(mockContainer.dataset.destinationStatus).toBe("valid");
  expect(screen.getByText(/23.0 km · 2 turn/)).toBeInTheDocument();
  expect(screen.getAllByTestId("route")).toHaveLength(2);
  expect(screen.getByTestId("route-overlay")).toHaveStyle({
    zIndex: 640,
    pointerEvents: "none",
  });
  expect(screen.getAllByTestId("route")[1]).toHaveAttribute(
    "data-dashed",
    "8 6",
  );
  act(() => mockHandlers.mousemove(event(43, 42)));
  expect(mockContainer.dataset.destinationStatus).toBe("pending");
  act(() => {
    mockHandlers.click(event(43, 42));
  });
  expect(bridge.pick).not.toHaveBeenCalled();
});

it("shows a blocked reason and invalid cursor without allowing the click", async () => {
  const { bridge } = setup();
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  await act(async () =>
    (bridge.preview as jest.Mock).mock.calls[0][2](
      '{"valid":false,"error":"Choose a position in friendly territory"}',
    ),
  );
  expect(mockContainer.dataset.destinationStatus).toBe("invalid");
  expect(
    screen.getByText("Choose a position in friendly territory"),
  ).toBeInTheDocument();
  expect(screen.queryByTestId("route")).not.toBeInTheDocument();
  act(() => {
    mockHandlers.click(event());
  });
  expect(bridge.pick).not.toHaveBeenCalled();
});

it("ignores the banner and clears the preview on leaving the map", () => {
  const { bridge, unmount } = setup();
  act(() =>
    mockHandlers.mousemove({
      ...event(),
      originalEvent: { target: screen.getByRole("status") },
    }),
  );
  act(() => jest.advanceTimersByTime(150));
  expect(bridge.preview).not.toHaveBeenCalled();
  act(() => mockHandlers.mousemove(event()));
  act(() => mockHandlers.mouseout({ originalEvent: { relatedTarget: null } }));
  expect(mockContainer.dataset.destinationStatus).toBe("idle");
  unmount();
  expect(mockContainer.dataset.destinationStatus).toBeUndefined();
});
