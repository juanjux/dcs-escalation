import { selectMapCenter, selectMapZoom } from "../../api/mapSlice";
import { useAppSelector } from "../../app/hooks";
import MapLayersControl from "../maplayers/MapLayersControl";
import CoordinatePicker from "../coordinatepicker";
import SavedPointPins from "../savedpointpins/SavedPointPins";
import MapSearch from "../mapsearch";
import LeafletRuler from "../ruler/Ruler";
import GroundDestinationMode from "../grounddestination/GroundDestinationMap";
import "./LiberationMap.css";
import { Map } from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";
import { MapContainer, ScaleControl } from "react-leaflet";

export default function LiberationMap() {
  const map = useRef<Map>(null);
  const mapCenter = useAppSelector(selectMapCenter);
  const wantedZoom = useAppSelector(selectMapZoom);
  const [selecting, setSelecting] = useState(false);
  const selectingRef = useRef(false);
  const selectionChanged = useCallback((active: boolean) => {
    selectingRef.current = active;
    setSelecting(active);
  }, []);
  useEffect(() => {
    if (selectingRef.current) return;
    map.current?.setView(mapCenter, wantedZoom ?? map.current?.getZoom() ?? 8, {
      animate: true,
      duration: 1,
    });
  }, [mapCenter, wantedZoom]);
  return (
    <MapContainer
      zoom={map.current?.getZoom() ?? 8}
      zoomControl={false}
      ref={map}
    >
      <ScaleControl />
      <MapLayersControl />
      {!selecting && <LeafletRuler />}
      {!selecting && <MapSearch />}
      {!selecting && <CoordinatePicker />}
      {!selecting && <SavedPointPins />}
      <GroundDestinationMode onActiveChange={selectionChanged} />
    </MapContainer>
  );
}
