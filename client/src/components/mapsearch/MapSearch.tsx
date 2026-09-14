// Find a place on the map by typing its name.
//
// A log line or a message from the OPFOR planner names a site -- MINK, or "the Patriot
// north of Creech" -- and finding it meant panning around looking for a code name among
// two hundred icons. This searches what the map already knows: every objective and every
// base, by name AND by what is parked there, so "Patriot" or "Linebacker" finds the site
// that holds one even though the site is called something else entirely.
//
// Entirely client-side: the tgos and controlPoints slices carry the names, the unit
// lists and the categories, so there is nothing to ask the server for.
import { Tgo, ControlPoint } from "../../api/liberationApi";
import { selectControlPoints } from "../../api/controlPointsSlice";
import { setHoveredEmitter, setMapCenter } from "../../api/mapSlice";
import { selectTgos } from "../../api/tgosSlice";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import "./MapSearch.css";
import L, { LatLng } from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMap } from "react-leaflet";

// The kinds worth filtering by, and which objective categories fall into each. Grouped
// rather than one chip per category -- twenty-one chips is a list to read -- except
// where the difference is one worth acting on: a factory is what lets a base recruit
// ground units, and the three kinds of stores are each worth a different sortie.
const KINDS: { id: string; label: string; categories: string[] }[] = [
  { id: "base", label: "Bases", categories: [] },
  {
    id: "airdefense",
    label: "Air defence",
    categories: ["aa", "missile", "coastal"],
  },
  { id: "radar", label: "Radar", categories: ["ewr"] },
  {
    id: "command",
    label: "Command & comms",
    categories: ["commandcenter", "comms"],
  },
  { id: "power", label: "Power", categories: ["power"] },
  { id: "armor", label: "Armor", categories: ["armor", "motorpool"] },
  { id: "ship", label: "Ships", categories: ["ship"] },
  { id: "factory", label: "Factories", categories: ["factory"] },
  { id: "ware", label: "Warehouses", categories: ["ware"] },
  { id: "fuel", label: "Fuel depots", categories: ["fuel"] },
  { id: "derrick", label: "Oil & derricks", categories: ["derrick", "oil"] },
  {
    id: "building",
    label: "Other buildings",
    categories: ["allycamp", "ammo", "farp", "fob", "village", "ww2bunker"],
  },
];

// What the server calls each category, so a search for "command center" finds one and
// the row says what it is. Mirrors NAME_BY_CATEGORY in theatergroundobject.py.
const CATEGORY_LABELS: Record<string, string> = {
  aa: "AA defence site",
  allycamp: "Camp",
  ammo: "Ammo depot",
  armor: "Armor group",
  coastal: "Coastal defence",
  commandcenter: "Command centre",
  comms: "Communications tower",
  derrick: "Derrick",
  ewr: "Early warning radar",
  factory: "Factory",
  farp: "FARP",
  fob: "FOB",
  fuel: "Fuel depot",
  missile: "Missile site",
  motorpool: "Motorpool",
  oil: "Oil platform",
  power: "Power plant",
  ship: "Ship",
  village: "Village",
  ware: "Warehouse",
  ww2bunker: "Bunker",
};

const KIND_OF_CATEGORY: Record<string, string> = Object.fromEntries(
  KINDS.flatMap((kind) =>
    kind.categories.map((category) => [category, kind.id]),
  ),
);

interface Found {
  id: string;
  name: string;
  kind: string;
  label: string;
  blue: boolean;
  dead: boolean;
  position: LatLng;
  // What the search term matched, when it was not the name: the unit that put this
  // site in the list, so a search for "Patriot" says which of the code names is one.
  matched?: string;
  // Only objectives can be highlighted on the map; a base is not an emitter.
  highlightable: boolean;
}

