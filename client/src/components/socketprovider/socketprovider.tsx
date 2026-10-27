// Based on https://thenable.io/building-a-use-socket-hook-in-react.
import { WEBSOCKET_URL } from "../../api/backend";
import { ReactChild, createContext, useEffect, useState } from "react";

// A modal destination map only reads the campaign once. Do not leave another
// event-stream connection behind when its WebEngine page is closed.
const socket = new URL(window.location.toString()).searchParams.has(
  "groundDestination",
)
  ? null
  : new WebSocket(WEBSOCKET_URL);

export const SocketContext = createContext(socket);

interface SocketProviderProps {
  children: ReactChild;
}

export const SocketProvider = (props: SocketProviderProps) => {
  const [ws, setWs] = useState<WebSocket | null>(socket);
  useEffect(() => {
    if (ws === null) return;
    const onClose = () => {
      setWs(new WebSocket(WEBSOCKET_URL));
    };

    const onError = (error: Event) => {
      console.log(`Websocket error: ${error}`);
    };

    ws.addEventListener("close", onClose);
    ws.addEventListener("error", onError);

    return () => {
      ws.removeEventListener("close", onClose);
      ws.removeEventListener("error", onError);
    };
  });

  return (
    <SocketContext.Provider value={ws}>{props.children}</SocketContext.Provider>
  );
};
