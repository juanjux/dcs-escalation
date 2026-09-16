/**
 * A popup written as a child of a marker is bound to it and stays closed: react-leaflet
 * only opens the ones that hang from the map. The point was clicked, so it has to open
 * by itself.
 */
import CoordinatePicker from "./CoordinatePicker";
import { act, render } from "@testing-library/react";

const mockOpenPopup = jest.fn();
const mockHandlers: Record<string, (event: any) => void> = {};

jest.mock("react-leaflet", () => {
  // Required inside the factory: jest hoists it above the imports.
  const react = require("react");
  return {
    Marker: react.forwardRef((props: any, ref: any) => {
      if (ref) {
        ref.current = { openPopup: mockOpenPopup };
      }
      return react.createElement("div", null, props.children);
    }),
    Popup: (props: any) => react.createElement("div", null, props.children),
    useMapEvent: (name: string, handler: (event: any) => void) => {
      mockHandlers[name] = handler;
    },
  };
});

describe("the coordinate popup", () => {
  beforeEach(() => {
    mockOpenPopup.mockClear();
    global.fetch = jest.fn().mockResolvedValue({
      json: async () => ({ text: "N36°35.316' W115°40.416'", all: {} }),
    }) as any;
  });

  async function clickTheMap() {
    render(<CoordinatePicker />);
    await act(async () => {
      await mockHandlers.click({
        latlng: { lat: 36.5886, lng: -115.6736 },
        originalEvent: { target: document.createElement("div") },
      });
    });
  }

  it("opens where the map was clicked", async () => {
    await clickTheMap();

    expect(mockOpenPopup).toHaveBeenCalled();
  });

  it("asks the server for the coordinates of that point", async () => {
    await clickTheMap();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("coordinates/?lat=36.5886&lng=-115.6736"),
    );
  });
});
