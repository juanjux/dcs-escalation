import { act, render } from "@testing-library/react";
import LiberationMap from "./LiberationMap";

const mockMap = { setView: jest.fn(), getZoom: () => 8 };
const mockLayersMounted = jest.fn();
const mockLayersUnmounted = jest.fn();
let mockChangeMode: (active: boolean) => void;
jest.mock("../../app/hooks", () => ({ useAppSelector: () => null }));
jest.mock("react-leaflet", () => {
  const React = require("react");
  return {
    MapContainer: React.forwardRef(({ children }: any, ref: any) => {
      React.useImperativeHandle(ref, () => mockMap);
      return <div data-testid="main-map">{children}</div>;
    }),
    ScaleControl: () => null,
  };
});
jest.mock("../maplayers/MapLayersControl", () => {
  const React = require("react");
  return () => {
    React.useEffect(() => {
      mockLayersMounted();
      return mockLayersUnmounted;
    }, []);
    return null;
  };
});
jest.mock("../coordinatepicker", () => () => null);
jest.mock("../savedpointpins/SavedPointPins", () => () => null);
jest.mock("../mapsearch", () => () => null);
jest.mock("../ruler/Ruler", () => () => null);
jest.mock(
  "../grounddestination/GroundDestinationMap",
  () =>
    ({ onActiveChange }: any) => {
      mockChangeMode = onActiveChange;
      return null;
    },
);

it("keeps the existing map and basemap layers mounted while changing modes", () => {
  const { getByTestId, unmount } = render(<LiberationMap />);
  const map = getByTestId("main-map");
  const recentres = mockMap.setView.mock.calls.length;
  for (const active of [true, false, true, false])
    act(() => mockChangeMode(active));
  expect(getByTestId("main-map")).toBe(map);
  expect(mockLayersMounted).toHaveBeenCalledTimes(1);
  expect(mockLayersUnmounted).not.toHaveBeenCalled();
  expect(mockMap.setView).toHaveBeenCalledTimes(recentres);
  unmount();
  expect(mockLayersUnmounted).toHaveBeenCalledTimes(1);
});
