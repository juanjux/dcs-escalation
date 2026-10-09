import { HTTP_URL } from "../../api/backend";
import "./SavedPointPins.css";
import L, { Marker as LeafletMarker } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { Marker, Popup, Tooltip } from "react-leaflet";

export interface SavedPoint {
  id: string;
  name: string;
  kind: string;
  position: { lat: number; lng: number };
  coordinates: string;
  altitude_ft: number;
}

interface Receiver {
  id: string;
  callsign: string;
  aircraft: string;
  points: SavedPoint[];
}

export const PIN = L.divIcon({
  className: "saved-point-pin",
  html: '<svg viewBox="0 0 25 41" xmlns="http://www.w3.org/2000/svg"><path d="M12.5 40C10 33 1 24 1 13a11.5 11.5 0 0 1 23 0c0 11-9 20-11.5 27Z" fill="#ffdf32" stroke="#504000" stroke-width="1.5"/><circle cx="12.5" cy="13" r="4" fill="#fff9d0" stroke="#504000"/></svg>',
  iconSize: [25, 41],
  iconAnchor: [12.5, 41],
  popupAnchor: [0, -35],
  tooltipAnchor: [12, -25],
});

async function mutate(
  receiver: Receiver,
  point: SavedPoint,
  method: string,
  body?: object,
) {
  const response = await fetch(
    `${HTTP_URL}saved-points/${receiver.id}/points/${point.id}`,
    {
      method,
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
  );
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(
      typeof result?.detail === "string"
        ? result.detail
        : "Could not update the point",
    );
  }
  window.dispatchEvent(new Event("saved-points-changed"));
}

export function SavedPointPin({
  receiver,
  point,
}: {
  receiver: Receiver;
  point: SavedPoint;
}) {
  const marker = useRef<LeafletMarker | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState(point.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setName(point.name), [point.name]);

  const change = async (method: string, body?: object) => {
    setBusy(true);
    setError("");
    try {
      await mutate(receiver, point, method, body);
    } catch (failure) {
      marker.current?.setLatLng(point.position);
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not update the point",
      );
      marker.current?.openPopup();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Marker
      ref={marker}
      position={point.position}
      icon={PIN}
      draggable={!busy}
      bubblingMouseEvents={false}
      eventHandlers={{
        dragend: (event) => {
          const at = (event.target as LeafletMarker).getLatLng();
          void change("PATCH", { position: { lat: at.lat, lng: at.lng } });
        },
        popupopen: () => {
          input.current?.focus();
          input.current?.select();
        },
      }}
    >
      <Tooltip>{point.name}</Tooltip>
      <Popup autoPan={false}>
        <form
          className="saved-point-editor"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy && name.trim()) void change("PATCH", { name });
          }}
        >
          <label>
            Name
            <input
              ref={input}
              value={name}
              maxLength={24}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div className="saved-point-owner">
            {receiver.callsign} · {receiver.aircraft}
          </div>
          <div>
            {point.coordinates} · {point.altitude_ft} ft
          </div>
          <div className="saved-point-buttons">
            <button type="submit" disabled={busy || !name.trim()}>
              Rename
            </button>
            <button
              type="button"
              disabled={busy}
              className="saved-point-delete"
              onClick={() => void change("DELETE")}
            >
              Delete
            </button>
          </div>
          <div className="saved-point-hint">
            Drag the pin to move this point.
          </div>
          {error && <div role="alert">{error}</div>}
        </form>
      </Popup>
    </Marker>
  );
}

export default function SavedPointPins() {
  const [receivers, setReceivers] = useState<Receiver[]>([]);
  useEffect(() => {
    let generation = 0;
    let disposed = false;
    let controller: AbortController | undefined;
    const reload = async (event?: Event) => {
      const request = ++generation;
      controller?.abort();
      controller = new AbortController();
      if ((event as CustomEvent | undefined)?.detail?.reset) {
        setReceivers([]);
      }
      if ((event as CustomEvent | undefined)?.detail?.unloaded) {
        setReceivers([]);
        return;
      }
      try {
        const response = await fetch(`${HTTP_URL}saved-points/`, {
          signal: controller.signal,
        });
        const body: unknown = response.ok ? await response.json() : [];
        if (!disposed && request === generation) {
          setReceivers(Array.isArray(body) ? body : []);
        }
      } catch (error) {
        if (!disposed && request === generation) {
          setReceivers([]);
          console.error("Could not load saved map points", error);
        }
      }
    };
    void reload();
    window.addEventListener("saved-points-changed", reload);
    return () => {
      disposed = true;
      controller?.abort();
      window.removeEventListener("saved-points-changed", reload);
    };
  }, []);

  // Multiple player flights in one squadron share the same saved points.
  const seen = new Set<string>();
  return (
    <>
      {receivers.flatMap((receiver) =>
        (receiver.points ?? []).flatMap((point) => {
          if (!point.id || !point.position || seen.has(point.id)) return [];
          seen.add(point.id);
          return [
            <SavedPointPin key={point.id} receiver={receiver} point={point} />,
          ];
        }),
      )}
    </>
  );
}
