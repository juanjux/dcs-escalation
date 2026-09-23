import { renderWithProviders } from "../../testutils";
import HighCommandLayer, {
  HALO_RADIUS,
  RING_RADIUS,
  tagText,
} from "./HighCommandLayer";
import { PropsWithChildren } from "react";

const mockCircleMarker = jest.fn();
const mockMarker = jest.fn();
const mockPane = jest.fn();
jest.mock("react-leaflet", () => ({
  Pane: (props: PropsWithChildren<any>) => {
    mockPane(props);
    return <>{props.children}</>;
  },
  LayerGroup: (props: PropsWithChildren<any>) => <>{props.children}</>,
  CircleMarker: (props: any) => {
    mockCircleMarker(props);
    return null;
  },
  Marker: (props: PropsWithChildren<any>) => {
    mockMarker(props);
    return <>{props.children}</>;
  },
  Tooltip: (props: PropsWithChildren<any>) => <>{props.children}</>,
}));

const mark = {
  name: "TURKEY",
  position: { lat: -54, lng: -68 },
  orders: 1,
  soonest: 3,
  last_turn: false,
  tooltip: "High Command order · high tier",
};

beforeEach(() => {
  mockCircleMarker.mockClear();
  mockMarker.mockClear();
  mockPane.mockClear();
});

describe("HighCommandLayer", () => {
  it("draws nothing without orders", () => {
    renderWithProviders(<HighCommandLayer />);
    expect(mockCircleMarker).not.toHaveBeenCalled();
    expect(mockMarker).not.toHaveBeenCalled();
  });

  it("rings an order's objective above the marker pane, taking no clicks", () => {
    renderWithProviders(<HighCommandLayer />, {
      preloadedState: { highCommand: { marks: [mark] } },
    });
    expect(mockPane).toHaveBeenCalledWith(
      expect.objectContaining({ name: "high-command", style: { zIndex: 610 } })
    );
    expect(mockCircleMarker).toHaveBeenCalledTimes(1);
    expect(mockCircleMarker).toHaveBeenCalledWith(
      expect.objectContaining({ radius: RING_RADIUS, interactive: false })
    );
    expect(mockMarker).toHaveBeenCalledTimes(1);
  });

  it("adds a halo in an order's last turn", () => {
    renderWithProviders(<HighCommandLayer />, {
      preloadedState: { highCommand: { marks: [{ ...mark, last_turn: true }] } },
    });
    expect(mockCircleMarker).toHaveBeenCalledWith(
      expect.objectContaining({ radius: HALO_RADIUS })
    );
  });

  it("tags the turns left, and how many orders a base has", () => {
    expect(tagText(mark)).toBe("HC · 3");
    expect(tagText({ ...mark, orders: 2, soonest: 1 })).toBe("HC ×2 · 1");
    expect(tagText({ ...mark, last_turn: true })).toBe("LAST TURN");
  });
});
