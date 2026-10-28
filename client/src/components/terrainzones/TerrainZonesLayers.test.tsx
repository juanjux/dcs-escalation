import { renderWithProviders } from "../../testutils";
import { ExclusionZonesLayer } from "./TerrainZonesLayers";

const mockPolygon = jest.fn();
jest.mock("react-leaflet", () => ({
  LayerGroup: ({ children }: any) => children,
  Polygon: (props: any) => {
    mockPolygon(props);
    return null;
  },
}));

const outer = [
  { lat: 32, lng: 66 },
  { lat: 32, lng: 67 },
  { lat: 33, lng: 67 },
  { lat: 32, lng: 66 },
];
const hole = [
  { lat: 32.2, lng: 66.2 },
  { lat: 32.2, lng: 66.4 },
  { lat: 32.4, lng: 66.4 },
  { lat: 32.2, lng: 66.2 },
];
const polygon = [outer, hole];

beforeEach(() => mockPolygon.mockClear());

it("renders movement exclusions with transparent fill and non-interactive outlines", () => {
  renderWithProviders(<ExclusionZonesLayer movement />, {
    preloadedState: {
      mapZones: { mapZones: { exclusion: [polygon], inclusion: [], sea: [] } },
    },
  });
  expect(mockPolygon).toHaveBeenCalledWith(
    expect.objectContaining({
      positions: polygon,
      fillOpacity: 0.18,
      color: "#ff886b",
      fillColor: "#ff6655",
      interactive: false,
      dashArray: "6 4",
    }),
  );
});

it("keeps the normal terrain layer appearance unchanged", () => {
  renderWithProviders(<ExclusionZonesLayer />, {
    preloadedState: {
      mapZones: { mapZones: { exclusion: [polygon], inclusion: [], sea: [] } },
    },
  });
  expect(mockPolygon).toHaveBeenCalledWith(
    expect.objectContaining({
      positions: polygon,
      fillOpacity: 1,
      color: "#969696",
      fillColor: "#303030",
      interactive: false,
    }),
  );
});

it("does not draw zones that are absent from the current campaign", () => {
  renderWithProviders(<ExclusionZonesLayer movement />);
  expect(mockPolygon).not.toHaveBeenCalled();
});
