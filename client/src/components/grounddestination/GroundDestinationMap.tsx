import { useEffect, useRef, useState } from "react";
import { BasemapLayer } from "react-esri-leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Pane,
  ScaleControl,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { DomEvent, LatLngLiteral } from "leaflet";
import { useAppSelector } from "../../app/hooks";
import { selectControlPoints } from "../../api/controlPointsSlice";
import { selectTgos } from "../../api/tgosSlice";
import { selectFrontLines } from "../../api/frontLinesSlice";
import { selectSupplyRoutes } from "../../api/supplyRoutesSlice";
import { iconForControlPoint } from "../controlpoints/Icons";
import { iconForTgo } from "../tgos/shared";
import {
  bridgeCall,
  DestinationBridge,
  DestinationPreviewController,
  RoutePreview,
} from "./bridge";
import "../liberationmap/LiberationMap.css";
import "./GroundDestinationMap.css";

interface Origin {
  origin: LatLngLiteral;
  name: string;
}

function Background() {
  const bases = useAppSelector(selectControlPoints).controlPoints;
  const tgos = useAppSelector(selectTgos).tgos;
  const roads = useAppSelector(selectSupplyRoutes).routes;
  const fronts = useAppSelector(selectFrontLines).fronts;
  return (
    <>
      <BasemapLayer name="ImageryClarity" />
      {Object.values(roads)
        .filter((road) => !road.is_sea)
        .map((road) => (
          <Polyline
            key={road.id}
            positions={road.points}
            interactive={false}
            pathOptions={{
              color: road.front_active
                ? "#c85050"
                : road.blue
                  ? "#8b9daa"
                  : "#8c1414",
              weight: 5,
            }}
          />
        ))}
      {Object.values(fronts).map((front) => (
        <Polyline
          key={front.id}
          positions={front.extents}
          interactive={false}
          pathOptions={{ color: "#fe7d0a", weight: 12 }}
        />
      ))}
      {Object.values(tgos)
        .filter((tgo) => !tgo.dead)
        .map((tgo) => (
          <Marker
            key={tgo.id}
            position={tgo.position}
            icon={iconForTgo(tgo)}
            interactive={false}
          />
        ))}
      {Object.values(bases).map((base) => (
        <Marker
          key={base.id}
          position={base.position}
          icon={iconForControlPoint(base)}
          interactive={false}
          zIndexOffset={1000}
        >
          <Tooltip permanent direction="right">
            {base.name}
          </Tooltip>
        </Marker>
      ))}
    </>
  );
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
      if (event.key === "Escape") bridge.dismiss();
    };
    window.addEventListener("keydown", escape);
    return () => {
      instance.dispose();
      window.removeEventListener("keydown", escape);
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
      controller.current?.move({
        lat: event.latlng.lat,
        lng: event.latlng.lng,
      });
    },
    click: (event) =>
      controller.current?.pick({
        lat: event.latlng.lat,
        lng: event.latlng.lng,
      }),
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
        <strong>Choose the armor group/SAM destination and click</strong>
        <div className="gd-source">
          From {origin.name}. Selecting a position does not dispatch units.
        </div>
        {at && (
          <div>
            {at.lat.toFixed(5)}, {at.lng.toFixed(5)}
          </div>
        )}
        {!at ? (
          <div>Move the cursor to preview a route. Escape to cancel.</div>
        ) : pending ? (
          <div>Checking route…</div>
        ) : preview?.valid ? (
          <div>
            {(
              ((preview.road_distance_m ?? 0) +
                (preview.offroad_distance_m ?? 0)) /
              1000
            ).toFixed(1)}{" "}
            km · {preview.arrival_in_turns} turn(s)
            <div>
              Road: {((preview.road_distance_m ?? 0) / 1000).toFixed(1)} km ·
              Off-road: {((preview.offroad_distance_m ?? 0) / 1000).toFixed(1)}{" "}
              km
            </div>
            <div className="gd-valid">Click to use this destination</div>
          </div>
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

export default function GroundDestinationMap() {
  const [ready, setReady] = useState<{
    bridge: DestinationBridge;
    origin: Origin;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let connecting = false;
    const connect = async () => {
      const bridge = window.groundDestinationBridge;
      if (!bridge || connecting) return;
      connecting = true;
      try {
        const origin = await bridgeCall<Origin>((done) => bridge.initial(done));
        if (active) setReady({ bridge, origin });
      } catch (error) {
        if (active) setError(String(error));
      }
    };
    window.addEventListener("ground-destination-ready", connect);
    connect();
    const timeout = setTimeout(() => {
      if (active && !connecting)
        setError(
          "The map could not connect to the campaign. Close and reopen the selector.",
        );
    }, 10000);
    return () => {
      active = false;
      clearTimeout(timeout);
      window.removeEventListener("ground-destination-ready", connect);
    };
  }, []);
  if (!ready)
    return (
      <div className="gd-loading" role="status">
        {error || "Loading destination map…"}
      </div>
    );
  return (
    <MapContainer
      className="ground-destination-map"
      center={ready.origin.origin}
      zoom={10}
      doubleClickZoom={false}
    >
      <ScaleControl />
      <Background />
      <DestinationInteraction {...ready} />
    </MapContainer>
  );
}
