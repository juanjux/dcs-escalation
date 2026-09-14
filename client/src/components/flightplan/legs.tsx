import { Waypoint } from "../../api/liberationApi";
import {
  DivIcon,
  LatLng,
  LatLngLiteral,
  LeafletEventHandlerFnMap,
  latLng,
} from "leaflet";
import { ReactElement } from "react";
import { Marker, Polyline, useMap, useMapEvent } from "react-leaflet";
import { useReducer } from "react";

/** Where the flight releases, dashed and red so it reads as a run rather than a route. */
export const TARGET_PATH = "#d42a2a";

const METRES_PER_NAUTICAL_MILE = 1852;

/** How far the label sits from the line it belongs to. */
const LABEL_OFFSET = 13;

/** Legs shorter than this in pixels get no label: there is nowhere to put it. */
const MIN_LABELLED_PIXELS = 34;

export function distanceNm(from: LatLngLiteral, to: LatLngLiteral): number {
  return latLng(from).distanceTo(latLng(to)) / METRES_PER_NAUTICAL_MILE;
}

/** A tenth of a mile matters on a short run and is noise on a long one. */
export function legLabel(nm: number): string {
  return nm < 10 ? `${nm.toFixed(1)} NM` : `${nm.toFixed(0)} NM`;
}

/**
 * Which way to step off the line, in screen pixels.
 *
 * A steep leg takes its label to one side and a shallow one above, so the label is
 * never lying along the line it measures.
 */
export function labelOffset(dx: number, dy: number): [number, number] {
  return Math.abs(dy) > Math.abs(dx) ? [LABEL_OFFSET, 0] : [0, -LABEL_OFFSET];
}

interface LegProps {
  from: LatLngLiteral;
  to: LatLngLiteral;
  /** The dashed run to a target, which is worth telling apart from a nav leg. */
  toTarget?: boolean;
}

/**
 * The length of one leg, beside the line rather than on it.
 *
 * Which side depends on which way the leg runs: a steep leg takes its label to one
 * side, a shallow one above or below, so the label never lies along the line it is
 * measuring and never covers the leg after it.
 */
export function LegDistance(props: LegProps): ReactElement | null {
  const map = useMap();
  // The offset is in screen space, so it has to be worked out again after a zoom.
  const [, redraw] = useReducer((count: number) => count + 1, 0);
  useMapEvent("zoomend", redraw);

  const from = map.latLngToLayerPoint(props.from);
  const to = map.latLngToLayerPoint(props.to);
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.hypot(dx, dy) < MIN_LABELLED_PIXELS) {
    return null;
  }

  const offset = labelOffset(dx, dy);

  const middle: LatLng = latLng(
    (props.from.lat + props.to.lat) / 2,
    (props.from.lng + props.to.lng) / 2,
  );
  const nm = distanceNm(props.from, props.to);
  const classes = `leg-distance${props.toTarget ? " to-target" : ""}`;

  return (
    <Marker
      position={middle}
      interactive={false}
      keyboard={false}
      icon={
        new DivIcon({
          className: "",
          html: `<div class="${classes}">${legLabel(nm)}</div>`,
          // Half a line of text up, and then the step to the side, so the anchor is
          // the middle of the label rather than its corner.
          iconAnchor: [-offset[0], 7 + offset[1]],
        })
      }
    />
  );
}

/**
 * The run from the last point the flight navigates by to each thing it was sent to
 * attack.
 *
 * Dashed, because it is not a leg the flight flies as such -- there is no turn at
 * the far end -- and red, because it is the part of the plan that has to be inside
 * the weapon's reach.
 */
export function TargetRuns(props: {
  waypoints: Waypoint[];
  drawn: Waypoint[];
  /** The run's colour. The flight's own, when its plan is only part of the picture. */
  color?: string;
  /** How long each run is. Worth saying for the flight being worked on, and only it. */
  labelled?: boolean;
  /**
   * What to do with the mouse on a run, if anything. The run is part of the plan and
   * reads as part of it, so it answers the pointer like the rest of the route: it is
   * the leg nearest the target, and the one most likely to be pointed at.
   */
  handlers?: LeafletEventHandlerFnMap;
  /** Shown while the pointer is on a run, as on the route itself. */
  tooltip?: ReactElement;
}): ReactElement {
  const runs: ReactElement[] = [];
  for (const target of props.waypoints.filter((w) => w.is_target)) {
    const from = lastDrawnBefore(props.drawn, target.index);
    if (from == null) {
      continue;
    }
    runs.push(
      <Polyline
        key={`run-${target.index}`}
        positions={[from.position, target.position]}
        pathOptions={{
          color: props.color ?? TARGET_PATH,
          weight: 2,
          dashArray: "7 6",
          interactive: false,
        }}
      />,
    );
    if (props.handlers !== undefined) {
      // A wide, invisible twin catches the mouse, so a two-pixel dashed line is as
      // easy to hit as the route -- the same trick the route itself uses.
      runs.push(
        <Polyline
          key={`run-grab-${target.index}`}
          positions={[from.position, target.position]}
          pathOptions={{ weight: 16, opacity: 0, interactive: true }}
          eventHandlers={props.handlers}
        >
          {props.tooltip}
        </Polyline>,
      );
    }
    if (props.labelled) {
      runs.push(
        <LegDistance
          key={`run-label-${target.index}`}
          from={from.position}
          to={target.position}
          toTarget
        />,
      );
    }
  }
  return <>{runs}</>;
}

/** The last point on the drawn route before this index: where the run starts from. */
function lastDrawnBefore(drawn: Waypoint[], index: number): Waypoint | null {
  let best: Waypoint | null = null;
  for (const waypoint of drawn) {
    if (waypoint.index < index) {
      best = waypoint;
    }
  }
  return best;
}
