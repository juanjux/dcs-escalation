import { Flight, Waypoint } from "../../api/liberationApi";
import {
  useGetCommitBoundaryForFlightQuery,
  useInsertWaypointMutation,
  useDeleteWaypointMutation,
  useOpenTgoInfoDialogMutation,
  useSelectFlightMutation,
} from "../../api/liberationApi";
import WaypointMarker from "../waypointmarker";
import { WaypointDialog, WaypointMenu, WaypointTarget } from "../waypointmenu";
import { LegDistance, TargetRuns } from "./legs";
import { LineUtil, Polyline as LPolyline, LeafletMouseEvent } from "leaflet";
import { ReactElement, useEffect, useRef, useState } from "react";
import { Polyline, Tooltip, useMap } from "react-leaflet";

const BLUE_PATH = "#0084ff";
const RED_PATH = "#c85050";
const SELECTED_PATH = "#ffff00";

interface FlightPlanProps {
  flight: Flight;
  selected: boolean;
  highlight?: boolean;
}

const pathColor = (props: FlightPlanProps) => {
  if (props.selected && props.highlight) {
    return SELECTED_PATH;
  } else if (props.flight.blue) {
    return BLUE_PATH;
  } else {
    return RED_PATH;
  }
};

// Hover summary of a package's intent: callsign / composition, task, target and
// time-over-target. Fields are optional so it degrades gracefully if the server
// hasn't supplied them (older data); the live server always populates them.
function FlightTooltip({ flight }: { flight: Flight }) {
  const composition =
    flight.aircraft != null
      ? `${flight.num_aircraft ?? "?"}x ${flight.aircraft}`
      : null;
  return (
    <Tooltip sticky className="tooltip-delayed">
      <b>{flight.callsign || composition || "Flight"}</b>
      {flight.flight_type ? ` - ${flight.flight_type}` : ""}
      {flight.callsign && composition ? <div>{composition}</div> : null}
      {flight.package_target ? (
        <div>
          Target: {flight.package_target}
          {flight.package_tot ? ` (TOT ${flight.package_tot})` : ""}
        </div>
      ) : null}
    </Tooltip>
  );
}

interface PathProps extends FlightPlanProps {
  onError: (message: string) => void;
}

function FlightPlanPath(props: PathProps) {
  const color = pathColor(props);
  const waypoints = props.flight.waypoints;
  const [selectFlight] = useSelectFlightMutation();
  const [insertWaypoint] = useInsertWaypointMutation();
  const map = useMap();

  const polylineRef = useRef<LPolyline | null>(null);

  // Flight paths should be drawn under everything else. There seems to be an
  // issue where `interactive: false` doesn't do as its told (there's nuance,
  // see the bug for details). It looks better if we draw the other elements on
  // top of the flight plans anyway, so just push the flight plan to the back.
  //
  // https://github.com/dcs-liberation/dcs_liberation/issues/3295
  //
  // It's not possible to z-index a polyline (and leaflet says it never will be,
  // because this is a limitation of SVG, not leaflet:
  // https://github.com/Leaflet/Leaflet/issues/185), so we need to use
  // bringToBack() to push the flight paths to the back of the drawing once
  // they've been added to the map. They'll still draw on top of the map, but
  // behind everything than was added before them. Anything added after always
  // goes on top.
  useEffect(() => {
    if (props.selected) {
      polylineRef.current?.bringToFront();
    } else {
      polylineRef.current?.bringToBack();
    }
  });

  if (waypoints == null) {
    return <></>;
  }
  const drawn = waypoints.filter((waypoint) => waypoint.include_in_path);
  const points = drawn.map((waypoint) => waypoint.position);

  // Only blue flight plans are interactive: hovering highlights the route in
  // yellow and clicking selects the owning package (and flight) in the Qt
  // sidebar via a round-trip through the server.
  const interactive = props.flight.blue;

  // The thin visible route never catches the mouse itself. For blue flights a
  // wide, invisible overlay polyline sits on top and handles hover (yellow
  // highlight + tooltip) and the click-to-select, so the route is easy to grab
  // without looking any thicker -- the same trick the SAM rings use.
  const visible = (
    <Polyline
      positions={points}
      pathOptions={{ color: color, interactive: false }}
      ref={polylineRef}
    />
  );

  // Every flight drawn on the map shows what it is going in against, not only the one
  // being worked on: that is how you see at a glance which targets already have
  // somebody on them. The run to the target is red for the selected flight, where it
  // is the thing you are looking at, and the flight's own colour in the crowd.
  const runs = (
    <TargetRuns
      waypoints={waypoints}
      drawn={drawn}
      color={props.selected ? undefined : color}
      labelled={props.selected}
    />
  );

  if (!interactive) {
    return (
      <>
        {visible}
        {runs}
      </>
    );
  }

  return (
    <>
      {visible}
      {runs}
      {props.selected && (
        <>
          {drawn.slice(0, -1).map((waypoint, index) => (
            <LegDistance
              key={`leg-${waypoint.index}`}
              from={waypoint.position}
              to={drawn[index + 1].position}
            />
          ))}
        </>
      )}
      <Polyline
        positions={points}
        pathOptions={{
          color: color,
          weight: 16,
          opacity: 0,
          interactive: true,
        }}
        eventHandlers={{
          mouseover: () => {
            polylineRef.current?.setStyle({ color: SELECTED_PATH });
            polylineRef.current?.bringToFront();
          },
          mouseout: () => {
            if (!props.selected) {
              polylineRef.current?.setStyle({ color: color });
              polylineRef.current?.bringToBack();
            }
          },
          click: async (event: LeafletMouseEvent) => {
            if (!event.originalEvent.altKey) {
              selectFlight({ flightId: props.flight.id });
              return;
            }
            // Alt-click on the route draws a new nav point into it, where the
            // pointer is, on the leg the pointer is over. Without this the only way
            // to bend a route around something was to add a waypoint in the flight
            // editor and then drag it across the map.
            const after = legUnderPointer(map, drawn, event);
            if (after == null) {
              return;
            }
            try {
              await insertWaypoint({
                flightId: props.flight.id,
                waypointIdx: after,
                waypointInsert: {
                  before: false,
                  position: { lat: event.latlng.lat, lng: event.latlng.lng },
                },
              }).unwrap();
            } catch (error) {
              props.onError(refusalFrom(error));
            }
          },
        }}
      >
        <FlightTooltip flight={props.flight} />
      </Polyline>
    </>
  );
}

