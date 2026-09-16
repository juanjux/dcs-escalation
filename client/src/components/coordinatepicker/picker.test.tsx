/**
 * The coordinates come up for a click on bare map, and not for one that landed on
 * something: Leaflet bubbles a click on a route or an icon up to the map as well, and
 * that click belongs to whatever was clicked.
 */
import { landedOnSomething } from "./CoordinatePicker";

function element(html: string): Element {
  const host = document.createElement("div");
  host.innerHTML = html;
  return host.firstElementChild as Element;
}

it("leaves a click that landed on a route alone", () => {
  const path = element('<svg><path class="leaflet-interactive"></path></svg>');
  expect(landedOnSomething(path.querySelector("path"))).toBe(true);
});

it("leaves a click that landed inside an icon alone", () => {
  const icon = element(
    '<div class="leaflet-marker-icon leaflet-interactive"><img></div>',
  );
  expect(landedOnSomething(icon.querySelector("img"))).toBe(true);
});

it("answers a click on the map itself", () => {
  const tile = element('<div class="leaflet-tile-container"><img></div>');
  expect(landedOnSomething(tile.querySelector("img"))).toBe(false);
});

it("answers a click with no target at all", () => {
  expect(landedOnSomething(null)).toBe(false);
});
