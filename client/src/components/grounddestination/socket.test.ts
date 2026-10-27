export {};

it("keeps one campaign socket while destination mode starts and stops", () => {
  const socket = jest
    .spyOn(window, "WebSocket")
    .mockImplementation(() => ({}) as WebSocket);
  try {
    jest.isolateModules(() => {
      require("../socketprovider/socketprovider");
    });
    window.dispatchEvent(
      new CustomEvent("ground-destination-start", { detail: { id: "one" } }),
    );
    window.dispatchEvent(
      new CustomEvent("ground-destination-end", { detail: { id: "one" } }),
    );
    expect(socket).toHaveBeenCalledTimes(1);
  } finally {
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