interface MarkersProps extends FlightPlanProps {
  selectedWaypoint: number | null;
  onSelect: (index: number | null) => void;
  onOpen: (target: WaypointTarget) => void;
  onMenu: (target: WaypointTarget) => void;
}

const WaypointMarkers = (props: MarkersProps) => {
  if (!props.selected || props.flight.waypoints == null) {
    return <></>;
  }

  var markers: ReactElement[] = [];
  props.flight.waypoints?.forEach((p, idx) => {
    if (p.should_mark) {
      markers.push(
        <WaypointMarker
          key={idx}
          number={idx}
          waypoint={p}
          flight={props.flight}
          selected={props.selectedWaypoint === p.index}
          onSelect={() => props.onSelect(p.index)}
          onOpen={(at) =>
            props.onOpen({ flight: props.flight, waypoint: p, at })
          }
          onMenu={(at) =>
            props.onMenu({ flight: props.flight, waypoint: p, at })
          }
        />,
      );
    }
  });

  return <>{markers}</>;
};

interface CommitBoundaryProps {
  flightId: string;
  selected: boolean;
}

function CommitBoundary(props: CommitBoundaryProps) {
  const { data, error, isLoading } = useGetCommitBoundaryForFlightQuery(
    {
      flightId: props.flightId,
    },
    // RTK Query doesn't seem to allow us to invalidate the cache from anything
    // but a mutation, but this data can be invalidated by events from the
    // websocket. Just disable the cache for this.
    //
    // This isn't perfect. It won't redraw until the component remounts. There
    // doesn't appear to be a better way.
    { refetchOnMountOrArgChange: true },
  );
  if (isLoading) {
    return <></>;
  }
  if (error) {
    console.error(`Error loading commit boundary for ${props.flightId}`, error);
    return <></>;
  }
  if (!data) {
    console.log(
      `Null response data when loading commit boundary for ${props.flightId}`,
    );
    return <></>;
  }
  return (
    <Polyline positions={data} color="#ffff00" weight={1} interactive={false} />
  );
}

function CommitBoundaryIfSelected(props: CommitBoundaryProps) {
  if (!props.selected) {
    return <></>;
  }
  return <CommitBoundary {...props} />;
}

/** What came back from the server when it refused, in the words it refused with. */
function refusalFrom(error: unknown): string {
  const detail = (error as { data?: { detail?: string } })?.data?.detail;
  return typeof detail === "string" ? detail : "The server refused that.";
}

