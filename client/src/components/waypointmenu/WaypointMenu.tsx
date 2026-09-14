import {
  Flight,
  Waypoint,
  useDeleteWaypointMutation,
  useEditWaypointMutation,
  useInsertWaypointMutation,
} from "../../api/liberationApi";
import "./WaypointMenu.css";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface WaypointTarget {
  flight: Flight;
  waypoint: Waypoint;
  /** Where on the screen the menu or dialog should appear. */
  at: { x: number; y: number };
}

/** What came back from the server when it refused, in the words it refused with. */
function refusal(error: unknown): string {
  const detail = (error as { data?: { detail?: string } })?.data?.detail;
  return typeof detail === "string" ? detail : "The server refused that.";
}

/** Keep a floating panel on screen when it is opened near an edge. */
function useNudgedOnScreen(at: { x: number; y: number }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [offset, setOffset] = useState({ dx: 0, dy: 0 });
  useEffect(() => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const dx = Math.min(0, window.innerWidth - (at.x + box.width) - 8);
    const dy = Math.min(0, window.innerHeight - (at.y + box.height) - 8);
    setOffset({ dx, dy });
  }, [at.x, at.y]);
  return { ref, style: { left: at.x + offset.dx, top: at.y + offset.dy } };
}

interface MenuProps {
  target: WaypointTarget;
  onOpenDialog: () => void;
  onOpenTarget: () => void;
  onRename: () => void;
  onClose: () => void;
  onError: (message: string) => void;
}

export function WaypointMenu(props: MenuProps) {
  const { flight, waypoint } = props.target;
  const [deleteWaypoint] = useDeleteWaypointMutation();
  const [insertWaypoint] = useInsertWaypointMutation();
  const { ref, style } = useNudgedOnScreen(props.target.at);

  // Anywhere else, and Escape, puts the menu away. Mousedown rather than click so a
  // press that starts on the map does not also drag it out from under the pointer.
  useEffect(() => {
    const dismiss = (event: Event) => {
      if (!ref.current?.contains(event.target as Node)) props.onClose();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    document.addEventListener("mousedown", dismiss, true);
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("mousedown", dismiss, true);
      document.removeEventListener("keydown", key, true);
    };
  });

  const insert = async (before: boolean) => {
    props.onClose();
    try {
      await insertWaypoint({
        flightId: flight.id,
        waypointIdx: waypoint.index,
        waypointInsert: { before: before },
      }).unwrap();
    } catch (error) {
      props.onError(refusal(error));
    }
  };

  const remove = async () => {
    props.onClose();
    try {
      await deleteWaypoint({
        flightId: flight.id,
        waypointIdx: waypoint.index,
      }).unwrap();
    } catch (error) {
      props.onError(refusal(error));
    }
  };

  // A target is what the package was fragged against. Renaming it, dropping it or
  // threading a nav point through the attack run would each say the mission changed
  // when it has not, so the menu offers the objective and nothing else.
  if (waypoint.is_target) {
    return createPortal(
      <div className="wp-menu" ref={ref} style={style}>
        <div className="wp-menu-title">{waypoint.name}</div>
        <button onClick={props.onOpenTarget} disabled={!waypoint.target_id}>
          Objective…
        </button>
        <div className="wp-menu-note">
          {waypoint.is_movable
            ? "Dragging the mark moves where this flight hunts."
            : "The target is fixed: plan a different package to attack elsewhere."}
        </div>
      </div>,
      document.body,
    );
  }

  return createPortal(
    <div className="wp-menu" ref={ref} style={style}>
      <div className="wp-menu-title">{waypoint.name}</div>
      <button onClick={props.onOpenDialog}>Open…</button>
      <button onClick={props.onRename}>Rename…</button>
      <button onClick={() => insert(true)}>Insert waypoint before</button>
      <button onClick={() => insert(false)}>Add waypoint after</button>
      <button
        className="wp-danger"
        disabled={!waypoint.can_delete}
        title={
          waypoint.can_delete
            ? undefined
            : "Part of this flight's plan. Remove it from the flight's waypoint tab."
        }
        onClick={remove}
      >
        Delete
      </button>
    </div>,
    document.body,
  );
}

interface DialogProps {
  target: WaypointTarget;
  /** Opened straight into the name field by "Rename…". */
  renaming?: boolean;
  onClose: () => void;
  onError: (message: string) => void;
}

export function WaypointDialog(props: DialogProps) {
  const { flight, waypoint } = props.target;
  const [editWaypoint] = useEditWaypointMutation();
  const { ref, style } = useNudgedOnScreen(props.target.at);
  const [name, setName] = useState(waypoint.name);
  const [altitude, setAltitude] = useState(
    String(Math.round(waypoint.altitude_ft)),
  );
  const [reference, setReference] = useState(waypoint.altitude_reference);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    document.addEventListener("keydown", key, true);
    return () => document.removeEventListener("keydown", key, true);
  });

  const apply = async () => {
    const feet = Number(altitude);
    props.onClose();
    try {
      await editWaypoint({
        flightId: flight.id,
        waypointIdx: waypoint.index,
        waypointEdit: {
          name: name,
          altitude_ft: Number.isFinite(feet) ? feet : undefined,
          altitude_reference: reference,
        },
      }).unwrap();
    } catch (error) {
      props.onError(refusal(error));
    }
  };

  return createPortal(
    <div className="wp-dialog" ref={ref} style={style}>
      <h3>Waypoint {waypoint.index}</h3>
      <div className="wp-row">
        <label htmlFor="wp-name">Name</label>
        <input
          id="wp-name"
          value={name}
          autoFocus={props.renaming}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") apply();
          }}
        />
      </div>
      <div className="wp-row">
        <label htmlFor="wp-alt">Altitude (ft)</label>
        <input
          id="wp-alt"
          type="number"
          step={500}
          value={altitude}
          autoFocus={!props.renaming}
          onChange={(e) => setAltitude(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") apply();
          }}
        />
      </div>
      <div className="wp-row">
        <label htmlFor="wp-ref">Reference</label>
        <select
          id="wp-ref"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        >
          <option value="BARO">BARO</option>
          <option value="RADIO">RADIO</option>
        </select>
      </div>
      <div className="wp-row">
        <label>Speed</label>
        {/* The plan's, not the waypoint's: there is nothing per-waypoint to set. */}
        <span className="wp-readonly">
          {waypoint.speed_kts > 0
            ? `${Math.round(waypoint.speed_kts)} kt`
            : "—"}
        </span>
      </div>
      <div className="wp-actions">
        <button onClick={props.onClose}>Cancel</button>
        <button onClick={apply}>Apply</button>
      </div>
    </div>,
    document.body,
  );
}
