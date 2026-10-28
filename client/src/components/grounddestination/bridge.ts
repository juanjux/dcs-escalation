import { LatLngLiteral } from "leaflet";

export interface RoutePreview {
  valid: boolean;
  error?: string;
  position?: LatLngLiteral;
  road_distance_m?: number;
  offroad_distance_m?: number;
  arrival_in_turns?: number;
  distance_m?: number;
  target_name?: string;
  warning?: string;
  segments?: { start: LatLngLiteral; end: LatLngLiteral; on_road: boolean }[];
}

export interface DestinationBridge {
  ready: () => void;
  initial: (done: (json: string) => void) => void;
  preview: (lat: number, lng: number, done: (json: string) => void) => void;
  pick: (lat: number, lng: number, done: (json: string) => void) => void;
  dismiss: () => void;
}

declare global {
  interface Window {
    groundDestinationModeReady?: boolean;
  }
}

export function bridgeCall<T>(
  invoke: (done: (json: string) => void) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () =>
        reject(
          new Error(
            "The campaign did not respond. Close and reopen the selector.",
          ),
        ),
      10000,
    );
    try {
      invoke((json) => {
        clearTimeout(timer);
        try {
          resolve(JSON.parse(json));
        } catch (error) {
          reject(error);
        }
      });
    } catch (error) {
      clearTimeout(timer);
      reject(error);
    }
  });
}

// Limit routing work to one request at a time. A response for an older cursor
// position must never enable a click at the newer one.
export class DestinationPreviewController {
  private timer?: ReturnType<typeof setTimeout>;
  private position?: LatLngLiteral;
  private version = 0;
  private busy = false;
  private stopped = false;
  private current?: RoutePreview;
  private choosing = false;

  constructor(
    private bridge: DestinationBridge,
    private pending: (position: LatLngLiteral) => void,
    private received: (result: RoutePreview) => void,
  ) {}

  move(position: LatLngLiteral) {
    if (this.stopped || this.choosing || this.samePosition(position)) return;
    this.position = position;
    this.version++;
    this.current = undefined;
    this.pending(position);
    this.schedule();
  }

  private samePosition(at: LatLngLiteral) {
    return at.lat === this.position?.lat && at.lng === this.position?.lng;
  }

  private schedule() {
    if (!this.timer && !this.busy && !this.stopped) {
      this.timer = setTimeout(() => this.preview(), 150);
    }
  }

  private async preview() {
    this.timer = undefined;
    const at = this.position;
    if (!at || this.stopped) return;
    const version = this.version;
    this.busy = true;
    let result: RoutePreview;
    try {
      result = await bridgeCall<RoutePreview>((done) =>
        this.bridge.preview(at.lat, at.lng, done),
      );
    } catch (error) {
      result = { valid: false, error: String(error) };
    }
    this.busy = false;
    if (this.stopped) return;
    if (this.version !== version) {
      this.schedule();
      return;
    }
    this.current = result;
    this.received(result);
  }

  async pick(at: LatLngLiteral) {
    if (this.stopped || this.choosing) return;
    if (!this.samePosition(at)) {
      this.move(at);
      return;
    }
    if (!this.current?.valid) return;
    this.choosing = true;
    this.pending(at);
    try {
      const result = await bridgeCall<RoutePreview>((done) =>
        this.bridge.pick(at.lat, at.lng, done),
      );
      if (!this.stopped) {
        this.current = result;
        this.received(result);
        if (result.valid) this.dispose();
      }
    } catch (error) {
      if (!this.stopped) this.received({ valid: false, error: String(error) });
    } finally {
      this.choosing = false;
    }
  }

  leave() {
    this.version++;
    this.position = undefined;
    this.current = undefined;
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
  }

  dispose() {
    this.stopped = true;
    this.leave();
  }
}
