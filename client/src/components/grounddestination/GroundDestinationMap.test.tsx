import { act, fireEvent, render, screen } from "@testing-library/react";
import GroundDestinationMode, {
  DestinationInteraction,
} from "./GroundDestinationMap";
import { DestinationBridge } from "./bridge";
import { Marker } from "leaflet";
import TgoIcon from "../tgos/TgoIcon";
import { SnapTarget } from "./targetSnap";

const mockContainer = document.createElement("div");
const mockMap = {
  getContainer: () => mockContainer,
  getCenter: () => ({ lat: 40, lng: 39 }),
  getZoom: () => 8,
  stop: jest.fn(),
  closePopup: jest.fn(),
  setView: jest.fn(),
  eachLayer: jest.fn(),
  doubleClickZoom: {
    enabled: () => true,
    disable: jest.fn(),
    enable: jest.fn(),
  },
};
let mockHandlers: Record<string, (event: any) => void>;
jest.mock("../terrainzones/TerrainZonesLayers", () => ({
  ExclusionZonesLayer: () => <div data-testid="movement-exclusions" />,
}));
jest.mock("react-leaflet", () => ({
  Pane: ({ children, style, name }: any) => (
    <div
      data-testid={
        name === "ground-destination-route"
          ? "route-overlay"
          : "exclusion-overlay"
      }
      style={style}
    >
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
  Circle: (props: any) => (
    <div data-testid="missile-ring" data-radius={props.radius} />
  ),
}));

function event(lat = 42, lng = 41) {
  return {
    latlng: { lat, lng },
    originalEvent: { target: mockContainer, clientX: 30, clientY: 30 },
  };
}
function setup(
  options: { mode?: "missile"; snap_targets?: SnapTarget[] } = {},
) {
  const bridge: DestinationBridge = {
    ready: jest.fn(),
    initial: jest.fn(),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  const view = render(
    <DestinationInteraction
      bridge={bridge}
      origin={{
        origin: { lat: 42, lng: 41 },
        name: "Reserve Alpha",
        ...options,
      }}
    />,
  );
  return { bridge, ...view };
}

it("shows missile range rings and aimpoint warnings instead of ground-route ETA", async () => {
  const bridge: DestinationBridge = {
    ready: jest.fn(),
    initial: jest.fn(),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  render(
    <DestinationInteraction
      bridge={bridge}
      origin={{
        origin: { lat: 42, lng: 41 },
        name: "SCUD",
        mode: "missile",
        min_range_m: 10000,
        max_range_m: 250000,
      }}
    />,
  );
  expect(
    screen.getByText("Choose the missile target and click"),
  ).toBeInTheDocument();
  expect(screen.getAllByTestId("missile-ring")).toHaveLength(2);
  expect(screen.queryByTestId("movement-exclusions")).not.toBeInTheDocument();
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  await act(async () => {
    (bridge.preview as jest.Mock).mock.calls[0][2](
      JSON.stringify({
        valid: true,
        distance_m: 50000,
        target_name: "GPS position",
        warning: "No known enemy target here",
      }),
    );
  });
  expect(screen.getByText(/50.0 km · GPS position/)).toBeInTheDocument();
  expect(screen.getByText("No known enemy target here")).toBeInTheDocument();
  expect(screen.queryByText(/turn\(s\)/)).not.toBeInTheDocument();
});
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockMap.eachLayer.mockReset();
  mockContainer.replaceChildren();
});

function targetIcon() {
  const target = {
    id: "enemy",
    name: "MINK",
    position: { lat: 42.1, lng: 41.1 },
  };
  const marker = new Marker([42.1, 41.1], {
    icon: new TgoIcon(target.id, { iconUrl: "enemy.svg" }),
  });
  const icon = document.createElement("img");
  mockContainer.appendChild(icon);
  jest.spyOn(marker, "getElement").mockReturnValue(icon);
  jest.spyOn(icon, "getBoundingClientRect").mockReturnValue({
    left: 20,
    right: 60,
    top: 20,
    bottom: 60,
    width: 40,
    height: 40,
  } as DOMRect);
  mockMap.eachLayer.mockImplementation((visit) => visit(marker));
  return target;
}

it("uses the same snapped coordinates for preview and click anywhere within an icon", async () => {
  const target = targetIcon();
  const { bridge } = setup({ mode: "missile", snap_targets: [target] });
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  expect(bridge.preview).toHaveBeenCalledWith(42.1, 41.1, expect.any(Function));
  await act(async () => {
    (bridge.preview as jest.Mock).mock.calls[0][2](
      JSON.stringify({
        valid: true,
        target_name: "MINK",
        distance_m: 50000,
      }),
    );
  });
  expect(screen.getByText(/50.0 km · MINK/)).toBeInTheDocument();
  act(() => {
    mockHandlers.mousemove(event(42.05, 41.05));
    mockHandlers.click(event(42.08, 41.08));
  });
  expect(bridge.preview).toHaveBeenCalledTimes(1);
  expect(bridge.pick).toHaveBeenCalledWith(42.1, 41.1, expect.any(Function));
});

it("returns to free aimpoints after leaving an icon and keeps ground movement unsnapped", () => {
  const target = targetIcon();
  const first = setup({ mode: "missile", snap_targets: [target] });
  act(() => {
    mockHandlers.mousemove({
      ...event(),
      originalEvent: { target: mockContainer, clientX: 80, clientY: 80 },
    });
    jest.advanceTimersByTime(150);
  });
  expect(first.bridge.preview).toHaveBeenCalledWith(
    42,
    41,
    expect.any(Function),
  );
  first.unmount();
  const second = setup({ snap_targets: [target] });
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  expect(second.bridge.preview).toHaveBeenCalledWith(
    42,
    41,
    expect.any(Function),
  );
});

it("does not allow clicking an out-of-range snapped target", async () => {
  const target = targetIcon();
  const { bridge } = setup({ mode: "missile", snap_targets: [target] });
  act(() => {
    mockHandlers.mousemove(event());
    jest.advanceTimersByTime(150);
  });
  await act(async () => {
    (bridge.preview as jest.Mock).mock.calls[0][2](
      JSON.stringify({ valid: false, error: "Outside missile range" }),
    );
  });
  act(() => mockHandlers.click(event()));
  expect(bridge.pick).not.toHaveBeenCalled();
  expect(screen.getByText("Outside missile range")).toBeInTheDocument();
});
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

it("shows exclusion zones only while choosing a ground destination", () => {
  const { unmount } = setup();
  expect(screen.getByTestId("movement-exclusions")).toBeInTheDocument();
  expect(screen.getByTestId("exclusion-overlay")).toHaveStyle({
    zIndex: 410,
    pointerEvents: "none",
  });
  expect(screen.getByText(/campaign roads may cross/)).toBeInTheDocument();
  unmount();
  expect(screen.queryByTestId("movement-exclusions")).not.toBeInTheDocument();
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

it("reuses the map and restores its view and interactions on exit", () => {
  const { bridge, unmount } = setup();
  expect(bridge.ready).toHaveBeenCalledTimes(1);
  expect(mockMap.setView).toHaveBeenCalledWith({ lat: 42, lng: 41 }, 10, {
    animate: false,
  });
  expect(mockContainer).toHaveClass("ground-destination-map");
  expect(mockMap.doubleClickZoom.disable).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(bridge.dismiss).toHaveBeenCalledTimes(1);
  const editing = jest.fn();
  document.addEventListener("keydown", editing);
  fireEvent.keyDown(document, { key: "Delete" });
  fireEvent.keyDown(document, { key: "Enter" });
  expect(editing).not.toHaveBeenCalled();
  unmount();
  expect(mockMap.setView).toHaveBeenLastCalledWith({ lat: 40, lng: 39 }, 8, {
    animate: false,
  });
  expect(mockContainer).not.toHaveClass("ground-destination-map");
  expect(mockMap.doubleClickZoom.enable).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(document, { key: "Delete" });
  expect(editing).toHaveBeenCalledTimes(1);
  document.removeEventListener("keydown", editing);
});

it("can enter and leave selection repeatedly without a second map", async () => {
  const changed = jest.fn();
  const bridge: DestinationBridge = {
    ready: jest.fn(),
    initial: (done) =>
      done(
        JSON.stringify({ origin: { lat: 42, lng: 41 }, name: "Reserve Alpha" }),
      ),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  const { unmount } = render(
    <GroundDestinationMode onActiveChange={changed} />,
  );
  expect(window.groundDestinationModeReady).toBe(true);
  for (const id of ["first", "second"]) {
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("ground-destination-start", { detail: { id, bridge } }),
      );
    });
    expect(changed).toHaveBeenLastCalledWith(true);
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(
        new CustomEvent("ground-destination-end", {
          detail: { id: "old-session" },
        }),
      );
    });
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(
        new CustomEvent("ground-destination-end", { detail: { id } }),
      );
    });
    expect(changed).toHaveBeenLastCalledWith(false);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  }
  expect(bridge.ready).toHaveBeenCalledTimes(2);
  unmount();
  expect(window.groundDestinationModeReady).toBe(false);
});

it("discards an initial response received after cancellation", async () => {
  const changed = jest.fn();
  const bridge: DestinationBridge = {
    ready: jest.fn(),
    initial: jest.fn(),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  render(<GroundDestinationMode onActiveChange={changed} />);
  act(() => {
    window.dispatchEvent(
      new CustomEvent("ground-destination-start", {
        detail: { id: "late", bridge },
      }),
    );
    window.dispatchEvent(
      new CustomEvent("ground-destination-end", { detail: { id: "late" } }),
    );
  });
  await act(async () => {
    (bridge.initial as jest.Mock).mock.calls[0][0](
      JSON.stringify({ origin: { lat: 42, lng: 41 }, name: "Reserve Alpha" }),
    );
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(bridge.ready).not.toHaveBeenCalled();
  expect(changed).toHaveBeenLastCalledWith(false);
});
