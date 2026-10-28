import { LatLng, LatLngLiteral, LeafletEvent, Map, Marker } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { CircleMarker, useMap } from "react-leaflet";
import {
  clearButtonHover,
  selectHighlightEmitters,
  selectHoveredEmitterSource,
  setHoveredEmitter,
} from "../../api/mapSlice";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { ControlPointIcon } from "../controlpoints/Icons";
import TgoIcon from "../tgos/TgoIcon";

export interface MapButtonHoverRequest {
  owner: string;
  target_id: string | null;
  position: LatLngLiteral | null;
}

/** Only a rendered, visible icon may receive a button highlight. */
export function visibleHoverTarget(map: Map, request: MapButtonHoverRequest) {
  let found: { id: string; position: LatLng } | undefined;
  map.eachLayer((layer) => {
    if (found || !(layer instanceof Marker)) return;
    const icon = layer.options.icon;
    const id =
      icon instanceof TgoIcon
        ? icon.tgoId
        : icon instanceof ControlPointIcon
          ? icon.controlPointId
          : null;
    if (!id || !request.position) return;
    if (
      request.target_id
        ? request.target_id !== id
        : !layer.getLatLng().equals(request.position, 1e-7)
    )
      return;
    const element = layer.getElement();
    if (
      !element ||
      !map.getContainer().contains(element) ||
      !map.getBounds().contains(layer.getLatLng())
    )
      return;
    const box = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    if (
      !box.width ||
      !box.height ||
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.opacity === "0"
    )
      return;
    found = { id, position: layer.getLatLng() };
  });
  return found;
}

export default function MapButtonHover() {
  const map = useMap();
  const dispatch = useAppDispatch();
  const request = useRef<MapButtonHoverRequest | null>(null);
  const [position, setPosition] = useState<LatLng | null>(null);
  const enabled = useAppSelector(selectHighlightEmitters);
  const source = useAppSelector(selectHoveredEmitterSource);

  useEffect(() => {
    const update = () => {
      const target =
        request.current && visibleHoverTarget(map, request.current);
      if (target) {
        dispatch(setHoveredEmitter({ id: target.id, source: "button" }));
        setPosition((old) =>
          old?.equals(target.position) ? old : target.position,
        );
      } else {
        dispatch(clearButtonHover());
        setPosition(null);
      }
    };
    const hover = (event: Event) => {
      const next = (event as CustomEvent<MapButtonHoverRequest>).detail;
      if (next.position) request.current = next;
      else if (next.owner === request.current?.owner) request.current = null;
      else return;
      update();
    };
    const layersChanged = (event: LeafletEvent) => {
      // Our CircleMarker must not restart a hover that a later map interaction
      // has already replaced. Only icon-layer changes affect visibility.
      if (
        (event.type === "layeradd" || event.type === "layerremove") &&
        !(event.layer instanceof Marker)
      )
        return;
      if (request.current) update();
    };
    const clear = () => {
      request.current = null;
      update();
    };
    window.addEventListener("map-button-hover", hover);
    window.addEventListener("saved-points-changed", clear);
    window.addEventListener("blur", clear);
    map.on("layeradd layerremove moveend zoomend", layersChanged);
    return () => {
      window.removeEventListener("map-button-hover", hover);
      window.removeEventListener("saved-points-changed", clear);
      window.removeEventListener("blur", clear);
      map.off("layeradd layerremove moveend zoomend", layersChanged);
      dispatch(clearButtonHover());
    };
  }, [map, dispatch]);

  return enabled && source === "button" && position ? (
    <CircleMarker
      center={position}
      radius={20}
      color="#ffff00"
      fillColor="#ffff00"
      fillOpacity={0.5}
      weight={4}
      interactive={false}
      pane="tooltipPane"
    />
  ) : null;
}
