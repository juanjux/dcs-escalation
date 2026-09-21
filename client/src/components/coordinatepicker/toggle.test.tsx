/**
 * The toggle beside the ruler, and what it does to the map while it is on.
 *
 * A tool that is picked up has to look picked up: the ruler puts a crosshair on the
 * map for exactly that reason, and a picker that changes nothing leaves the player
 * clicking to find out whether it is armed.
 */
import PickerToggle from "./PickerToggle";
import { act, render } from "@testing-library/react";

const mockContainer = document.createElement("div");
mockContainer.style.cursor = "grab";

// Enough of a Leaflet map for Control.addTo: the corner it hangs the button in, and
// the event pair it registers on.
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

it("gives the map its own cursor back when it is put down", () => {
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

it("gives it back when the map goes away with the tool still up", () => {
  const { unmount } = render(<PickerToggle on={true} toggle={() => {}} />);

  act(() => {
    unmount();
  });

  expect(mockContainer.style.cursor).toBe("grab");
});