/**
 * Where a new nav point goes for an alt-click at this spot, or null if the route has
 * no leg to put one in.
 *
 * The answer is an index in the full route, not in the drawn one: a leg can span
 * waypoints that are not drawn -- the targets between an ingress and a split -- and
 * the new point belongs after the last of them, so the attack run is left alone and
 * it is the leg you can see that bends.
 */
export function legUnderPointer(
  map: ReturnType<typeof useMap>,
  drawn: Waypoint[],
  event: LeafletMouseEvent,
): number | null {
  if (drawn.length < 2) {
    return null;
  }
  // In screen space, so "nearest" means nearest to look at rather than nearest in
  // degrees, which near the poles is not the same thing.
  const pointer = map.latLngToLayerPoint(event.latlng);
  let best: number | null = null;
  let bestDistance = Infinity;
  for (let i = 0; i < drawn.length - 1; i++) {
    const from = map.latLngToLayerPoint(drawn[i].position);
    const to = map.latLngToLayerPoint(drawn[i + 1].position);
    const distance = LineUtil.pointToSegmentDistance(pointer, from, to);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = drawn[i + 1].index - 1;
    }
  }
  return best;
}

export default function FlightPlan(props: FlightPlanProps) {
  const [selectedWaypoint, setSelectedWaypoint] = useState<number | null>(null);
  const [menu, setMenu] = useState<WaypointTarget | null>(null);
  const [dialog, setDialog] = useState<{
    target: WaypointTarget;
    renaming: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteWaypoint] = useDeleteWaypointMutation();
  const [openTgoInfo] = useOpenTgoInfoDialogMutation();

  // Delete removes the selected waypoint, the same key that removes it in the
  // flight editor's list, in the package list and in the flights list. Asked first,
  // because there is no undo, and refused out loud when the plan will not give it up.
  useEffect(() => {
    if (!props.selected || selectedWaypoint == null) {
      return;
    }
    const onKey = async (event: KeyboardEvent) => {
      if (event.key !== "Delete" || menu != null || dialog != null) {
        return;
      }
      const target = document.activeElement;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLSelectElement
      ) {
        return;
      }
      const waypoint = props.flight.waypoints?.find(
        (w) => w.index === selectedWaypoint,
      );
      if (waypoint == null) {
        return;
      }
      if (!waypoint.can_delete) {
        setError(
          `${waypoint.name} is part of this flight's plan. It can be removed from ` +
            "the flight's waypoint tab, which can rebuild the plan around it.",
        );
        return;
      }
      if (!window.confirm(`Delete ${waypoint.name}?`)) {
        return;
      }
      setSelectedWaypoint(null);
      try {
        await deleteWaypoint({
          flightId: props.flight.id,
          waypointIdx: waypoint.index,
        }).unwrap();
      } catch (e) {
        setError(refusalFrom(e));
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [
    props.selected,
    props.flight,
    selectedWaypoint,
    menu,
    dialog,
    deleteWaypoint,
  ]);

  return (
    <>
      <FlightPlanPath {...props} onError={setError} />
      <WaypointMarkers
        {...props}
        selectedWaypoint={selectedWaypoint}
        onSelect={setSelectedWaypoint}
        onOpen={(target) => setDialog({ target: target, renaming: false })}
        onMenu={setMenu}
      />
      <CommitBoundaryIfSelected
        flightId={props.flight.id}
        selected={props.selected}
      />
      {menu && (
        <WaypointMenu
          target={menu}
          onOpenTarget={() => {
            if (menu.waypoint.target_id) {
              openTgoInfo({ tgoId: menu.waypoint.target_id });
            }
            setMenu(null);
          }}
          onOpenDialog={() => {
            setDialog({ target: menu, renaming: false });
            setMenu(null);
          }}
          onRename={() => {
            setDialog({ target: menu, renaming: true });
            setMenu(null);
          }}
          onClose={() => setMenu(null)}
          onError={setError}
        />
      )}
      {dialog && (
        <WaypointDialog
          target={dialog.target}
          renaming={dialog.renaming}
          onClose={() => setDialog(null)}
          onError={setError}
        />
      )}
      {error && (
        <WaypointError message={error} onClose={() => setError(null)} />
      )}
    </>
  );
}

function WaypointError(props: { message: string; onClose: () => void }) {
  useEffect(() => {
    const id = setTimeout(props.onClose, 6000);
    return () => clearTimeout(id);
  });
  return (
    <div className="wp-toast" onClick={props.onClose}>
      {props.message}
    </div>
  );
}
