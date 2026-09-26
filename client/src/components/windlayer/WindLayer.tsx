import { useEffect, useMemo, useState } from "react";
import { LayerGroup, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";

import backend from "../../api/backend";
import { useAppSelector } from "../../app/hooks";

// The turn's wind at one of the three levels DCS models, drawn as arrows across the
// part of the map in view. DCS blows the same wind everywhere at a level, so every
// arrow of a layer is the same; the grid only keeps one in sight wherever you look.

export interface WindLevel {
  altitude_m: number;
  // Where the wind blows to, in degrees, as DCS keeps it.
  blows_to: number;
  speed_mps: number;
}

const SPACING_PX = 160;
const LEVELS: Record<number, { label: string; color: string; offset: number }> = {
  0: { label: "SFC", color: "#7fd3ff", offset: 0 },
  2000: { label: "2000 m", color: "#ffd27f", offset: 1 },
  8000: { label: "8000 m", color: "#ff9fe0", offset: 2 },
};

const knots = (mps: number) => Math.round(mps * 1.94384);

export function windLabel(wind: WindLevel): string {
  const level = LEVELS[wind.altitude_m]?.label ?? `${wind.altitude_m} m`;
  const speed = knots(wind.speed_mps);
  if (speed === 0) {
    return `${level} calm`;
  }
  const from = (Math.round(wind.blows_to) + 180) % 360;
  return `${level} from ${String(from).padStart(3, "0")}° ${speed} kt`;
}

function windIcon(wind: WindLevel): L.DivIcon {
  const color = LEVELS[wind.altitude_m]?.color ?? "#ffffff";
  const arrow =
    knots(wind.speed_mps) === 0
      ? `<circle cx="16" cy="16" r="5" fill="none" stroke="${color}" stroke-width="2"/>`
      : `<g transform="rotate(${wind.blows_to} 16 16)">` +
        `<line x1="16" y1="28" x2="16" y2="8" stroke="${color}" stroke-width="2.5"/>` +
        `<polygon points="16,2 10,12 22,12" fill="${color}"/></g>`;
  return L.divIcon({
    className: "",
    iconSize: [120, 52],
    iconAnchor: [60, 16],
    html:
      `<div style="display:flex;flex-direction:column;align-items:center;` +
      `pointer-events:none;filter:drop-shadow(0 0 2px #000)">` +
      `<svg width="32" height="32" viewBox="0 0 32 32">${arrow}</svg>` +
      `<span style="color:${color};font:600 11px sans-serif;white-space:nowrap">` +
      `${windLabel(wind)}</span></div>`,
  });
}

interface WindLayerProps {
  altitude: number;
}

export default function WindLayer(props: WindLayerProps) {
  const map = useMap();
  // Changes when a game or a new turn is loaded, which is when the wind changes.
  const center = useAppSelector((state) => state.map.center);
  const [wind, setWind] = useState<WindLevel | null>(null);
  const [view, setView] = useState(0);

  useEffect(() => {
    let live = true;
    backend
      .get<WindLevel[]>("game/wind")
      .then((response) => {
        if (live) {
          setWind(
            response.data.find((w) => w.altitude_m === props.altitude) ?? null
          );
        }
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [props.altitude, center]);

  useMapEvents({
    moveend: () => setView((v) => v + 1),
    zoomend: () => setView((v) => v + 1),
  });

  const points = useMemo(() => {
    const size = map.getSize();
    const shift = ((LEVELS[props.altitude]?.offset ?? 0) * SPACING_PX) / 3;
    const out: L.LatLng[] = [];
    for (let x = SPACING_PX / 2 + shift; x < size.x; x += SPACING_PX) {
      for (let y = SPACING_PX / 2; y < size.y; y += SPACING_PX) {
        out.push(map.containerPointToLatLng([x, y]));
      }
    }
    return out;
    // `view` only asks for a recompute when the map moves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, view, props.altitude]);

  const icon = useMemo(() => (wind ? windIcon(wind) : null), [wind]);
  if (icon === null) {
    return null;
  }
  return (
    <LayerGroup>
      {points.map((point, idx) => (
        <Marker key={idx} position={point} icon={icon} interactive={false} />
      ))}
    </LayerGroup>
  );
}
