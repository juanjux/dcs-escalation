/**
 * The toggle beside the ruler, and what it does to the map while it is on.
 *
 * The ruler shows a crosshair while it is active so the player can see it is armed;
 * the picker does the same.
 */
import PickerToggle from "./PickerToggle";
import { act, render } from "@testing-library/react";

const mockContainer = document.createElement("div");
mockContainer.style.cursor = "grab";

// Enough of a Leaflet map for Control.addTo: the corner it appends the button to,
// and the events it registers.
const mockMap = {
  getContainer: () => mockContainer,
  _controlCorners: { topleft: document.createElement("div") },
  _controlContainer: document.createElement("div"),
  on: () => {},
  off: () => {},
};

jest.mock("react-leaflet", () => ({
  useMap: () => mockMap,
}));

beforeEach(() => {
  mockContainer.style.cursor = "grab";
});

it("puts a crosshair on the map while it is on", () => {
  render(<PickerToggle on={true} toggle={() => {}} />);

  expect(mockContainer.style.cursor).toBe("crosshair");
});

it("restores the map cursor when it is switched off", () => {
  const { rerender } = render(<PickerToggle on={true} toggle={() => {}} />);

  act(() => {
    rerender(<PickerToggle on={false} toggle={() => {}} />);
  });

  expect(mockContainer.style.cursor).toBe("grab");
});

it("leaves the cursor alone while it is off", () => {
  render(<PickerToggle on={false} toggle={() => {}} />);

  expect(mockContainer.style.cursor).toBe("grab");
});

it("restores the cursor if the map unmounts while it is on", () => {
  const { unmount } = render(<PickerToggle on={true} toggle={() => {}} />);

  act(() => {
    unmount();
  });

  expect(mockContainer.style.cursor).toBe("grab");
});
