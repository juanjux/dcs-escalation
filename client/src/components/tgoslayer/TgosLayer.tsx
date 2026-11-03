import {
  selectShowDestroyedNonRepairable,
  selectShowDestroyedRepairable,
} from "../../api/mapSlice";
import { selectTgos } from "../../api/tgosSlice";
import { useAppSelector } from "../../app/hooks";
import Tgo from "../tgos/Tgo";
import { LayerGroup } from "react-leaflet";

interface TgosLayerProps {
  categories?: string[];
  exclude?: true;
  task?: string;
}

export default function TgosLayer(props: TgosLayerProps) {
  const allTgos = Object.values(useAppSelector(selectTgos).tgos);
  const showDestroyed = useAppSelector(selectShowDestroyedNonRepairable);
  const showDestroyedRepairable = useAppSelector(selectShowDestroyedRepairable);
  const categoryFilter = props.categories ?? [];
  const taskFilter = props.task ?? "";
  const tgos = allTgos.filter((tgo) => {
    // The API's purchasable field reports repairability, including rebuildable
    // buildings. Only completely destroyed sites use these visibility filters.
    if (tgo.dead) {
      const visibility = tgo.purchasable ? showDestroyedRepairable : showDestroyed;
      const shown = tgo.blue ? visibility.blue : visibility.red;
      if (!shown) {
        return false;
      }
    }
    if (taskFilter && tgo.task) {
      return taskFilter === tgo.task[0];
    }
    return categoryFilter.includes(tgo.category) === !(props.exclude ?? false);
  });
  return (
    <LayerGroup>
      {tgos.map((tgo) => {
        return <Tgo key={tgo.name} tgo={tgo} />;
      })}
    </LayerGroup>
  );
}
