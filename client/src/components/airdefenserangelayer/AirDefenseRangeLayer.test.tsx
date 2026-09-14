import { renderWithProviders } from "../../testutils";
import AirDefenseRangeLayer, { colorFor } from "./AirDefenseRangeLayer";
import { PropsWithChildren } from "react";

const mockLayerGroup = jest.fn();
const mockCircle = jest.fn();
jest.mock("react-leaflet", () => ({
  LayerGroup: (props: PropsWithChildren<any>) => {
    mockLayerGroup(props);
    return <>{props.children}</>;
  },
  Circle: (props: any) => {
    mockCircle(props);
  },
  Tooltip: (props: PropsWithChildren<any>) => <>{props.children}</>,
}));

describe("colorFor", () => {
  it("has a unique color for each configuration", () => {
    const params = [
      [false, false],
      [false, true],
      [true, false],
      [true, true],
    ];
    var colors = new Set<string>();
    for (const [blue, detection] of params) {
      colors.add(colorFor(blue, detection));
    }
    expect(colors.size).toEqual(4);
  });
});

describe("AirDefenseRangeLayer", () => {
  it("draws nothing when there are no TGOs", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />);
    expect(mockLayerGroup).toHaveBeenCalledTimes(1);
    expect(mockCircle).not.toHaveBeenCalled();
  });

  it("does not draw wrong range types", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />, {
      preloadedState: {
        tgos: {
          tgos: {
            foo: {
              id: "foo",
              name: "Foo",
              control_point_name: "Bar",
              category: "AA",
              blue: false,
              position: {
                lat: 0,
                lng: 0,
              },
              units: [],
              threat_ranges: [],
              detection_ranges: [20],
              dead: false,
              purchasable: true,
              sidc: "",
              mobile: false,
            },
          },
        },
      },
    });
    expect(mockLayerGroup).toHaveBeenCalledTimes(1);
    expect(mockCircle).not.toHaveBeenCalled();
  });

  it("draws threat ranges", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />, {
      preloadedState: {
        tgos: {
          tgos: {
            foo: {
              id: "foo",
              name: "Foo",
              control_point_name: "Bar",
              category: "AA",
              blue: true,
              position: {
                lat: 10,
                lng: 20,
              },
              units: [],
              threat_ranges: [10],
              detection_ranges: [20],
              dead: false,
              purchasable: true,
              sidc: "",
              mobile: false,
            },
          },
        },
      },
    });
    expect(mockLayerGroup).toHaveBeenCalledTimes(1);
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        center: {
          lat: 10,
          lng: 20,
        },
        radius: 10,
        color: colorFor(true, false),
      }),
    );
  });

  it("draws detection ranges", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} detection />, {
      preloadedState: {
        tgos: {
          tgos: {
            foo: {
              id: "foo",
              name: "Foo",
              control_point_name: "Bar",
              category: "AA",
              blue: true,
              position: {
                lat: 10,
                lng: 20,
              },
              units: [],
              threat_ranges: [10],
              detection_ranges: [20],
              dead: false,
              purchasable: true,
              sidc: "",
              mobile: false,
            },
          },
        },
      },
    });
    expect(mockLayerGroup).toHaveBeenCalledTimes(1);
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        center: {
          lat: 10,
          lng: 20,
        },
        radius: 20,
        color: colorFor(true, true),
      }),
    );
  });

  const radarOnlyState = (blue: boolean) => ({
    tgos: {
      tgos: {
        ewr: {
          id: "ewr",
          name: "Ewr",
          control_point_name: "Bar",
          category: "AA",
          blue: blue,
          position: { lat: 10, lng: 20 },
          units: [],
          threat_ranges: [],
          detection_ranges: [300],
          dead: false,
          purchasable: true,
          sidc: "",
          task: [],
          mobile: false,
        },
      },
    },
  });

  // A site that only detects has no threat ring, and its detection ring belongs on
  // the detection layer under the switch the player already has for it. Drawing it on
  // the threat layer dashed made a radar-only SAM look exactly like a GPS jammer.
  it("keeps a radar-only site off the threat layer", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />, {
      preloadedState: radarOnlyState(true) as any,
    });
    expect(mockCircle).not.toHaveBeenCalled();
  });

  it("draws a radar-only site on the detection layer", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} detection />, {
      preloadedState: radarOnlyState(true) as any,
    });
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        radius: 300,
        pathOptions: expect.objectContaining({ color: colorFor(true, true) }),
      }),
    );
  });

  const withIadsState = (
    state: string | null,
    blind = false,
    detection_ranges: number[] = [],
  ) => ({
    tgos: {
      tgos: {
        sam: {
          id: "sam",
          name: "Sam",
          control_point_name: "Bar",
          category: "AA",
          blue: false,
          position: { lat: 10, lng: 20 },
          units: [],
          threat_ranges: [500],
          detection_ranges,
          dead: false,
          purchasable: true,
          sidc: "",
          task: [],
          mobile: false,
          iads_state: state,
          iads_reason: "Because.",
          iads_blind: blind,
        },
      },
    },
  });

  // A site Skynet will not switch on gets no ring at all: it will not see and it will
  // not shoot for the whole mission, so drawing the circle it would have had is drawing
  // a threat that is not there.
  it("draws no ring at all for a dark site", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={false} />, {
      preloadedState: withIadsState("dark") as any,
    });
    expect(mockCircle).not.toHaveBeenCalled();
  });

  it("draws no detection ring for a dark site either", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={false} detection />, {
      preloadedState: withIadsState("dark", false, [400]) as any,
    });
    expect(mockCircle).not.toHaveBeenCalled();
  });

  // An autonomous site still shoots, at whatever its own radar finds, so its ring is
  // left exactly as it is. Dashing or recolouring it would say "jamming bubble".
  it("leaves an autonomous site's ring alone", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={false} />, {
      preloadedState: withIadsState("autonomous") as any,
    });
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        radius: 500,
        pathOptions: expect.objectContaining({
          color: colorFor(false, false),
          dashArray: undefined,
        }),
      }),
    );
  });

  it("leaves a shooting site's threat ring solid", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />, {
      preloadedState: {
        tgos: {
          tgos: {
            sam: {
              id: "sam",
              name: "Sam",
              control_point_name: "Bar",
              category: "AA",
              blue: true,
              position: { lat: 10, lng: 20 },
              units: [],
              threat_ranges: [10],
              detection_ranges: [20],
              dead: false,
              purchasable: true,
              sidc: "",
              task: [],
              mobile: false,
            },
          },
        },
      } as any,
    });
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        radius: 10,
        pathOptions: expect.objectContaining({ dashArray: undefined }),
      }),
    );
  });

  // A jamming site carries point defence, so it has a threat ring -- a couple of
  // miles where the bubble is tens. The bubble is the circle anyone is looking for.
  it("draws a jamming bubble dashed, alongside its point defence", () => {
    renderWithProviders(<AirDefenseRangeLayer blue={true} />, {
      preloadedState: {
        tgos: {
          tgos: {
            jam: {
              id: "jam",
              name: "Jam",
              control_point_name: "Bar",
              category: "AA",
              blue: true,
              position: { lat: 10, lng: 20 },
              units: [],
              threat_ranges: [4000],
              detection_ranges: [18000],
              jamming_range: 55560,
              dead: false,
              purchasable: true,
              sidc: "",
              task: [],
              mobile: false,
            },
          },
        },
      } as any,
    });
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        radius: 55560,
        pathOptions: expect.objectContaining({ dashArray: expect.any(String) }),
      }),
    );
    expect(mockCircle).toHaveBeenCalledWith(
      expect.objectContaining({
        radius: 4000,
        pathOptions: expect.objectContaining({ dashArray: undefined }),
      }),
    );
  });
});
