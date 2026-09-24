import {
  Flight,
  Waypoint,
  useOpenTgoInfoDialogMutation,
  useSetWaypointPositionMutation,
} from "../../api/liberationApi";
import "./WaypointMarker.css";
import { Icon } from "leaflet";
import { Marker as LMarker } from "leaflet";
import icon from "leaflet/dist/images/marker-icon.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";
import { MutableRefObject, useCallback, useEffect, useRef } from "react";
import { Marker, Tooltip, useMap, useMapEvent } from "react-leaflet";

/**
 * The colour of a waypoint's pin, or null for Leaflet's own blue. Red where the
 * flight works: its target, its track or orbit, the ingress of an attack. Green where
 * it refuels, orange where it holds or joins the package.
 */
export function tintFor(waypoint: Waypoint): string | null {
  if (waypoint.is_target) {
    return "red";
  }
  switch (waypoint.pin) {
    case "track":
    case "ingress":
      return "red";
    case "refuel":
      return "green";
    case "hold":
      return "orange";
    default:
      return null;
  }
}

// One icon per colour and selection, made the first time it is asked for. Every pin
// is Leaflet's one marker image; the classes recolour and light it up.
const ICONS = new Map<string, Icon>();

export function iconFor(waypoint: Waypoint, selected: boolean): Icon {
  const tint = tintFor(waypoint);
  const key = `${tint}:${selected}`;
  let found = ICONS.get(key);
  if (found === undefined) {
    const classes = ["wp-pin"];
    if (tint !== null) {
      classes.push(`wp-pin-${tint}`);
    }
    if (selected) {
      classes.push("wp-pin-selected");
    }
    found = new Icon({
      iconUrl: icon,
      shadowUrl: iconShadow,
      iconAnchor: [12, 41],
      className: classes.join(" "),
    });
    ICONS.set(key, found);
  }
  return found;
}

/**
 * What the tooltip says about a waypoint.
 *
 * The altitude is left out where it is not a height the flight flies at: a target's
 * is the ground it stands on and a takeoff's is the airfield, and "0 ft RADIO" on a
 * target reads as a setting rather than as a fact about the terrain.
 */
export function tooltipFor(waypoint: Waypoint, number: number): string {
  const lines = [`${number - 1} ${waypoint.name}`];
  if (waypoint.shows_altitude) {
    lines.push(
      `${waypoint.altitude_ft.toFixed()} ft ${waypoint.altitude_reference}`,
    );
  }
  if (waypoint.timing) {
    lines.push(waypoint.timing);
  }
  return lines.join("<br />");
}

interface WaypointMarkerProps {
  number: number;
  waypoint: Waypoint;
  flight: Flight;
  selected: boolean;
  onSelect: () => void;
  onOpen: (at: { x: number; y: number }) => void;
  onMenu: (at: { x: number; y: number }) => void;
}

const WaypointMarker = (props: WaypointMarkerProps) => {
  // Most props of react-leaflet types are immutable and components will not
  // update to account for changes, so we can't simply use the `permanent`
  // property of the tooltip to control tooltip visibility based on the zoom
  // level.
  //
  // On top of that, listening for zoom changes and opening/closing is not
  // sufficient because clicking anywhere will close any opened tooltips (even
  // if they are permanent; once openTooltip has been called that seems to no
  // longer have any effect).
  //
  // Instead, listen for zoom changes and rebind the tooltip when the zoom level
  // changes.
  const map = useMap();
  const marker: MutableRefObject<LMarker | undefined> = useRef();

  const [putDestination] = useSetWaypointPositionMutation();
  const [openTgoInfo] = useOpenTgoInfoDialogMutation();

  const rebindTooltip = useCallback(() => {
    if (marker.current === undefined) {
      return;
    }

    const tooltip = marker.current.getTooltip();
    if (tooltip === undefined) {
      return;
    }

    const permanent = map.getZoom() >= 9;
    marker.current
      .unbindTooltip()
      .bindTooltip(tooltip, { permanent: permanent });
  }, [map]);
  useMapEvent("zoomend", rebindTooltip);

  useEffect(() => {
    marker.current?.setTooltipContent(tooltipFor(props.waypoint, props.number));
  });

  const waypoint = props.waypoint;

  // A target opens the objective rather than a waypoint editor: what matters at a
  // target is what is down there. The rest of the waypoint controls are refused for
  // the same reason -- the package was fragged against this place, and renaming or
  // dropping the mark would say the plan changed when it has not.
  const openTarget = () => {
    if (waypoint.target_id) {
      openTgoInfo({ tgoId: waypoint.target_id });
    }
  };

  return (
    <Marker
      position={waypoint.position}
      icon={iconFor(waypoint, props.selected)}
      draggable={waypoint.is_movable}
      eventHandlers={{
        click: () => props.onSelect(),
        dblclick: (e) => {
          // Leaflet's own double-click zooms the map. Editing a waypoint is not a
          // reason to change what you are looking at.
          e.originalEvent.preventDefault();
          e.originalEvent.stopPropagation();
          props.onSelect();
          if (waypoint.is_target) {
            openTarget();
            return;
          }
          props.onOpen({
            x: e.originalEvent.clientX,
            y: e.originalEvent.clientY,
          });
        },
        contextmenu: (e) => {
          e.originalEvent.preventDefault();
          props.onSelect();
          props.onMenu({
            x: e.originalEvent.clientX,
            y: e.originalEvent.clientY,
          });
        },
        dragstart: (e) => {
          const m: LMarker = e.target;
          m.setTooltipContent("Waiting to recompute TOT...");
        },
        dragend: async (e) => {
          const m: LMarker = e.target;
          const destination = m.getLatLng();
          try {
            await putDestination({
              flightId: props.flight.id,
              waypointIdx: props.number,
              leafletPoint: { lat: destination.lat, lng: destination.lng },
            });
          } catch (e) {
            console.error("Failed to set waypoint position", e);
          }
        },
      }}
      ref={(ref) => {
        if (ref != null) {
          marker.current = ref;
        }
      }}
    >
      <Tooltip position={waypoint.position} className="wp-tip" />
    </Marker>
  );
};

export default WaypointMarker;
