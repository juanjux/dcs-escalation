// How often the "is this destination in range" question is worth asking while a
// marker is being dragged. Leaflet fires `drag` several times a frame; the answer
// changes once, when the marker crosses the range ring.
export const RANGE_CHECK_INTERVAL_MS = 120;
