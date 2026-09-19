// Putting the picked point into one of the player's own aircraft.
//
// A spot is worth writing down long before it is worth a flight plan, and it goes to
// one aircraft rather than into the plan everybody else flies. Only aircraft somebody
// is actually sitting in are offered: an AI has nobody in it to read a point.
//
// Which kinds an airframe is offered, and how many more of each it will take, are the
// server's answer -- they come off the aircraft's own limits -- so this asks rather
// than deciding.
import { HTTP_URL } from "../../api/backend";
import { LatLng } from "leaflet";
import { useEffect, useState } from "react";

interface Receiver {
  id: string;
  callsign: string;
  aircraft: string;
  departure: string;
  kinds: string[];
  room: Record<string, number>;
}

const LABEL: Record<string, string> = {
  waypoint: "waypoint",
  markpoint: "markpoint",
};

export default function SavePoint(props: { at: LatLng; name: string }) {
  const [receivers, setReceivers] = useState<Receiver[] | null>(null);
  const [chosen, setChosen] = useState<string>("");
  const [said, setSaid] = useState<string>("");

  useEffect(() => {
    let dropped = false;
    (async () => {
      try {
        const response = await fetch(`${HTTP_URL}saved-points/`);
        // Whatever comes back, this is a popup on the map: an error page, an older
        // server that has never heard of this, anything that is not a list of
        // aircraft leaves the control quiet rather than throwing inside a render.
        const body: unknown = response.ok ? await response.json() : null;
        const list: Receiver[] = Array.isArray(body) ? body : [];
        if (dropped) {
          return;
        }
        setReceivers(list);
        setChosen(list.length > 0 ? list[0].id : "");
      } catch (error) {
        console.error("Could not list the player's aircraft", error);
        setReceivers([]);
      }
    })();
    return () => {
      dropped = true;
    };
  }, []);

  if (receivers === null) {
    return null;
  }
  if (receivers.length === 0) {
    return (
      <div className="cp-save cp-save-none">No player aircraft to save to</div>
    );
  }

  const receiver = receivers.find((one) => one.id === chosen) ?? receivers[0];

  const save = async (kind: string) => {
    try {
      const response = await fetch(`${HTTP_URL}saved-points/${receiver.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: kind,
          name: props.name,
          lat: props.at.lat,
          lng: props.at.lng,
        }),
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const detail =
          body && typeof body === "object" && "detail" in body
            ? String((body as { detail: unknown }).detail)
            : "Could not save it";
        setSaid(detail);
        return;
      }
      const updated = body as Receiver | null;
      if (!updated || typeof updated.id !== "string") {
        setSaid("Saved");
        return;
      }
      setReceivers(
        receivers.map((one) => (one.id === updated.id ? updated : one)),
      );
      setSaid(`Saved to ${updated.callsign}`);
    } catch (error) {
      console.error("Could not save the point", error);
      setSaid("Could not save it");
    }
  };

  return (
    <div className="cp-save">
      <select value={receiver.id} onChange={(e) => setChosen(e.target.value)}>
        {receivers.map((one) => (
          <option
            key={one.id}
            value={one.id}
            title={`${one.callsign} · ${one.aircraft} · from ${one.departure}`}
          >
            {one.callsign} · {one.aircraft}
          </option>
        ))}
      </select>
      <div className="cp-save-buttons">
        {receiver.kinds.map((kind) => {
          const room = receiver.room[kind] ?? 0;
          return (
            <button
              key={kind}
              disabled={room <= 0}
              title={
                room > 0
                  ? `Room for ${room} more`
                  : `${receiver.callsign} has no room for another`
              }
              onClick={() => save(kind)}
            >
              Save as {LABEL[kind] ?? kind}
            </button>
          );
        })}
      </div>
      {said !== "" && <div className="cp-save-said">{said}</div>}
    </div>
  );
}
