import { ControlPoint } from "../../api/_liberationApi";
import { Icon, IconOptions, Point } from "leaflet";
import ms from "milsymbol";
import { healthBarSvg } from "../health/health";

export class ControlPointIcon extends Icon {
  constructor(
    readonly controlPointId: string,
    options: IconOptions,
  ) {
    super(options);
  }
}

export const iconForControlPoint = (cp: ControlPoint) => {
  const symbol = new ms.Symbol(cp.sidc, {
    size: 24,
    colorMode: "Dark",
  });

  return new ControlPointIcon(cp.id, {
    iconUrl:
      "data:image/svg+xml;charset=utf-8," +
      encodeURIComponent(healthBarSvg(symbol.asSVG(), cp.health)),
    iconAnchor: new Point(symbol.getAnchor().x, symbol.getAnchor().y),
  });
};
