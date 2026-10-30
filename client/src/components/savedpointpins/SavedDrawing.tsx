import { HTTP_URL } from "../../api/backend";
import { useEffect, useState } from "react";
import { Polygon, Polyline, Popup, Tooltip } from "react-leaflet";

export interface Drawing {
  id: string;
  name: string;
  closed: boolean;
  points: { lat: number; lng: number }[];
}

export default function SavedDrawing({
  drawing,
  flightId,
}: {
  drawing: Drawing;
  flightId: string;
}) {
  const [name, setName] = useState(drawing.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setName(drawing.name), [drawing.name]);
  const mutate = async (method: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `${HTTP_URL}saved-points/${flightId}/drawings/${drawing.id}`,
        {
          method,
          headers: { "Content-Type": "application/json" },
          ...(method === "PATCH" ? { body: JSON.stringify({ name }) } : {}),
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "Could not update drawing",
        );
      }
      window.dispatchEvent(new Event("saved-points-changed"));
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Could not update drawing",
      );
    } finally {
      setBusy(false);
    }
  };
  const Shape = drawing.closed ? Polygon : Polyline;
  return (
    <Shape
      positions={drawing.points}
      bubblingMouseEvents={false}
      pathOptions={{ color: "#ffdf32", weight: 3, fillOpacity: 0.12 }}
    >
      <Tooltip>{drawing.name}</Tooltip>
      <Popup autoPan={false}>
        <form
          className="saved-point-editor"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim() && !busy) void mutate("PATCH");
          }}
        >
          <label>
            Drawing name
            <input
              aria-label="Drawing name"
              maxLength={24}
              value={name}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div>
            {drawing.closed ? "Area" : "Line"} · {drawing.points.length}{" "}
            vertices
          </div>
          <div className="saved-point-buttons">
            <button disabled={busy || !name.trim()} type="submit">
              Rename
            </button>
            <button
              disabled={busy}
              type="button"
              onClick={() => void mutate("DELETE")}
            >
              Delete drawing
            </button>
          </div>
          {error && <div role="alert">{error}</div>}
        </form>
      </Popup>
    </Shape>
  );
}
