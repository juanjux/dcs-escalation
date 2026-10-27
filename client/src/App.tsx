import LiberationMap from "./components/liberationmap";
import useEventStream from "./hooks/useEventSteam";
import useInitialGameState from "./hooks/useInitialGameState";
import GroundDestinationMap from "./components/grounddestination/GroundDestinationMap";

function App() {
  const destinationPicker = new URL(
    window.location.toString(),
  ).searchParams.has("groundDestination");
  return destinationPicker ? <DestinationApp /> : <CampaignApp />;
}

function DestinationApp() {
  useInitialGameState();
  return <GroundDestinationMap />;
}

function CampaignApp() {
  useInitialGameState();
  useEventStream();

  return (
    <div className="App">
      <LiberationMap />
    </div>
  );
}

export default App;
