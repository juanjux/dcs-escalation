import { renderWithProviders } from "../../testutils";
import FlightPlansLayer, { SelectedFlightPlanLayer } from "./FlightPlansLayer";
import { PropsWithChildren } from "react";

const mockPolyline = jest.fn();
const mockLayerGroup = jest.fn();
const mockMarker = jest.fn();
jest.mock("react-leaflet", () => ({
  LayerGroup: (props: PropsWithChildren<any>) => {
    mockLayerGroup(props);
    return <>{props.children}</>;
  },
  Polyline: (props: any) => {
    mockPolyline(props);
  },
  // The route reads the map to work out which leg an alt-click landed on, and the
  // leg labels read it to decide which side of the line to sit on. Only the
  // projection is needed; no test here clicks or zooms.
  useMap: () => ({
    latLngToLayerPoint: ({ lat, lng }: { lat: number; lng: number }) => ({
      x: lng,
      y: lat,
    }),
  }),
  useMapEvent: () => undefined,
  Marker: (props: any) => {
    mockMarker(props);
    return null;
  },
}));

// The waypoints in test data below should all use `should_make: false`. Markers
// need useMap() to check the zoom level to decide if they should be drawn or
// not, and we don't have good options here for mocking that behavior.
describe("FlightPlansLayer", () => {
  describe("unselected flights", () => {
    it("are drawn", () => {
      renderWithProviders(<FlightPlansLayer blue={true} />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
              bar: {
                id: "bar",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: null,
          },
        },
      });

      // Each drawn blue flight renders two polylines now: the visible route and
      // a wide invisible hover overlay. Passing a ref to the visible one also
      // causes a redraw, so these counts are higher than the flight count. (It
      // probably needs to be rewritten without mocks.)
      expect(mockPolyline).toHaveBeenCalledTimes(5);
      expect(mockLayerGroup).toBeCalledTimes(2);
    });
    it("are not drawn if wrong coalition", () => {
      renderWithProviders(<FlightPlansLayer blue={true} />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
              bar: {
                id: "bar",
                blue: false,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: null,
          },
        },
      });
      expect(mockPolyline).toHaveBeenCalledTimes(2);
      expect(mockLayerGroup).toBeCalledTimes(1);
    });
    it("are not drawn by the selected-plan layer", () => {
      renderWithProviders(<SelectedFlightPlanLayer />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: null,
          },
        },
      });
      expect(mockPolyline).not.toHaveBeenCalled();
      expect(mockLayerGroup).toBeCalledTimes(1);
    });
  });
  describe("selected flights", () => {
    it("are drawn by their own layer", () => {
      renderWithProviders(<SelectedFlightPlanLayer />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
              bar: {
                id: "bar",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: "foo",
          },
        },
      });
      expect(mockPolyline).toHaveBeenCalledTimes(2);
      expect(mockLayerGroup).toBeCalledTimes(1);
    });
    it("are left to that layer by the side layers, so never drawn twice", () => {
      renderWithProviders(<FlightPlansLayer blue={true} />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: true,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: "foo",
          },
        },
      });
      expect(mockPolyline).not.toHaveBeenCalled();
      expect(mockLayerGroup).toBeCalledTimes(1);
    });
    it("are drawn whatever side they are on", () => {
      renderWithProviders(<SelectedFlightPlanLayer />, {
        preloadedState: {
          flights: {
            flights: {
              foo: {
                id: "foo",
                blue: false,
                sidc: "",
                waypoints: [
                  {
                    name: "",
                    position: {
                      lat: 0,
                      lng: 0,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                  {
                    name: "",
                    position: {
                      lat: 1,
                      lng: 1,
                    },
                    altitude_ft: 0,
                    altitude_reference: "MSL",
                    is_movable: true,
                    should_mark: false,
                    include_in_path: true,
                    is_target: false,
                    shows_altitude: true,
                    timing: "",
                    index: 0,
                    can_delete: false,
                    speed_kts: 0,
                  },
                ],
              },
            },
            selected: "foo",
          },
        },
      });
      expect(mockPolyline).toHaveBeenCalled();
      expect(mockLayerGroup).toBeCalledTimes(1);
    });
  });
  it("are not drawn if there are no flights", () => {
    renderWithProviders(<FlightPlansLayer blue={true} />);
    expect(mockPolyline).not.toHaveBeenCalled();
    expect(mockLayerGroup).toBeCalledTimes(1);
  });
});
