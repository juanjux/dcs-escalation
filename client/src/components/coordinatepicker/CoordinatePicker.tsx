// The coordinates of any empty spot on the map.
//
// Clicking bare map did nothing before, so it reports the point instead: the campaign's
// coordinate format with a button that copies it, and the other formats under it, each
// of which copies when clicked.
//
// It is behind a toggle in the corner, off until it is switched on. Always-on meant
// every missed click -- and most of the map is a miss -- opened a popup to dismiss.
//
// Clicks that land on something -- a route, an objective, a base -- belong to that thing
// and are left alone. Leaflet marks those elements `leaflet-interactive` and still
// bubbles the click up to the map, so the target is what tells the two apart.
//
// The ruler is the other claim on a bare click: while it is measuring, every click is a
// vertex of the line being drawn, and a popup on each one is in the way. It marks its
// own control button while it is on, which is the only thing it says out loud.
//
// The formatting is the server's, so the map, the objective dialog and anything added
// later say the same thing about the same spot.
import { HTTP_URL } from "../../api/backend";
import PickerToggle from "./PickerToggle";
import SavePoint from "./SavePoint";
import { copyText } from "./clipboard";
import "./CoordinatePicker.css";
import L, { LatLng, Marker as LeafletMarker } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { Marker, Popup, useMapEvent } from "react-leaflet";

interface Picked {
  at: LatLng;
  text: string;
  all: Record<string, string>;
  // How high the ground is here, when the server could look it up.
  elevationFt?: number;
}

const CROSSHAIR = L.divIcon({
  className: "",
  html: '<div class="cp-crosshair"></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export function landedOnSomething(target: EventTarget | null): boolean {
  return (
    target instanceof Element && target.closest(".leaflet-interactive") !== null
  );
}

// leaflet-ruler puts this class on its control while it is measuring, and takes it off
// when the measurement ends.
export function measuring(): boolean {
  return document.querySelector(".leaflet-ruler-clicked") !== null;
}

export default function CoordinatePicker() {
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [copied, setCopied] = useState(false);
  const marker = useRef<LeafletMarker | null>(null);

  // A popup inside a marker is bound to it, not opened: react-leaflet only opens the
  // ones that hang from the map. The point was just clicked, so open it.
  useEffect(() => {
    if (picked !== null) {
      marker.current?.openPopup();
    }
  }, [picked]);

  useMapEvent("click", async (event) => {
    if (
      !picking ||
      landedOnSomething(event.originalEvent.target) ||
      measuring()
    ) {
      return;
    }
    const { lat, lng } = event.latlng;
    try {
      const response = await fetch(
        `${HTTP_URL}coordinates/?lat=${lat}&lng=${lng}`,
      );
      const body = await response.json();
      setCopied(false);
      setPicked({
        at: event.latlng,
        text: body.text,
        all: body.all ?? {},
        elevationFt:
          typeof body.elevation_ft === "number" ? body.elevation_ft : undefined,
      });
    } catch (error) {
      console.error("Could not read the coordinates of that point", error);
    }
  });

  const copy = async (text: string) => {
    setCopied(await copyText(text));
  };

  // Putting the tool down takes the open popup with it.
  const toggle = () => {
    setPicking((on) => !on);
    setPicked(null);
  };

  if (picked === null) {
    return <PickerToggle on={picking} toggle={toggle} />;
  }

  return (
    <>
      <PickerToggle on={picking} toggle={toggle} />
      <Marker
        ref={marker}
        position={picked.at}
        icon={CROSSHAIR}
        eventHandlers={{ popupclose: () => setPicked(null) }}
      >
        <Popup autoPan={false}>
          <div className="cp-popup">
            <div
              className="cp-text"
              title="Copy"
              onClick={() => copy(picked.text)}
            >
              {picked.text}
            </div>
            <button onClick={() => copy(picked.text)}>
              {copied ? "Copied" : "Copy"}
            </button>
            <SavePoint
              at={picked.at}
              name={picked.text}
              elevationFt={picked.elevationFt}
            />
            <div className="cp-others">
              {Object.entries(picked.all)
                .filter(([, text]) => text !== picked.text)
                .map(([name, text]) => (
                  <div key={name} onClick={() => copy(text)} title="Copy">
                    {text}
                  </div>
                ))}
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
}
