import { act, screen } from "@testing-library/react";
import { MapContainer } from "react-leaflet";
import { renderWithProviders } from "../../testutils";
import MapLayersControl from "./MapLayersControl";

jest.mock("react-esri-leaflet", () => ({ BasemapLayer: () => null }));
jest.mock("../../api/backend", () => ({
  __esModule: true,
  default: {
    get: () => Promise.resolve({ data: { state: null } }),
    put: jest.fn(() => Promise.resolve()),
  },
}));
jest.mock("../terrainzones/TerrainZonesLayers", () => ({
  InclusionZonesLayer: () => null,
  ExclusionZonesLayer: () => <div data-testid="existing-exclusions" />,
  SeaZonesLayer: () => null,
}));

beforeEach(() => {
  localStorage.clear();
});

it.each([true, false])(
  "temporarily enables the existing exclusion layer without changing saved visibility (%s)",
  async (saved) => {
    localStorage.setItem(
      "fjg.mapLayers.v2",
      JSON.stringify({ visible: { exclusionZones: saved } }),
    );
    function view(selecting: boolean) {
      return (
        <MapContainer center={[42, 41]} zoom={8}>
          <MapLayersControl groundDestination={selecting} />
        </MapContainer>
      );
    }
    const rendered = renderWithProviders(view(false));
    await act(async () => {});
    const before = screen.queryByTestId("existing-exclusions");
    expect(screen.queryAllByTestId("existing-exclusions")).toHaveLength(
      saved ? 1 : 0,
    );
    for (const selecting of [true, false, true, false]) {
      rendered.rerender(view(selecting));
      expect(screen.queryAllByTestId("existing-exclusions")).toHaveLength(
        selecting || saved ? 1 : 0,
      );
      if (saved) expect(screen.getByTestId("existing-exclusions")).toBe(before);
      expect(
        JSON.parse(localStorage.getItem("fjg.mapLayers.v2")!).visible
          .exclusionZones,
      ).toBe(saved);
    }
  },
);
