import DrawMode from "./DrawMode";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import L from "leaflet";
import { useEffect } from "react";
import { MapContainer, useMap } from "react-leaflet";

let map: L.Map;
function Capture() {
  const instance = useMap();
  useEffect(() => {
    map = instance;
  }, [instance]);
  return null;
}
beforeEach(() => {
  global.fetch = jest
    .fn()
    .mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: "flight",
          callsign: "Hawg",
          aircraft: "A-10C",
          departure: "Base",
        },
      ],
    });
  (L.Browser as any).svg = true;
});

it("collects real Leaflet clicks, undoes a vertex, cancels for GPS and restores zoom", async () => {
  const view = render(
    <MapContainer center={[42, 42]} zoom={8}>
      <Capture />
      <DrawMode />
    </MapContainer>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Draw on map" }));
  await screen.findByText("Hawg · A-10C · Base");
  expect(map.doubleClickZoom.enabled()).toBe(false);
  await act(async () => {
    map.fire("click", {
      latlng: L.latLng(42, 42),
      originalEvent: { target: document.body },
    });
    map.fire("click", {
      latlng: L.latLng(43, 43),
      originalEvent: { target: document.body },
    });
    map.fire("click", {
      latlng: L.latLng(44, 42),
      originalEvent: { target: document.body },
    });
  });
  expect(screen.getByText("Drawing · 3/64 vertices")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Undo"));
  expect(screen.getByText("Drawing · 2/64 vertices")).toBeInTheDocument();
  act(() => {
    window.dispatchEvent(new Event("gps-picker-activated"));
  });
  await waitFor(() =>
    expect(screen.queryByText("Save line")).not.toBeInTheDocument(),
  );
  expect(map.doubleClickZoom.enabled()).toBe(true);
  view.unmount();
});
