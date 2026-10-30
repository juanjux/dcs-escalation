import { render } from "@testing-library/react";
import L from "leaflet";
import LiberationMap from "./LiberationMap";

let mockCenter = { lat: 0, lng: 0 };
let mockCampaignLoaded = false;

jest.mock("../../app/hooks", () => ({
  useAppSelector: (selector: any) =>
    selector({ map: { center: mockCenter, zoom: null } }),
}));
jest.mock("../maplayers/MapLayersControl", () => () => {
  const { Polygon } = require("react-leaflet");
  return mockCampaignLoaded ? (
    <Polygon
      positions={[
        [34, 69],
        [35, 69],
        [34, 70],
      ]}
    />
  ) : null;
});
jest.mock("../coordinatepicker", () => () => null);
jest.mock("../coordinatepicker/DrawMode", () => () => null);
jest.mock("../savedpointpins/SavedPointPins", () => () => null);
jest.mock("../mapsearch", () => () => null);
jest.mock("../maphover/MapButtonHover", () => () => null);
jest.mock("../ruler/Ruler", () => () => null);
jest.mock("../grounddestination/GroundDestinationMap", () => () => null);

beforeEach(() => {
  mockCenter = { lat: 0, lng: 0 };
  mockCampaignLoaded = false;
  (L.Browser as any).svg = true;
});

it("draws campaign polygons already available when the map mounts", () => {
  mockCenter = { lat: 34, lng: 69 };
  mockCampaignLoaded = true;
  const view = render(<LiberationMap />);
  expect(
    view.container.querySelector(".leaflet-overlay-pane svg path"),
  ).toBeInTheDocument();
  view.unmount();
});

it("draws campaign polygons arriving after the map mounts", () => {
  const view = render(<LiberationMap />);
  mockCenter = { lat: 34, lng: 69 };
  mockCampaignLoaded = true;
  view.rerender(<LiberationMap />);
  expect(
    view.container.querySelector(".leaflet-container"),
  ).toBeInTheDocument();
  expect(
    view.container.querySelector(".leaflet-overlay-pane svg path"),
  ).toBeInTheDocument();
  view.unmount();
});

it("draws campaign polygons even when the map center does not change", () => {
  const view = render(<LiberationMap />);
  mockCampaignLoaded = true;
  view.rerender(<LiberationMap />);
  expect(
    view.container.querySelector(".leaflet-overlay-pane svg path"),
  ).toBeInTheDocument();
  view.unmount();
});

it("recreates a ready vector renderer after the mission map is unloaded", () => {
  mockCampaignLoaded = true;
  const first = render(<LiberationMap />);
  expect(
    first.container.querySelector(".leaflet-overlay-pane svg path"),
  ).toBeInTheDocument();
  first.unmount();
  mockCenter = { lat: 33, lng: 68 };
  const restored = render(<LiberationMap />);
  expect(
    restored.container.querySelector(".leaflet-overlay-pane svg path"),
  ).toBeInTheDocument();
  restored.unmount();
});
