import { useAppSelector } from "../../app/hooks";
import { LatLngLiteral } from "leaflet";
import { LayerGroup, Polygon } from "react-leaflet";
import { selectMapZones } from "../../api/mapZonesSlice";

interface TerrainZoneLayerProps {
  zones: LatLngLiteral[][][];
  color: string;
  fillColor: string;
  fillOpacity?: number;
  dashArray?: string;
}

function TerrainZoneLayer(props: TerrainZoneLayerProps) {
  return (
    <LayerGroup>
      {props.zones.map((poly, idx) => {
        return (
          <Polygon
            key={idx}
            positions={poly}
            color={props.color}
            fillColor={props.fillColor}
            fillOpacity={props.fillOpacity ?? 1}
            dashArray={props.dashArray}
            interactive={false}
          />
        );
      })}
    </LayerGroup>
  );
}

// Self-contained, raw-layer variants (no LayersControl.Overlay) so the custom
// map layers panel can render and toggle them directly.
export function InclusionZonesLayer() {
  const zones = useAppSelector(selectMapZones).mapZones;
  if (!zones) return null;
  return (
    <TerrainZoneLayer
      zones={zones.inclusion}
      color="#969696"
      fillColor="#4b4b4b"
    />
  );
}

export function ExclusionZonesLayer({
  movement = false,
}: { movement?: boolean } = {}) {
  const zones = useAppSelector(selectMapZones).mapZones;
  if (!zones) return null;
  return (
    <TerrainZoneLayer
      zones={zones.exclusion}
      color={movement ? "#ff886b" : "#969696"}
      fillColor={movement ? "#ff6655" : "#303030"}
      fillOpacity={movement ? 0.18 : 1}
      dashArray={movement ? "6 4" : undefined}
    />
  );
}

export function SeaZonesLayer() {
  const zones = useAppSelector(selectMapZones).mapZones;
  if (!zones) return null;
  return (
    <TerrainZoneLayer zones={zones.sea} color="#344455" fillColor="#344455" />
  );
}
