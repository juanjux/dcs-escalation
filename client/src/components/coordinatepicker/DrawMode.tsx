import { HTTP_URL } from "../../api/backend";
import { landedOnSomething, measuring } from "./CoordinatePicker";
import L, { LatLng } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Polyline, useMap, useMapEvent } from "react-leaflet";
import "./DrawMode.css";

interface Receiver {
  id: string;
  callsign: string;
  aircraft: string;
  departure: string;
}

export function DrawPanel({
  points,
  undo,
  close,
}: {
  points: LatLng[];
  undo: () => void;
  close: () => void;
}) {
  const [receivers, setReceivers] = useState<Receiver[]>([]);
  const [chosen, setChosen] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    fetch(`${HTTP_URL}saved-points/`, { signal: controller.signal })
      .then(async (response) => (response.ok ? response.json() : []))
      .then((body) => {
        if (!mounted.current) return;
        const list: Receiver[] = Array.isArray(body) ? body : [];
        setReceivers(list);
        setChosen(list[0]?.id ?? "");
      })
      .catch(() => {
        if (mounted.current) setError("Could not load player aircraft");
      });
    return () => {
      mounted.current = false;
      controller.abort();
    };
  }, []);

  const save = async (closed: boolean) => {
    if (busy || !chosen) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `${HTTP_URL}saved-points/${chosen}/drawings`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            closed,
            points: points.map(({ lat, lng }) => ({ lat, lng })),
          }),
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "Could not save drawing",
        );
      }
      if (mounted.current) {
        window.dispatchEvent(new Event("saved-points-changed"));
        close();
      }
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof Error ? failure.message : "Could not save drawing",
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <div className="map-draw-panel">
      <strong>Drawing · {points.length}/64 vertices</strong>
      <div>Click empty map to add a vertex.</div>
      <label>
        Player aircraft
        <select
          aria-label="Player aircraft"
          value={chosen}
          disabled={busy}
          onChange={(event) => setChosen(event.target.value)}
        >
          {!receivers.length && <option value="">No player aircraft</option>}
          {receivers.map((one) => (
            <option key={one.id} value={one.id}>
              {one.callsign} · {one.aircraft} · {one.departure}
            </option>
          ))}
        </select>
      </label>
      <input
        aria-label="Drawing name"
        placeholder="Name (optional)"
        maxLength={24}
        value={name}
        disabled={busy}
        onChange={(event) => setName(event.target.value)}
      />
      <div className="map-draw-actions">
        <button
          disabled={busy || !chosen || points.length < 2}
          onClick={() => void save(false)}
        >
          Save line
        </button>
        <button
          disabled={busy || !chosen || points.length < 3}
          onClick={() => void save(true)}
        >
          Save area
        </button>
        <button disabled={busy || !points.length} onClick={undo}>
          Undo
        </button>
        <button disabled={busy} onClick={close}>
          Cancel
        </button>
      </div>
      <small>
        Saved on the squadron, map and kneeboard. Cockpit export depends on
        aircraft limits.
      </small>
      {error && <div role="alert">{error}</div>}
    </div>
  );
}

export default function DrawMode() {
  const map = useMap();
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const [active, setActive] = useState(false);
  const [points, setPoints] = useState<LatLng[]>([]);
  const toggle = useRef(() => {});
  const close = () => {
    setActive(false);
    setPoints([]);
  };
  toggle.current = () => {
    setActive((on) => !on);
    setPoints([]);
  };

  useEffect(() => {
    const control = new L.Control({ position: "topleft" });
    control.onAdd = () => {
      const node = L.DomUtil.create("div", "leaflet-control map-draw-control");
      L.DomEvent.disableClickPropagation(node);
      L.DomEvent.disableScrollPropagation(node);
      setContainer(node);
      return node;
    };
    control.addTo(map);
    return () => {
      control.remove();
    };
  }, [map]);
  useEffect(() => {
    const reset = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.reset || detail?.unloaded) {
        setActive(false);
        setPoints([]);
      }
    };
    const picking = () => {
      setActive(false);
      setPoints([]);
    };
    window.addEventListener("gps-picker-activated", picking);
    window.addEventListener("saved-points-changed", reset);
    return () => {
      window.removeEventListener("gps-picker-activated", picking);
      window.removeEventListener("saved-points-changed", reset);
    };
  }, []);
  useEffect(() => {
    if (!active) return;
    window.dispatchEvent(new Event("map-drawing-activated"));
    const node = map.getContainer();
    const cursor = node.style.cursor;
    const zoom = map.doubleClickZoom.enabled();
    node.style.cursor = "crosshair";
    map.doubleClickZoom.disable();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActive(false);
        setPoints([]);
      }
    };
    window.addEventListener("keydown", escape);
    return () => {
      node.style.cursor = cursor;
      if (zoom) map.doubleClickZoom.enable();
      window.removeEventListener("keydown", escape);
    };
  }, [map, active]);
  useMapEvent("click", (event) => {
    if (
      active &&
      !measuring() &&
      !landedOnSomething(event.originalEvent.target)
    ) {
      setPoints((previous) =>
        previous.length < 64 ? [...previous, event.latlng] : previous,
      );
    }
  });
  return (
    <>
      {container &&
        createPortal(
          <>
            <button
              className={active ? "map-draw-toggle active" : "map-draw-toggle"}
              title="Draw a saved line or area"
              aria-label="Draw on map"
              aria-pressed={active}
              onClick={() => toggle.current()}
            >
              ✎
            </button>
            {active && (
              <DrawPanel
                points={points}
                undo={() => setPoints((p) => p.slice(0, -1))}
                close={close}
              />
            )}
          </>,
          container,
        )}
      {active && points.length > 1 && (
        <Polyline
          positions={points}
          interactive={false}
          pathOptions={{ color: "#ffdf32", weight: 3, dashArray: "6 4" }}
        />
      )}
    </>
  );
}
