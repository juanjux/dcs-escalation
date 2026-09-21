// The switch that decides whether a click on bare map reports its coordinates.
//
// It used to be always on, so every miss -- and half the map is a miss -- opened a
// popup that had to be dismissed. It is a tool now, like the ruler beside it: off
// until it is picked up.
import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

interface PickerToggleProps {
  on: boolean;
  toggle: () => void;
}

export default function PickerToggle(props: PickerToggleProps) {
  const map = useMap();
  const bar = useRef<HTMLElement | null>(null);

  // Read through a ref: the control is built once, and the handler it keeps has to
  // be the current one rather than the one from the render that built it.
  const toggle = useRef(props.toggle);
  toggle.current = props.toggle;

  useEffect(() => {
    if (!map) {
      return;
    }
    const control = new L.Control({ position: "topleft" });
    control.onAdd = () => {
      const container = L.DomUtil.create(
        "div",
        "leaflet-bar leaflet-control cp-toggle",
      );
      const button = L.DomUtil.create("a", "", container);
      button.href = "#";
      button.setAttribute("role", "button");
      button.title = "GPS coordinates: read any point on the map";
      // Leaflet would otherwise pan the map under the button and follow the href.
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.on(button, "click", (event: Event) => {
        L.DomEvent.stop(event);
        toggle.current();
      });
      bar.current = container;
      return container;
    };
    control.addTo(map);
    return () => {
      control.remove();
      bar.current = null;
    };
  }, [map]);

  useEffect(() => {
    bar.current?.classList.toggle("cp-toggle-on", props.on);
  }, [props.on]);

  // The same crosshair the ruler puts up while it is measuring, set the same way it
  // sets it: the cursor is what tells the player the next click is the tool's and
  // not the map's.
  useEffect(() => {
    const container = map?.getContainer?.();
    if (!container || !props.on) {
      return;
    }
    const was = container.style.cursor;
    container.style.cursor = "crosshair";
    return () => {
      container.style.cursor = was;
    };
  }, [map, props.on]);

  return null;
}
