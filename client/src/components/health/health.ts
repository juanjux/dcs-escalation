import { HealthStatus } from "../../api/liberationApi";

export function hasPersistentDamage(health?: HealthStatus | null): boolean {
  return (
    health?.units.some(
      (unit) =>
        unit.persistent && unit.health_percent > 0 && unit.health_percent < 100,
    ) ?? false
  );
}

export function healthBarSvg(
  svg: string,
  health?: HealthStatus | null,
): string {
  if (!hasPersistentDamage(health)) return svg;
  const fraction = Math.max(
    0,
    Math.min(1, (health?.health_percent ?? 100) / 100),
  );
  // Only milsymbol's rectangular condition bar, never the symbol frame or icon.
  return svg.replace(/<path\b[^>]*(?:\/>|>\s*<\/path>)/g, (path) => {
    const geometry =
      /d="M(-?[\d.]+),(-?[\d.]+) l([\d.]+),0 0,25 -[\d.]+,0 z"/.exec(path);
    if (!geometry || !/fill="rgb\((?:255,255,0|0,255,0)\)"/.test(path))
      return path;
    const [original, x, y, width] = geometry;
    const track = path.replace(/fill="[^"]*"/, 'fill="#35404a"');
    const fill = path
      .replace(
        original,
        `d="M${x},${y} l${Number(width) * fraction},0 0,25 -${Number(width) * fraction},0 z"`,
      )
      .replace(/fill="[^"]*"/, 'fill="rgb(255,140,0)"');
    return track + fill;
  });
}
