export {};

it("does not open an event-stream connection for a destination picker", () => {
  const original = window.location.href;
  window.history.replaceState({}, "", "?groundDestination=1");
  const socket = jest
    .spyOn(window, "WebSocket")
    .mockImplementation(() => ({}) as WebSocket);
  try {
    jest.isolateModules(() => {
      require("../socketprovider/socketprovider");
    });
    expect(socket).not.toHaveBeenCalled();
  } finally {
    window.history.replaceState({}, "", original);
    socket.mockRestore();
  }
});

it("keeps the normal campaign event-stream connection", () => {
  const socket = jest
    .spyOn(window, "WebSocket")
    .mockImplementation(() => ({}) as WebSocket);
  try {
    jest.isolateModules(() => {
      require("../socketprovider/socketprovider");
    });
    expect(socket).toHaveBeenCalledTimes(1);
  } finally {
    socket.mockRestore();
  }
});
