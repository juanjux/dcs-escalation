import { useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  Circle,
  Polyline,
  Pane,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { DomEvent, LatLngLiteral } from "leaflet";
import {
  bridgeCall,
  DestinationBridge,
  DestinationPreviewController,
  RoutePreview,
} from "./bridge";
import "../liberationmap/LiberationMap.css";
import "./GroundDestinationMap.css";
import { snapMissileTarget, SnapTarget } from "./targetSnap";

interface Origin {
  origin: LatLngLiteral;
  name: string;
  mode?: "missile";
  min_range_m?: number;
  max_range_m?: number;
  snap_targets?: SnapTarget[];
}

export function DestinationInteraction({
  bridge,
  origin,
}: {
  bridge: DestinationBridge;
  origin: Origin;
}) {
  const map = useMap();
  const [at, setAt] = useState<LatLngLiteral | null>(null);
  const [preview, setPreview] = useState<RoutePreview | null>(null);
  const [pending, setPending] = useState(false);
  const controller = useRef<DestinationPreviewController>();
  const banner = useRef<HTMLDivElement>(null);
  const targets = useMemo(
    () => new Map(origin.snap_targets?.map((target) => [target.id, target])),
    [origin.snap_targets],
  );

  useEffect(() => {
    const center = map.getCenter();
    const zoom = map.getZoom();
    const doubleClickZoom = map.doubleClickZoom.enabled();
    const container = map.getContainer();
    map.stop();
    map.closePopup();
    container.classList.add("ground-destination-map");
    map.doubleClickZoom.disable();
    map.setView(origin.origin, Math.max(zoom, 10), { animate: false });
    bridge.ready();
    return () => {
      container.classList.remove("ground-destination-map");
      map.stop();
      map.setView(center, zoom, { animate: false });
      if (doubleClickZoom) map.doubleClickZoom.enable();
    };
  }, [map, bridge, origin]);

  useEffect(() => {
    if (banner.current) {
      DomEvent.disableClickPropagation(banner.current);
      DomEvent.disableScrollPropagation(banner.current);
    }
  }, []);

  useEffect(() => {
    const instance = new DestinationPreviewController(
      bridge,
      (position) => {
        setAt(position);
        setPending(true);
      },
      (result) => {
        setPreview(result);
        setPending(false);
      },
    );
    controller.current = instance;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        bridge.dismiss();
      } else if (event.key === "Enter" || event.key === " ") {
        if (
          !(
            event.target instanceof Element &&
            event.target.closest(".gd-banner")
          )
        ) {
          // Marker keyboard activation must not open normal campaign dialogs.
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      } else if (
        ![
          "Tab",
          "+",
          "-",
          "=",
          "ArrowUp",
          "ArrowDown",
          "ArrowLeft",
          "ArrowRight",
        ].includes(event.key)
      ) {
        // Normal layers remain mounted. Do not let their edit shortcuts run.
        event.stopImmediatePropagation();
      }
    };
    window.addEventListener("keydown", escape, true);
    return () => {
      instance.dispose();
      window.removeEventListener("keydown", escape, true);
    };
  }, [bridge]);

  const status = !at
    ? "idle"
    : pending
      ? "pending"
      : preview?.valid
        ? "valid"
        : "invalid";
  useEffect(() => {
    const container = map.getContainer();
    container.dataset.destinationStatus = status;
    return () => {
      delete container.dataset.destinationStatus;
    };
  }, [map, status]);

  useMapEvents({
    mousemove: (event) => {
      const target = event.originalEvent.target;
      if (
        target instanceof Element &&
        target.closest(".gd-banner, .leaflet-control")
      )
        return;
      const position = {
        lat: event.latlng.lat,
        lng: event.latlng.lng,
      };
      controller.current?.move(
        origin.mode === "missile"
          ? snapMissileTarget(map, event.originalEvent, position, targets)
          : position,
      );
    },
    click: (event) => {
      const position = {
        lat: event.latlng.lat,
        lng: event.latlng.lng,
      };
      controller.current?.pick(
        origin.mode === "missile"
          ? snapMissileTarget(map, event.originalEvent, position, targets)
          : position,
      );
    },
    mouseout: (event) => {
      const related = event.originalEvent.relatedTarget;
      if (related instanceof Node && map.getContainer().contains(related))
        return;
      controller.current?.leave();
      setAt(null);
      setPreview(null);
      setPending(false);
    },
  });

  return (
    <>
      <div ref={banner} className="gd-banner" role="status" aria-live="polite">
        <strong>
          {origin.mode === "missile"
            ? "Choose the missile target and click"
            : "Choose the armor group/SAM destination and click"}
        </strong>
        <button className="gd-cancel" onClick={() => bridge.dismiss()}>
          Cancel
        </button>
        <div className="gd-source">
          From {origin.name}.{" "}
          {origin.mode === "missile"
            ? "Selecting a position does not assign the target."
            : "Selecting a position does not dispatch units."}
        </div>
        {at && (
          <div>
            {at.lat.toFixed(5)}, {at.lng.toFixed(5)}
          </div>
        )}
        {!at ? (
          <div>
            {origin.mode === "missile"
              ? "Move the cursor to check missile range. Escape to cancel."
              : "Move the cursor to preview a route. Escape to cancel."}
          </div>
        ) : pending ? (
          <div>
            {origin.mode === "missile"
              ? "Checking missile range…"
              : "Checking route…"}
          </div>
        ) : preview?.valid ? (
          origin.mode === "missile" ? (
            <div>
              {((preview.distance_m ?? 0) / 1000).toFixed(1)} km ·{" "}
              {preview.target_name}
              {preview.warning && (
                <div className="gd-error">{preview.warning}</div>
              )}
              <div className="gd-valid">Click to use this aimpoint</div>
            </div>
          ) : (
            <div>
              {(
                ((preview.road_distance_m ?? 0) +
                  (preview.offroad_distance_m ?? 0)) /
                1000
              ).toFixed(1)}{" "}
              km · {preview.arrival_in_turns} turn(s)
              <div>
                Road: {((preview.road_distance_m ?? 0) / 1000).toFixed(1)} km ·
                Off-road:{" "}
                {((preview.offroad_distance_m ?? 0) / 1000).toFixed(1)} km
              </div>
              <div className="gd-valid">Click to use this destination</div>
            </div>
          )
        ) : (
          <div className="gd-error">{preview?.error ?? "No valid route"}</div>
        )}
      </div>
      <Pane
        name="ground-destination-route"
        style={{ zIndex: 640, pointerEvents: "none" }}
      >
        <CircleMarker
          center={origin.origin}
          radius={12}
          interactive={false}
          pathOptions={{ color: "#ffffff", weight: 3, fillOpacity: 0 }}
        />
        {origin.mode === "missile" && origin.max_range_m && (
          <Circle
            center={origin.origin}
            radius={origin.max_range_m}
            interactive={false}
            pathOptions={{ color: "#ffdc61", fillOpacity: 0, dashArray: "8 6" }}
          />
        )}
        {origin.mode === "missile" && !!origin.min_range_m && (
          <Circle
            center={origin.origin}
            radius={origin.min_range_m}
            interactive={false}
            pathOptions={{
              color: "#ff6b6b",
              fillOpacity: 0.08,
              dashArray: "8 6",
            }}
          />
        )}
        {origin.mode === "missile" && at && preview?.valid && (
          <Polyline
            positions={[origin.origin, at]}
            interactive={false}
            pathOptions={{ color: "#ffdc61", weight: 2 }}
          />
        )}
        {at && (
          <CircleMarker
            center={at}
            radius={6}
            interactive={false}
            pathOptions={{
              color: status === "invalid" ? "#ff6b6b" : "#ffdc61",
              fillOpacity: 0.8,
            }}
          />
        )}
        {preview?.valid &&
          preview.segments?.map((segment, index) => (
            <Polyline
              key={index}
              positions={[segment.start, segment.end]}
              interactive={false}
              pathOptions={{
                color: segment.on_road ? "#ffdc61" : "#4bd9ed",
                weight: 5,
                opacity: pending ? 0.45 : 1,
                dashArray: segment.on_road ? undefined : "8 6",
              }}
            />
          ))}
      </Pane>
    </>
  );
}

