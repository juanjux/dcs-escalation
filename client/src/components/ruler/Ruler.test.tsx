import { render } from "@testing-library/react";
import L from "leaflet";
import LeafletRuler from "./Ruler";

const mockMap = { removeLayer: jest.fn() };
jest.mock("react-leaflet", () => ({ useMap: () => mockMap }));
jest.mock("leaflet-ruler", () => ({}));

it.each([false, true])(
  "releases ruler controls and active handlers on mode change (%s)",
  (active) => {
    const control = {
      _choice: active,
      _toggleMeasure: jest.fn(),
      _tempLine: {},
      _tempPoint: {},
      remove: jest.fn(),
      addTo: jest.fn(),
    };
    control.addTo.mockReturnValue(control);
    Object.assign(L.control, { ruler: jest.fn(() => control) });
    const { unmount } = render(<LeafletRuler />);
    unmount();
    expect(control._toggleMeasure).toHaveBeenCalledTimes(active ? 1 : 0);
    expect(mockMap.removeLayer).toHaveBeenCalledWith(control._tempLine);
    expect(mockMap.removeLayer).toHaveBeenCalledWith(control._tempPoint);
    expect(control.remove).toHaveBeenCalledTimes(1);
  },
);
