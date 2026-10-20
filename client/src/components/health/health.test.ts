import ms from "milsymbol";
import { HealthStatus } from "../../api/liberationApi";
import { healthBarSvg } from "./health";

const health: HealthStatus = {
  health_percent: 65,
  damage_repaired_per_turn_percent: 30,
  repair_next_turn_percent: 10.5,
  health_next_turn_percent: 75.5,
  units: [
    {
      id: 1,
      name: "Ship",
      health_percent: 65,
      persistent: true,
      damage_repaired_per_turn_percent: 30,
      repair_next_turn_percent: 10.5,
      health_next_turn_percent: 75.5,
    },
  ],
};

it.each(["10031030001201000000", "10033030001201000000"])(
  "draws a proportional orange bar using real milsymbol geometry (%s)",
  (sidc) => {
    const original = new ms.Symbol(sidc, { size: 24 }).asSVG();
    const svg = healthBarSvg(original, health);
    expect(svg).toContain('fill="rgb(255,140,0)"');
    expect(svg).toContain('fill="#35404a"');
    const document = new DOMParser().parseFromString(svg, "image/svg+xml");
    const fill = document.querySelector('path[fill="rgb(255,140,0)"]');
    const track = document.querySelector('path[fill="#35404a"]');
    const width = (path: Element | null) =>
      Number(/ l([\d.]+),0/.exec(path?.getAttribute("d") ?? "")?.[1]);
    expect(width(fill) / width(track)).toBeCloseTo(0.65);
  },
);

it("keeps intact, destroyed and excluded units on their normal bars", () => {
  const original = new ms.Symbol("10031030001201000000", { size: 24 }).asSVG();
  expect(healthBarSvg(original)).toBe(original);
  expect(
    healthBarSvg(original, {
      ...health,
      units: health.units.map((unit) => ({ ...unit, persistent: false })),
    }),
  ).toBe(original);
  expect(
    healthBarSvg(original, {
      ...health,
      units: health.units.map((unit) => ({ ...unit, health_percent: 0 })),
    }),
  ).toBe(original);
});
