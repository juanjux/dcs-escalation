import { LatLngLiteral, Map, Marker } from "leaflet";
import TgoIcon from "../tgos/TgoIcon";

export interface SnapTarget {
  id: string;
  name: string;
  position: LatLngLiteral;
}

/** Use visible icon bounds in pixels, not a distance that changes with zoom. */
export function snapMissileTarget(
  map: Map,
  cursor: Pick<MouseEvent, "clientX" | "clientY">,
  position: LatLngLiteral,
  targets: ReadonlyMap<string, SnapTarget>,
): LatLngLiteral {
  let hit: { position: LatLngLiteral; z: number; distance: number } | undefined;
  map.eachLayer((layer) => {
    if (!(layer instanceof Marker)) return;
    const icon = layer.options.icon;
    if (!(icon instanceof TgoIcon)) return;
    const target = targets.get(icon.tgoId);
    const element = layer.getElement();
    if (!target || !element || !map.getContainer().contains(element)) return;
    const box = element.getBoundingClientRect();
    if (
      box.width <= 0 ||
      box.height <= 0 ||
      cursor.clientX < box.left ||
      cursor.clientX > box.right ||
      cursor.clientY < box.top ||
      cursor.clientY > box.bottom
    )
      return;
    const style = window.getComputedStyle(element);
    if (style.visibility === "hidden" || style.display === "none") return;
    const z = Number(style.zIndex) || 0;
    const distance = Math.hypot(
      cursor.clientX - (box.left + box.right) / 2,
      cursor.clientY - (box.top + box.bottom) / 2,
    );
    if (!hit || z > hit.z || (z === hit.z && distance < hit.distance)) {
      hit = { position: target.position, z, distance };
    }
  });
  return hit?.position ?? position;
}
