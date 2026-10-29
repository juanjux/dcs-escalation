import { act, render } from "@testing-library/react";
import LiberationMap from "./LiberationMap";
jest.mock("../coordinatepicker/DrawMode", () => () => null);

const mockMap = { setView: jest.fn(), getZoom: () => 8 };
const mockLayersMounted = jest.fn();
const mockLayersUnmounted = jest.fn();
const mockGroundDestination = jest.fn();
let mockChangeMode: (active: boolean, mode?: "ground" | "missile") => void;
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
  return ({ groundDestination }: any) => {
    mockGroundDestination(groundDestination);
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
jest.mock("../maphover/MapButtonHover", () => () => null);
jest.mock("../ruler/Ruler", () => () => null);
jest.mock(
  "../grounddestination/GroundDestinationMap",
  () =>
    ({ onActiveChange }: any) => {
      mockChangeMode = onActiveChange;
      return null;
    },
);

it("forces exclusions only for ground selection and clears the override on exit", () => {
  render(<LiberationMap />);
  expect(mockGroundDestination).toHaveBeenLastCalledWith(false);
  act(() => mockChangeMode(true));
  expect(mockGroundDestination).toHaveBeenLastCalledWith(false);
  act(() => mockChangeMode(true, "ground"));
  expect(mockGroundDestination).toHaveBeenLastCalledWith(true);
  act(() => mockChangeMode(false));
  expect(mockGroundDestination).toHaveBeenLastCalledWith(false);
  act(() => mockChangeMode(true, "missile"));
  expect(mockGroundDestination).toHaveBeenLastCalledWith(false);
});

it("keeps the existing map and basemap layers mounted while changing modes", () => {
  const { getByTestId, unmount } = render(<LiberationMap />);
  const map = getByTestId("main-map");
  const recentres = mockMap.setView.mock.calls.length;
  const changeMode = mockChangeMode;
  for (const active of [true, false, true, false])
    act(() => changeMode(active));
  expect(getByTestId("main-map")).toBe(map);
  expect(mockLayersMounted).toHaveBeenCalledTimes(1);
  expect(mockLayersUnmounted).not.toHaveBeenCalled();
  expect(mockMap.setView).toHaveBeenCalledTimes(recentres);
  unmount();
  expect(mockLayersUnmounted).toHaveBeenCalledTimes(1);
});