function normalise(text: string): string {
  return text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function tgoToFound(tgo: Tgo): Found {
  return {
    id: tgo.id,
    name: tgo.name,
    kind: KIND_OF_CATEGORY[tgo.category] ?? "building",
    label: CATEGORY_LABELS[tgo.category] ?? tgo.category,
    blue: tgo.blue,
    dead: tgo.dead,
    position: tgo.position as LatLng,
    highlightable: true,
  };
}

function controlPointToFound(cp: ControlPoint): Found {
  return {
    id: cp.id,
    name: cp.name,
    kind: "base",
    label: "Base",
    blue: cp.blue,
    dead: cp.dead === true,
    position: cp.position as LatLng,
    highlightable: false,
  };
}

// Name first, then whatever is parked there. Returns the matching unit when the name
// was not what matched, so the row can say why it is in the list.
function matches(
  found: Found,
  units: string[],
  needle: string,
): { hit: boolean; matched?: string } {
  if (!needle) {
    return { hit: true };
  }
  if (normalise(found.name).includes(needle)) {
    return { hit: true };
  }
  if (normalise(found.label).includes(needle)) {
    return { hit: true };
  }
  const unit = units.find((each) => normalise(each).includes(needle));
  return unit ? { hit: true, matched: unit } : { hit: false };
}

export default function MapSearch() {
  const map = useMap();
  const dispatch = useAppDispatch();
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState("");
  const [kinds, setKinds] = useState<Set<string>>(new Set());
  const [sides, setSides] = useState<Set<string>>(new Set());
  const input = useRef<HTMLInputElement | null>(null);

  const tgos = useAppSelector(selectTgos).tgos;
  const controlPoints = useAppSelector(selectControlPoints).controlPoints;

  useEffect(() => {
    const control = new L.Control({ position: "topleft" });
    const el = L.DomUtil.create("div");
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
    control.onAdd = () => el;
    control.addTo(map);
    setPortalEl(el);
    return () => {
      control.remove();
    };
  }, [map]);

  useEffect(() => {
    if (open) {
      input.current?.focus();
    }
  }, [open]);

  const results = useMemo(() => {
    const trimmed = normalise(needle.trim());
    const found: Found[] = [];
    for (const cp of Object.values(controlPoints)) {
      const entry = controlPointToFound(cp);
      const { hit, matched } = matches(entry, cp.units ?? [], trimmed);
      if (hit) {
        found.push({ ...entry, matched });
      }
    }
    for (const tgo of Object.values(tgos)) {
      const entry = tgoToFound(tgo);
      const { hit, matched } = matches(entry, tgo.units ?? [], trimmed);
      if (hit) {
        found.push({ ...entry, matched });
      }
    }
    const wanted = found.filter(
      (entry) =>
        (kinds.size === 0 || kinds.has(entry.kind)) &&
        (sides.size === 0 || sides.has(entry.blue ? "blue" : "red")),
    );
    // Alive before wrecks, then by name: what you are looking for is usually still
    // standing, and a list that reorders as you type is one you cannot aim at.
    wanted.sort(
      (a, b) => Number(a.dead) - Number(b.dead) || a.name.localeCompare(b.name),
    );
    return wanted;
  }, [tgos, controlPoints, needle, kinds, sides]);

  const toggle = (set: Set<string>, id: string): Set<string> => {
    const next = new Set(set);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    return next;
  };

  const go = (entry: Found) => {
    // Through the store rather than straight to Leaflet: the map re-centres itself on
    // whatever the store says, so a flyTo would be undone by the next render.
    dispatch(setMapCenter(entry.position));
  };

  const highlight = (entry: Found | null) => {
    if (entry && !entry.highlightable) {
      return;
    }
    dispatch(
      entry === null
        ? setHoveredEmitter(null)
        : setHoveredEmitter({ id: entry.id, source: "ring" }),
    );
  };

  const panel = open ? (
    <div className="ms-panel">
      <div className="ms-header">
        <input
          ref={input}
          className="ms-input"
          value={needle}
          placeholder="Find a place, or what is parked there…"
          onChange={(event) => setNeedle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
            } else if (event.key === "Enter" && results.length) {
              go(results[0]);
            }
          }}
        />
        <button
          className="ms-close"
          title="Close"
          onClick={() => {
            setOpen(false);
            highlight(null);
          }}
        >
          ✕
        </button>
      </div>
      <div className="ms-filters">
        <button
          className={"ms-chip" + (sides.has("blue") ? " active" : "")}
          onClick={() => setSides(toggle(sides, "blue"))}
        >
          Allied
        </button>
        <button
          className={"ms-chip" + (sides.has("red") ? " active" : "")}
          onClick={() => setSides(toggle(sides, "red"))}
        >
          Enemy
        </button>
        {KINDS.map((kind) => (
          <button
            key={kind.id}
            className={"ms-chip" + (kinds.has(kind.id) ? " active" : "")}
            onClick={() => setKinds(toggle(kinds, kind.id))}
          >
            {kind.label}
          </button>
        ))}
      </div>
      <div className="ms-results">
        {results.length === 0 ? (
          <div className="ms-empty">Nothing on the map matches that.</div>
        ) : (
          results.slice(0, 200).map((entry) => (
            <button
              key={entry.id}
              className="ms-row"
              onClick={() => go(entry)}
              onMouseEnter={() => highlight(entry)}
              onMouseLeave={() => highlight(null)}
            >
              <span
                className={
                  "ms-name" +
                  (entry.blue ? "" : " enemy") +
                  (entry.dead ? " dead" : "")
                }
              >
                {entry.name}
              </span>
              {entry.matched ? (
                <span className="ms-match">{entry.matched}</span>
              ) : null}
              <span className="ms-kind">{entry.label}</span>
            </button>
          ))
        )}
      </div>
    </div>
  ) : (
    <button
      className="ms-toggle"
      title="Find a place on the map"
      onClick={() => setOpen(true)}
    >
      🔍
    </button>
  );

  return <>{portalEl && createPortal(panel, portalEl)}</>;
}