export default function GroundDestinationMode({
  onActiveChange,
}: {
  onActiveChange: (active: boolean) => void;
}) {
  const [ready, setReady] = useState<{
    id: string;
    bridge: DestinationBridge;
    origin: Origin;
  } | null>(null);
  useEffect(() => {
    let active = true;
    let current: { id: string; bridge: DestinationBridge } | null = null;
    const connect = async (event: Event) => {
      const session = (event as CustomEvent).detail as {
        id: string;
        bridge: DestinationBridge;
      };
      current = session;
      setReady(null);
      onActiveChange(true);
      try {
        const origin = await bridgeCall<Origin>((done) =>
          session.bridge.initial(done),
        );
        if (active && current === session) setReady({ ...session, origin });
      } catch (error) {
        if (active && current === session) {
          console.error("Cannot start destination selection", error);
          session.bridge.dismiss();
        }
      }
    };
    const end = (event: Event) => {
      if ((event as CustomEvent).detail.id !== current?.id) return;
      current = null;
      setReady(null);
      onActiveChange(false);
    };
    window.addEventListener("ground-destination-start", connect);
    window.addEventListener("ground-destination-end", end);
    window.groundDestinationModeReady = true;
    return () => {
      active = false;
      window.groundDestinationModeReady = false;
      window.removeEventListener("ground-destination-start", connect);
      window.removeEventListener("ground-destination-end", end);
      current?.bridge.dismiss();
    };
  }, [onActiveChange]);
  return ready ? <DestinationInteraction key={ready.id} {...ready} /> : null;
}
