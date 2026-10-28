import { act, screen } from "@testing-library/react";
import { LatLng, Map, Marker } from "leaflet";
import { renderWithProviders } from "../../testutils";
import { clearButtonHover, setHoveredEmitter } from "../../api/mapSlice";
import TgoIcon from "../tgos/TgoIcon";
import { ControlPointIcon } from "../controlpoints/Icons";
import MapButtonHover, {
  MapButtonHoverRequest,
  visibleHoverTarget,
} from "./MapButtonHover";

let mockLayers: Marker[];
let mockContainer: HTMLDivElement;
const mockMap = {
  eachLayer: (visit: (layer: Marker) => void) => mockLayers.forEach(visit),
  getContainer: () => mockContainer,
  getBounds: () => ({ contains: () => true }),
  on: jest.fn(),
  off: jest.fn(),
};
jest.mock("react-leaflet", () => ({
  useMap: () => mockMap,
  CircleMarker: () => <div data-testid="hover-highlight" />,
}));

const request: MapButtonHoverRequest = {
  owner: "button-a",
  target_id: "target",
  position: { lat: 33, lng: 69 },
};
function marker(base = false) {
  const layer = new Marker([33, 69], {
    icon: base
      ? new ControlPointIcon("target", { iconUrl: "x.svg" })
      : new TgoIcon("target", { iconUrl: "x.svg" }),
  });
  const element = document.createElement("img");
  mockContainer.appendChild(element);
  jest
    .spyOn(element, "getBoundingClientRect")
    .mockReturnValue({ width: 40, height: 40 } as DOMRect);
  jest.spyOn(layer, "getElement").mockReturnValue(element);
  mockLayers.push(layer);
  return { layer, element };
}
function send(detail: MapButtonHoverRequest) {
  act(() =>
    window.dispatchEvent(new CustomEvent("map-button-hover", { detail })),
  );
}
beforeEach(() => {
  jest.restoreAllMocks();
  mockLayers = [];
  mockContainer = document.createElement("div");
  jest.clearAllMocks();
});

it.each([false, true])(
  "finds a rendered objective or base without moving the map: %s",
  (base) => {
    marker(base);
    expect(visibleHoverTarget(mockMap as unknown as Map, request)).toEqual({
      id: "target",
      position: new LatLng(33, 69),
    });
    expect(
      visibleHoverTarget(mockMap as unknown as Map, {
        ...request,
        target_id: null,
      }),
    ).toBeDefined();
  },
);

it.each([
  "hidden",
  "removed",
  "zero-size",
  "offscreen",
  "wrong-id",
  "wrong-position",
])("does not reveal an absent icon: %s", (kind) => {
  const { element } = marker();
  let next = request;
  if (kind === "hidden") element.style.visibility = "hidden";
  if (kind === "removed") element.remove();
  if (kind === "zero-size")
    jest
      .spyOn(element, "getBoundingClientRect")
      .mockReturnValue({ width: 0, height: 0 } as DOMRect);
  if (kind === "offscreen")
    jest
      .spyOn(mockMap, "getBounds")
      .mockReturnValueOnce({ contains: () => false });
  if (kind === "wrong-id") next = { ...request, target_id: "other" };
  if (kind === "wrong-position")
    next = { ...request, target_id: null, position: { lat: 34, lng: 70 } };
  expect(visibleHoverTarget(mockMap as unknown as Map, next)).toBeUndefined();
});

it("uses the search/ring highlight and clears it when its owner leaves", () => {
  marker();
  const { store } = renderWithProviders(<MapButtonHover />);
  const center = store.getState().map.center;
  send(request);
  expect(screen.getByTestId("hover-highlight")).toBeInTheDocument();
  expect(store.getState().map.hoveredEmitterId).toBe("target");
  expect(store.getState().map.center).toBe(center);
  send({ ...request, position: null });
  expect(screen.queryByTestId("hover-highlight")).not.toBeInTheDocument();
  expect(store.getState().map.hoveredEmitterId).toBeNull();
});

it("ignores an older button's leave and does not clear a later search hover", () => {
  marker();
  const { store } = renderWithProviders(<MapButtonHover />);
  send(request);
  send({ ...request, owner: "button-b" });
  send({ ...request, position: null });
  expect(screen.getByTestId("hover-highlight")).toBeInTheDocument();
  act(() =>
    store.dispatch(setHoveredEmitter({ id: "search", source: "ring" })),
  );
  send({ ...request, owner: "button-b", position: null });
  expect(store.getState().map.hoveredEmitterId).toBe("search");
  act(() => store.dispatch(clearButtonHover()));
  expect(store.getState().map.hoveredEmitterId).toBe("search");
});

it("clears hover on campaign changes, window blur and unmount", () => {
  marker();
  const { store, unmount } = renderWithProviders(<MapButtonHover />);
  for (const event of ["saved-points-changed", "blur"]) {
    send(request);
    act(() => window.dispatchEvent(new Event(event)));
    expect(store.getState().map.hoveredEmitterId).toBeNull();
  }
  send(request);
  unmount();
  expect(store.getState().map.hoveredEmitterId).toBeNull();
});

it("clears a highlight if its icon layer is removed", () => {
  const { layer } = marker();
  const { store } = renderWithProviders(<MapButtonHover />);
  send(request);
  mockLayers = [];
  act(() => mockMap.on.mock.calls[0][1]({ type: "layerremove", layer }));
  expect(store.getState().map.hoveredEmitterId).toBeNull();
  expect(screen.queryByTestId("hover-highlight")).not.toBeInTheDocument();
});

it("does not restart button hover when its highlight layer is removed by a later search", () => {
  marker();
  const { store } = renderWithProviders(<MapButtonHover />);
  send(request);
  act(() =>
    store.dispatch(setHoveredEmitter({ id: "search", source: "ring" })),
  );
  act(() => mockMap.on.mock.calls[0][1]({ type: "layerremove", layer: {} }));
  expect(store.getState().map.hoveredEmitterId).toBe("search");
});
