import { SocketContext } from "../components/socketprovider/socketprovider";
import { useContext } from "react";

export const useSocket = () => {
  const socket = useContext(SocketContext);

  if (socket === null) {
    throw new Error(
      "The destination map does not subscribe to campaign events",
    );
  }

  return socket;
};
