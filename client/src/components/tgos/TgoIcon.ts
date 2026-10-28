import { Icon, IconOptions } from "leaflet";

/** Identify a rendered objective without enabling its normal map interactions. */
export default class TgoIcon extends Icon {
  constructor(
    readonly tgoId: string,
    options: IconOptions,
  ) {
    super(options);
  }
}
