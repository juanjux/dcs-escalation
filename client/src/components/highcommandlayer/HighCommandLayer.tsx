import { HighCommandMark } from "../../api/_liberationApi";
import { selectHighCommandMarks } from "../../api/highCommandSlice";
import { useAppSelector } from "../../app/hooks";
import { divIcon } from "leaflet";
import { CircleMarker, LayerGroup, Marker, Pane, Tooltip } from "react-leaflet";

// The High Command orange, brighter than the window's (#F29A4A) so it holds up on
// the satellite map.
export const ORANGE = "#FF9F43";
// Screen pixels. The ring clears a site's icon, so the icon and its threat rings stay
// visible; an order in its last turn gets a thicker ring and a dashed halo.
export const RING_RADIUS = 24;
export const HALO_RADIUS = 32;
const TAG_GAP = 6;

export function tagText(mark: HighCommandMark): string {
  if (mark.last_turn) return "LAST TURN";
  if (mark.orders > 1) return `HC ×${mark.orders} · ${mark.soonest}`;
  return `HC · ${mark.soonest}`;
}

function tagIcon(mark: HighCommandMark) {
  const last = mark.last_turn;
  const style = [
    "position:absolute",
    "left:0",
    `bottom:${RING_RADIUS + TAG_GAP}px`,
    "transform:translateX(-50%)",
    "white-space:nowrap",
    "font:700 9.5px 'Segoe UI',sans-serif",
    "letter-spacing:0.6px",
    "padding:1px 5px",
    "border-radius:3px",
    `border:1px solid ${ORANGE}`,
    `background:${last ? ORANGE : "#14202B"}`,
    `color:${last ? "#0F1922" : ORANGE}`,
  ].join(";");
  // A zero-size icon anchored on the objective; the tag is placed above the ring by
  // its own style, so it never covers the icon underneath.
  return divIcon({
    className: "high-command-tag",
    html: `<div style="${style}">${tagText(mark)}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function HighCommandPoint(props: { mark: HighCommandMark }) {
  const mark = props.mark;
  const last = mark.last_turn;
  return (
    <>
      <CircleMarker
        center={mark.position}
        radius={RING_RADIUS}
        interactive={false}
        pathOptions={{ color: ORANGE, weight: last ? 4 : 2.5, fill: false }}
      />
      {last && (
        <CircleMarker
          center={mark.position}
          radius={HALO_RADIUS}
          interactive={false}
          pathOptions={{
            color: ORANGE,
            weight: 1.5,
            dashArray: "4 3",
            fill: false,
          }}
        />
      )}
      <Marker position={mark.position} icon={tagIcon(mark)}>
        <Tooltip direction="top">{mark.tooltip}</Tooltip>
      </Marker>
    </>
  );
}

export default function HighCommandLayer() {
  const marks = useAppSelector(selectHighCommandMarks);
  return (
    // Above the marker pane (600), so the ring is drawn over the site's icon, and
    // below the tooltip pane (650). The rings take no clicks: those go to the icon.
    <Pane name="high-command" style={{ zIndex: 610 }}>
      <LayerGroup>
        {marks.map((mark) => (
          <HighCommandPoint key={mark.name} mark={mark} />
        ))}
      </LayerGroup>
    </Pane>
  );
}
