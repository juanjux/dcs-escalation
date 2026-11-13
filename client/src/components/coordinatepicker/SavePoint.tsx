// GPS points belong to the campaign, not to a particular player flight.
import { HTTP_URL } from "../../api/backend";
import { LatLng } from "leaflet";
import { useState } from "react";

export default function SavePoint(props: {
  at: LatLng;
  defaultName: string;
  elevationFt?: number;
}) {
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [feet, setFeet] = useState<string>(
    props.elevationFt === undefined ? "" : String(props.elevationFt),
  );

  const save = async (name: string) => {
    setBusy(true);
    setSaid("");
    try {
      const response = await fetch(`${HTTP_URL}saved-points/campaign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "waypoint",
          name: name.trim() || props.defaultName,
          lat: props.at.lat,
          lng: props.at.lng,
          altitude_ft: Math.max(0, Math.round(Number(feet) || 0)),
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
      window.dispatchEvent(new Event("saved-points-changed"));
      setName(null);
      setSaid("Saved to campaign");
    } catch (error) {
      console.error("Could not save the point", error);
      setSaid("Could not save it");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cp-save">
      <div>Campaign GPS points · shared by all player aircraft</div>
      <label className="cp-save-alt">
        Elevation{props.elevationFt === undefined ? "" : " (ground)"}
        <input
          type="number"
          min={0}
          step={100}
          value={feet}
          placeholder="0"
          disabled={busy}
          onChange={(e) => setFeet(e.target.value)}
        />
        ft
      </label>
      {name === null ? (
        <div className="cp-save-buttons">
          <button
            type="button"
            onClick={() => {
              setSaid("");
              setName(props.defaultName);
            }}
          >
            Save as waypoint
          </button>
        </div>
      ) : (
        <form
          className="cp-save-asking"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void save(name);
          }}
        >
          <label className="cp-save-name">
            Waypoint name
            <input
              type="text"
              autoFocus
              onFocus={(event) => event.target.select()}
              value={name}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div className="cp-save-buttons">
            <button type="submit" disabled={busy}>
              Save
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setName(null);
                setSaid("");
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {said !== "" && (
        <div className="cp-save-said" role="status">
          {said}
        </div>
      )}
    </div>
  );
}
