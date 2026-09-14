import { selectMapCenter, selectMapZoom } from "../../api/mapSlice";
import { useAppSelector } from "../../app/hooks";
import MapLayersControl from "../maplayers/MapLayersControl";
import MapSearch from "../mapsearch";
import LeafletRuler from "../ruler/Ruler";
import "./LiberationMap.css";
import { Map } from "leaflet";
import { useEffect, useRef } from "react";
import { MapContainer, ScaleControl } from "react-leaflet";

export default function LiberationMap() {
  const map = useRef<Map>(null);
  const mapCenter = useAppSelector(selectMapCenter);
  const wantedZoom = useAppSelector(selectMapZoom);
  useEffect(() => {
    map.current?.setView(mapCenter, wantedZoom ?? map.current?.getZoom() ?? 8, {
      animate: true,
      duration: 1,
    });
  });
  return (
    <MapContainer
      zoom={map.current?.getZoom() ?? 8}
      zoomControl={false}
      ref={map}
    >
      <ScaleControl />
      <LeafletRuler />
      <MapLayersControl />
      <MapSearch />
    </MapContainer>
  );
}
