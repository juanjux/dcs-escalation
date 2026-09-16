// Read the coordinates of any point on the map.
//
// Everything on the map that has coordinates is an objective, a base or a waypoint, and
// each of those opens something when clicked. This is for the rest of the map: turn the
// picker on, click anywhere, and the point is reported in the campaign's coordinate
// format with a button that copies it.
//
// The formatting is the server's, so the picker, the objective dialog and anything
// added later say the same thing about the same spot.
import { HTTP_URL } from "../../api/backend";
import { copyText } from "./clipboard";
import "./CoordinatePicker.css";
import L, { LatLng } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Marker, Popup, useMap, useMapEvent } from "react-leaflet";

interface Picked {
  at: LatLng;
  text: string;
  all: Record<string, string>;
}

const CROSSHAIR = L.divIcon({
  className: "",
  html: '<div class="cp-crosshair"></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export default function CoordinatePicker() {
  const map = useMap();
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [copied, setCopied] = useState(false);
  const pickingRef = useRef(picking);
  pickingRef.current = picking;

  useEffect(() => {
    const control = new L.Control({ position: "topleft" });
    const el = L.DomUtil.create("div");
    L.DomEvent.disableClickPropagation(el);
    control.onAdd = () => el;
    control.addTo(map);
    setPortalEl(el);
    return () => {
      control.remove();
    };
  }, [map]);

  // The cursor is the only sign the map is waiting for a click.
  useEffect(() => {
    const container = map.getContainer();
    container.style.cursor = picking ? "crosshair" : "";
    return () => {
      container.style.cursor = "";
    };
  }, [map, picking]);

  useMapEvent("click", async (event) => {
    if (!pickingRef.current) {
      return;
    }
    const { lat, lng } = event.latlng;
    try {
      const response = await fetch(
        `${HTTP_URL}coordinates/?lat=${lat}&lng=${lng}`,
      );
      const body = await response.json();
      setCopied(false);
      setPicked({ at: event.latlng, text: body.text, all: body.all ?? {} });
    } catch (error) {
      console.error("Could not read the coordinates of that point", error);
    }
  });

  const copy = async (text: string) => {
    setCopied(await copyText(text));
  };

  return (
    <>
      {portalEl !== null &&
        createPortal(
          <button
            className={"cp-button" + (picking ? " active" : "")}
            title="Read the coordinates of a point on the map"
            onClick={() => setPicking(!picking)}
          >
            ⊕
          </button>,
          portalEl,
        )}
      {picked !== null && (
        <Marker
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
      )}
    </>
  );
}
