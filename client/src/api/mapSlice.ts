import { RootState } from "../app/store";
import { gameLoaded, gameUnloaded } from "./actions";
import { PayloadAction, createSlice } from "@reduxjs/toolkit";
import { LatLngLiteral } from "leaflet";

// Where a hover originated: the emitter's icon, or one of its range rings. The
// highlight is symmetric (hovering either lights up the other), but hovering a
// ring also marks its emitter with a blob so you can find it; hovering the
// emitter does not blob the icon you're already pointing at.
export type EmitterHoverSource = "emitter" | "ring";

interface MapState {
  center: LatLngLiteral;
  // How close to look when the centre was set by something that knows what it is
  // pointing at -- the command palette at a SAM site. Null leaves the zoom alone,
  // which is what moving the map around normally does.
  zoom: number | null;
  // Id of the TGO whose air-defense ring (or icon) is currently hovered, so its
  // icon can be raised above overlapping ones while highlighted.
  hoveredEmitterId: string | null;
  // What was hovered to set hoveredEmitterId (icon vs. ring).
  hoveredEmitterSource: EmitterHoverSource | null;
  // Whether the hover highlight (ring <-> emitter) is enabled. Toggled from
  // the map's layer control.
  highlightEmitters: boolean;
  // Whether fully-destroyed, non-repairable ground objects (buildings, ships,
  // ...) are shown on the map, per coalition. Toggled from the map's layer
  // control; defaults to shown. Repairable objects (SAM/EWR/armor) are never
  // hidden by this.
  showDestroyedNonRepairable: { blue: boolean; red: boolean };
}

const initialState: MapState = {
  center: { lat: 0, lng: 0 },
  zoom: null,
  hoveredEmitterId: null,
  hoveredEmitterSource: null,
  highlightEmitters: true,
  showDestroyedNonRepairable: { blue: true, red: true },
};

const mapSlice = createSlice({
  name: "map",
  initialState: initialState,
  reducers: {
    setHoveredEmitter(
      state,
      action: PayloadAction<{ id: string; source: EmitterHoverSource } | null>,
    ) {
      state.hoveredEmitterId = action.payload?.id ?? null;
      state.hoveredEmitterSource = action.payload?.source ?? null;
    },
    // Where the map should be looking. The map watches this rather than being moved
    // directly, because it re-centres itself on what the store says after every
    // render -- a flyTo of its own would be undone by the next one.
    setMapCenter(state, action: PayloadAction<LatLngLiteral>) {
      state.center = action.payload;
      state.zoom = null;
    },
    // Centre and zoom together, for something small enough that finding it at the
    // zoom you happened to be at is the hard part.
    setMapView(
      state,
      action: PayloadAction<{ center: LatLngLiteral; zoom: number | null }>,
    ) {
      state.center = action.payload.center;
      state.zoom = action.payload.zoom;
    },
    setHighlightEmitters(state, action: PayloadAction<boolean>) {
      state.highlightEmitters = action.payload;
    },
    setShowDestroyedNonRepairable(
      state,
      action: PayloadAction<{ blue: boolean; value: boolean }>,
    ) {
      if (action.payload.blue) {
        state.showDestroyedNonRepairable.blue = action.payload.value;
      } else {
        state.showDestroyedNonRepairable.red = action.payload.value;
      }
    },
  },
  extraReducers: (builder) => {
    builder.addCase(gameLoaded, (state, action) => {
      if (action.payload.map_center != null) {
        state.center = action.payload.map_center;
      }
    });
    builder.addCase(gameUnloaded, (state) => {
      state.center = { lat: 0, lng: 0 };
      state.hoveredEmitterId = null;
      state.hoveredEmitterSource = null;
    });
  },
});

export const {
  setHoveredEmitter,
  setHighlightEmitters,
  setMapCenter,
  setMapView,
  setShowDestroyedNonRepairable,
} = mapSlice.actions;

export const selectMapCenter = (state: RootState) => state.map.center;
export const selectMapZoom = (state: RootState) => state.map.zoom;
export const selectHoveredEmitter = (state: RootState) =>
  state.map.hoveredEmitterId;
export const selectHoveredEmitterSource = (state: RootState) =>
  state.map.hoveredEmitterSource;
export const selectHighlightEmitters = (state: RootState) =>
  state.map.highlightEmitters;
export const selectShowDestroyedNonRepairable = (state: RootState) =>
  state.map.showDestroyedNonRepairable;

export default mapSlice.reducer;
