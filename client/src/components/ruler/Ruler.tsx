/// <reference path="./leaflet-ruler.d.ts" />
import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-ruler";
import "./Ruler.css";

export default function LeafletRuler() {
  const map = useMap();

  useEffect(() => {
    if (!map) return;

    var options = {
      position: "topleft",
      circleMarker: {
        // Leaflet circle marker options for points used in this plugin
        color: "yellow",
        radius: 2,
      },
      lineStyle: {
        // Leaflet polyline options for lines used in this plugin
        color: "yellow",
        dashArray: "1,6",
      },
      lengthUnit: {
        factor: 0.539956803, //  from km to nm
        display: "NM",
        decimal: 2,
        label: "Distance",
      },
    };
    if (L.control.hasOwnProperty("ruler")) {
      const control = L.control.ruler(options).addTo(map) as L.Control & {
        _choice: boolean;
        _toggleMeasure: () => void;
        _tempLine?: L.Layer;
        _tempPoint?: L.Layer;
      };
      return () => {
        // The plugin's onRemove only removes its button listener. End an
        // active measurement first so it releases map and keyboard handlers.
        if (control._choice) control._toggleMeasure();
        if (control._tempLine) map.removeLayer(control._tempLine);
        if (control._tempPoint) map.removeLayer(control._tempPoint);
        control.remove();
      };
    }
  }, [map]);

  return null;
}
