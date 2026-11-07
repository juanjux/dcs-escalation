// GPS points belong to the campaign, not to a particular player flight.
import { HTTP_URL } from "../../api/backend";
import { LatLng } from "leaflet";
import { useState } from "react";

export default function SavePoint(props: {
  at: LatLng;
  name: string;
  elevationFt?: number;
}) {
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const [feet, setFeet] = useState<string>(
    props.elevationFt === undefined ? "" : String(props.elevationFt),
  );

  const save = async () => {
    setBusy(true);
    setSaid("");
    try {
      const response = await fetch(`${HTTP_URL}saved-points/campaign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "waypoint",
          name: props.name,
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
      <div className="cp-save-buttons">
        <button disabled={busy} onClick={() => void save()}>
          Save as waypoint
        </button>
      </div>
      {said !== "" && <div className="cp-save-said">{said}</div>}
    </div>
  );
}
