import { Icon, Map, Marker } from "leaflet";
import TgoIcon from "../tgos/TgoIcon";
import { SnapTarget, snapMissileTarget } from "./targetSnap";

const target: SnapTarget = {
  id: "enemy",
  name: "MINK",
  position: { lat: 32.92, lng: 66.63 },
};
const free = { lat: 33.5, lng: 67.5 };
let container: HTMLDivElement;
let layers: Marker[];
let map: Map;

function marker(id = target.id, left = 100, z = 0) {
  const layer = new Marker([0, 0], {
    icon: new TgoIcon(id, { iconUrl: "test.svg" }),
  });
  const element = document.createElement("img");
  element.style.zIndex = String(z);
  container.appendChild(element);
  jest.spyOn(element, "getBoundingClientRect").mockReturnValue({
    left,
    right: left + 40,
    top: 80,
    bottom: 120,
    width: 40,
    height: 40,
  } as DOMRect);
  jest.spyOn(layer, "getElement").mockReturnValue(element);
  layers.push(layer);
  return { layer, element };
}

beforeEach(() => {
  container = document.createElement("div");
  layers = [];
  map = {
    eachLayer: (visit: (layer: Marker) => void) => layers.forEach(visit),
    getContainer: () => container,
  } as unknown as Map;
});

it("snaps within the displayed icon even when the cursor's GPS point is far away", () => {
  marker();
  const targets = new globalThis.Map([[target.id, target]]);
  expect(
    snapMissileTarget(map, { clientX: 110, clientY: 90 }, free, targets),
  ).toEqual(target.position);
  expect(
    snapMissileTarget(map, { clientX: 139, clientY: 119 }, free, targets),
  ).toEqual(target.position);
});

it("returns to free GPS coordinates immediately outside the icon", () => {
  marker();
  const targets = new globalThis.Map([[target.id, target]]);
  for (const cursor of [
    { clientX: 99, clientY: 100 },
    { clientX: 141, clientY: 100 },
    { clientX: 120, clientY: 79 },
    { clientX: 120, clientY: 121 },
  ])
    expect(snapMissileTarget(map, cursor, free, targets)).toBe(free);
});

it("uses current icon bounds after panning or zooming", () => {
  const { element } = marker();
  const targets = new globalThis.Map([[target.id, target]]);
  jest.spyOn(element, "getBoundingClientRect").mockReturnValue({
    left: 400,
    right: 440,
    top: 80,
    bottom: 120,
    width: 40,
    height: 40,
  } as DOMRect);
  expect(
    snapMissileTarget(map, { clientX: 110, clientY: 90 }, free, targets),
  ).toBe(free);
  expect(
    snapMissileTarget(map, { clientX: 410, clientY: 90 }, free, targets),
  ).toEqual(target.position);
});

it.each(["ineligible", "hidden", "removed", "zero-size", "unmarked"])(
  "does not snap to an %s icon",
  (kind) => {
    const { layer, element } = marker();
    const targets = new globalThis.Map([[target.id, target]]);
    if (kind === "ineligible") targets.clear();
    if (kind === "hidden") element.style.visibility = "hidden";
    if (kind === "removed") element.remove();
    if (kind === "zero-size")
      jest.spyOn(element, "getBoundingClientRect").mockReturnValue({
        left: 100,
        right: 140,
        top: 80,
        bottom: 120,
        width: 0,
        height: 0,
      } as DOMRect);
    if (kind === "unmarked") layer.setIcon(new Icon({ iconUrl: "other.svg" }));
    expect(
      snapMissileTarget(map, { clientX: 110, clientY: 90 }, free, targets),
    ).toBe(free);
  },
);

it("selects the topmost overlapping icon, breaking equal-height ties by distance", () => {
  marker();
  const other = { ...target, id: "other", position: free };
  const { element } = marker(other.id, 110, 10);
  const targets = new globalThis.Map([
    [target.id, target],
    [other.id, other],
  ]);
  expect(
    snapMissileTarget(map, { clientX: 115, clientY: 90 }, free, targets),
  ).toBe(free);
  element.style.zIndex = "0";
  expect(
    snapMissileTarget(map, { clientX: 115, clientY: 90 }, free, targets),
  ).toEqual(target.position);
});
