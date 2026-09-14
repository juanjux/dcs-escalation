import { selectFlights, selectSelectedFlight } from "../../api/flightsSlice";
import { Flight } from "../../api/liberationApi";
import { useAppSelector } from "../../app/hooks";
import FlightPlan from "../flightplan";
import { LayerGroup } from "react-leaflet";

interface FlightPlansLayerProps {
  blue?: boolean;
}

// The flight you have selected is the one you are working on, so it is drawn
// whatever the side layers say: turning "All blue flight plans" off is how you get
// the clutter out of the way to see it, and it used to take the selected one with it.
// Drawn here and nowhere else, so it is never drawn twice.
export function SelectedFlightPlanLayer() {
  const flight = useAppSelector(selectSelectedFlight);
  // The group is there whether or not anything is in it: Leaflet keeps its place in
  // the stacking order, so selecting a flight does not put its plan under the others.
  return (
    <LayerGroup>
      {flight ? (
        <FlightPlan key={flight.id} flight={flight} selected={true} highlight />
      ) : null}
    </LayerGroup>
  );
}

export default function FlightPlansLayer(props: FlightPlansLayerProps) {
  const flightData = useAppSelector(selectFlights);
  const isNotSelected = (flight: Flight) => flightData.selected !== flight.id;

  return (
    <LayerGroup>
      {Object.values(flightData.flights)
        .filter(isNotSelected)
        .filter((flight) => props.blue === flight.blue)
        .map((flight) => {
          return <FlightPlan key={flight.id} flight={flight} selected={false} />;
        })}
    </LayerGroup>
  );
}
