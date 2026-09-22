/**
 * A popup written as a child of a marker is bound to it and stays closed: react-leaflet
 * only opens the ones that hang from the map. The point was clicked, so it has to open
 * by itself.
 */
import CoordinatePicker from "./CoordinatePicker";
import { act, render } from "@testing-library/react";

const mockOpenPopup = jest.fn();
const mockHandlers: Record<string, (event: any) => void> = {};
const mockToggle: { flip?: () => void; on?: boolean } = {};

jest.mock("./PickerToggle", () => (props: any) => {
  mockToggle.flip = props.toggle;
  mockToggle.on = props.on;
  return null;
});

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
    useMap: () => ({}),
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
    await act(async () => {
      await mockHandlers.click({
        latlng: { lat: 36.5886, lng: -115.6736 },
        originalEvent: { target: document.createElement("div") },
      });
    });
  }

  async function pickUpTheTool() {
    render(<CoordinatePicker />);
    await act(async () => {
      mockToggle.flip?.();
    });
  }

  it("opens where the map was clicked", async () => {
    await pickUpTheTool();

    await clickTheMap();

    expect(mockOpenPopup).toHaveBeenCalled();
  });

  it("asks the server for the coordinates of that point", async () => {
    await pickUpTheTool();

    await clickTheMap();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("coordinates/?lat=36.5886&lng=-115.6736"),
    );
  });

  it("does nothing until it is switched on", async () => {
    // Every stray click used to open a popup.
    render(<CoordinatePicker />);

    await clickTheMap();

    expect(global.fetch).not.toHaveBeenCalled();
    expect(mockOpenPopup).not.toHaveBeenCalled();
  });

  it("starts switched off", async () => {
    render(<CoordinatePicker />);

    expect(mockToggle.on).toBe(false);
  });

  it("switching it off closes the open point", async () => {
    await pickUpTheTool();
    await clickTheMap();
    (global.fetch as jest.Mock).mockClear();
    mockOpenPopup.mockClear();

    await act(async () => {
      mockToggle.flip?.();
    });

    expect(mockToggle.on).toBe(false);
    await clickTheMap();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(mockOpenPopup).not.toHaveBeenCalled();
  });
});
