import {
  bridgeCall,
  DestinationBridge,
  DestinationPreviewController,
  RoutePreview,
} from "./bridge";

const a = { lat: 42, lng: 41 };
const b = { lat: 43, lng: 42 };
const ok: RoutePreview = {
  valid: true,
  road_distance_m: 20000,
  offroad_distance_m: 3000,
  arrival_in_turns: 1,
  segments: [{ start: a, end: b, on_road: true }],
};

function setup() {
  const bridge: DestinationBridge = {
    ready: jest.fn(),
    initial: jest.fn(),
    preview: jest.fn(),
    pick: jest.fn(),
    dismiss: jest.fn(),
  };
  const pending = jest.fn();
  const received = jest.fn();
  const controller = new DestinationPreviewController(
    bridge,
    pending,
    received,
  );
  return { bridge, pending, received, controller };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}
beforeEach(() => jest.useFakeTimers());
afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
});

it("coalesces mouse moves into one preview for the latest position", async () => {
  const { controller, bridge, pending, received } = setup();
  controller.move(a);
  controller.move(b);
  expect(pending).toHaveBeenLastCalledWith(b);
  expect(bridge.preview).not.toHaveBeenCalled();
  jest.advanceTimersByTime(150);
  expect(bridge.preview).toHaveBeenCalledTimes(1);
  expect(bridge.preview).toHaveBeenCalledWith(
    b.lat,
    b.lng,
    expect.any(Function),
  );
  (bridge.preview as jest.Mock).mock.calls[0][2](JSON.stringify(ok));
  await flush();
  expect(received).toHaveBeenCalledWith(ok);
  controller.dispose();
});

it("never runs overlapping previews or accepts a stale response", async () => {
  const { controller, bridge, received } = setup();
  controller.move(a);
  jest.advanceTimersByTime(150);
  controller.move(b);
  jest.advanceTimersByTime(1000);
  expect(bridge.preview).toHaveBeenCalledTimes(1);
  (bridge.preview as jest.Mock).mock.calls[0][2](JSON.stringify(ok));
  await flush();
  expect(received).not.toHaveBeenCalled();
  await controller.pick(b);
  expect(bridge.pick).not.toHaveBeenCalled();
  jest.advanceTimersByTime(150);
  expect(bridge.preview).toHaveBeenCalledTimes(2);
  (bridge.preview as jest.Mock).mock.calls[1][2](
    JSON.stringify({ valid: false, error: "Enemy territory" }),
  );
  await flush();
  expect(received).toHaveBeenCalledWith({
    valid: false,
    error: "Enemy territory",
  });
  controller.dispose();
});

it("does not choose an invalid or still pending position", async () => {
  const { controller, bridge } = setup();
  controller.move(a);
  await controller.pick(a);
  jest.advanceTimersByTime(150);
  (bridge.preview as jest.Mock).mock.calls[0][2](
    '{"valid":false,"error":"No road access"}',
  );
  await flush();
  await controller.pick(a);
  expect(bridge.pick).not.toHaveBeenCalled();
  controller.dispose();
});

it("revalidates a valid click through the bridge and prevents double clicks", async () => {
  const { controller, bridge } = setup();
  (bridge.preview as jest.Mock).mockImplementation((lat, lng, done) =>
    done(JSON.stringify(ok)),
  );
  controller.move(a);
  jest.advanceTimersByTime(150);
  await flush();
  const first = controller.pick(a);
  await controller.pick(a);
  expect(bridge.pick).toHaveBeenCalledTimes(1);
  (bridge.pick as jest.Mock).mock.calls[0][2](JSON.stringify(ok));
  await first;
  controller.move(b);
  await controller.pick(a);
  expect(bridge.pick).toHaveBeenCalledTimes(1);
});

it("does not reuse a valid hover for a different clicked coordinate", async () => {
  const { controller, bridge } = setup();
  (bridge.preview as jest.Mock).mockImplementation((lat, lng, done) =>
    done(JSON.stringify(ok)),
  );
  controller.move(a);
  jest.advanceTimersByTime(150);
  await flush();
  await controller.pick(b);
  expect(bridge.pick).not.toHaveBeenCalled();
  controller.dispose();
});

it("shows a click-time rejection and allows another destination", async () => {
  const { controller, bridge, received } = setup();
  (bridge.preview as jest.Mock).mockImplementation((lat, lng, done) =>
    done(JSON.stringify(ok)),
  );
  (bridge.pick as jest.Mock).mockImplementation((lat, lng, done) =>
    done('{"valid":false,"error":"The campaign changed"}'),
  );
  controller.move(a);
  jest.advanceTimersByTime(150);
  await flush();
  await controller.pick(a);
  expect(received).toHaveBeenLastCalledWith({
    valid: false,
    error: "The campaign changed",
  });
  controller.move(b);
  jest.advanceTimersByTime(150);
  await flush();
  expect(bridge.preview).toHaveBeenCalledTimes(2);
  controller.dispose();
});

it("discards a response after leaving the map or closing the picker", async () => {
  const { controller, bridge, received } = setup();
  controller.move(a);
  jest.advanceTimersByTime(150);
  controller.leave();
  (bridge.preview as jest.Mock).mock.calls[0][2](JSON.stringify(ok));
  await flush();
  expect(received).not.toHaveBeenCalled();
  controller.move(b);
  controller.dispose();
  jest.advanceTimersByTime(300);
  expect(bridge.preview).toHaveBeenCalledTimes(1);
});

it("turns bridge failures and malformed responses into a blocked route", async () => {
  const { controller, bridge, received } = setup();
  (bridge.preview as jest.Mock).mockImplementation((lat, lng, done) =>
    done("bad JSON"),
  );
  controller.move(a);
  jest.advanceTimersByTime(150);
  await flush();
  expect(received).toHaveBeenCalledWith(
    expect.objectContaining({ valid: false }),
  );
  controller.dispose();
});

it("times out instead of leaving the cursor permanently pending", async () => {
  const promise = bridgeCall(() => {});
  const rejection = expect(promise).rejects.toThrow("campaign did not respond");
  jest.advanceTimersByTime(10000);
  await rejection;
});
