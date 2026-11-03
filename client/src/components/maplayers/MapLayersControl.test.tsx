import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import backend from "../../api/backend";
import { MapContainer } from "react-leaflet";
import { renderWithProviders } from "../../testutils";
import MapLayersControl from "./MapLayersControl";

jest.mock("react-esri-leaflet", () => ({ BasemapLayer: () => null }));
jest.mock("../../api/backend", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: { state: null } })),
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
  (backend.get as jest.Mock).mockResolvedValue({ data: { state: null } });
  (backend.put as jest.Mock).mockResolvedValue({});
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

async function renderPanel() {
  const rendered = renderWithProviders(
    <MapContainer center={[42, 41]} zoom={8}>
      <MapLayersControl />
    </MapContainer>,
  );
  await act(async () => {});
  fireEvent.click(
    screen.getByRole("button", { name: /Threat zones & destroyed/ }),
  );
  return rendered;
}

it("defaults new repairable filters to shown for old saved preferences", async () => {
  localStorage.setItem(
    "fjg.mapLayers.v2",
    JSON.stringify({ visible: { blueDestroyed: false, redDestroyed: false } }),
  );
  const { store } = await renderPanel();
  expect(screen.getByLabelText("Blue: destroyed (repairable)")).toBeChecked();
  expect(screen.getByLabelText("Red: destroyed (repairable)")).toBeChecked();
  expect(store.getState().map.showDestroyedRepairable).toEqual({
    blue: true,
    red: true,
  });
  expect(store.getState().map.showDestroyedNonRepairable).toEqual({
    blue: false,
    red: false,
  });
});

it("keeps both repairable filters independent and unchanged by presets", async () => {
  const { store } = await renderPanel();
  fireEvent.click(screen.getByLabelText("Blue: destroyed (repairable)"));
  expect(store.getState().map.showDestroyedRepairable).toEqual({
    blue: false,
    red: true,
  });
  expect(store.getState().map.showDestroyedNonRepairable).toEqual({
    blue: true,
    red: true,
  });
  for (const preset of ["SEAD", "Recon", "Clean", "Default"]) {
    fireEvent.click(screen.getByRole("button", { name: preset, exact: true }));
    expect(store.getState().map.showDestroyedRepairable).toEqual({
      blue: false,
      red: true,
    });
  }
  fireEvent.click(screen.getByLabelText("Red: destroyed (repairable)"));
  expect(store.getState().map.showDestroyedRepairable).toEqual({
    blue: false,
    red: false,
  });
  const cached = JSON.parse(localStorage.getItem("fjg.mapLayers.v2")!);
  expect(cached.visible.blueDestroyedRepairable).toBe(false);
  expect(cached.visible.redDestroyedRepairable).toBe(false);
  await waitFor(() =>
    expect(backend.put).toHaveBeenCalledWith("game/map-layers", {
      state: localStorage.getItem("fjg.mapLayers.v2"),
    }),
  );
});

it("restores repairable filters from the campaign over the local cache", async () => {
  localStorage.setItem(
    "fjg.mapLayers.v2",
    JSON.stringify({
      visible: { blueDestroyedRepairable: true, redDestroyedRepairable: false },
    }),
  );
  (backend.get as jest.Mock).mockResolvedValue({
    data: {
      state: JSON.stringify({
        visible: {
          blueDestroyedRepairable: false,
          redDestroyedRepairable: true,
        },
      }),
    },
  });
  const { store } = await renderPanel();
  expect(store.getState().map.showDestroyedRepairable).toEqual({
    blue: false,
    red: true,
  });
  expect(
    screen.getByLabelText("Blue: destroyed (repairable)"),
  ).not.toBeChecked();
  expect(screen.getByLabelText("Red: destroyed (repairable)")).toBeChecked();
});
