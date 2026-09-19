from __future__ import annotations

import hashlib
import logging
import pickle
import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

import dcs.terrain.falklands.airports

import pydcs_extensions
from game.profiling import logged_duration
from pydcs_extensions import (
    ELM2084_MMR_AD_RT,
    Iron_Dome_David_Sling_CP,
    RBS_70,
    RBS_90,
    CH_BVS10,
    Artillerisystem08_M982,
)

if TYPE_CHECKING:
    from game import Game

_dcs_saved_game_folder: Optional[str] = None
_prefer_liberation_payloads: bool = False
_server_port: int = 16880


# fmt: off
class DummyObject:
    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)


class RemovedEnum:
    """Stands in for an enum a save still names after the feature was dropped.

    A settings enum is pickled by reference, so deleting the class stops every
    campaign that ever stored one from loading at all. The value it resolves to is
    thrown away by Settings.__setstate__ -- there is no field left to hold it -- but
    it has to resolve to something first.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # An enum member unpickles as EnumClass(value); take the value and drop it.
        pass

    def __setstate__(self, state: Any) -> None:
        pass


#: Classes that were pickled into saves and no longer exist. See RemovedEnum.
REMOVED_CLASSES = {
    # Fast forward, removed along with the whole feature.
    "FastForwardStopCondition",
    "CombatResolutionMethod",
}


class MigrationUnpickler(pickle.Unpickler):
    """Custom unpickler to migrate campaign save-files for when components have been moved"""

    def find_class(self, module: Any, name: str) -> Any:
        if module == "game.settings.settings" and name in REMOVED_CLASSES:
            return RemovedEnum

        handlers = [
            self._handle_airport_migrations,
            self._handle_weather_classes,
            self._handle_ch_russian_assets,
            self._handle_ch_usa_assets,
            self._handle_su30,
            self._handle_misc,
        ]

        for handler in handlers:
            result = handler(module, name)
            if result is not None:
                return result

        # Fallback to default behavior with special handling
        return self._handle_default(module, name)

    def _handle_airport_migrations(self, module: str, name: str) -> Any:
        """Handle airport name changes across all terrains"""
        # Kola terrain airports
        if module == "dcs.terrain.kola.airports":
            if name == "Lakselv":
                from dcs.terrain.kola.airports import Banak
                return Banak
            elif name == "Severomorsk1":
                from dcs.terrain.kola.airports import Severomorsk_1
                return Severomorsk_1
            elif name == "Severomorsk3":
                from dcs.terrain.kola.airports import Severomorsk_3
                return Severomorsk_3
            elif name == "Olenegorsk":
                from dcs.terrain.kola.airports import Olenya
                return Olenya
            elif name == "Bas_100":
                from dcs.terrain.kola.airports import Vuojarvi
                return Vuojarvi
            elif name == "Alakourtti":
                from dcs.terrain.kola.airports import Alakurtti
                return Alakurtti
        
        # Sinai terrain airports
        if module == "dcs.terrain.sinai.airports":
            if name == "Borj_El_Arab_International_Airport":
                from dcs.terrain.sinai.airports import Borg_El_Arab_International_Airport
                return Borg_El_Arab_International_Airport
            elif name == "Palmahim":
                from dcs.terrain.sinai.airports import Palmachim
                return Palmachim
        
        # Syria terrain airports
        if module == "dcs.terrain.syria.airports":
            if name == "Amman":
                from dcs.terrain.syria.airports import Marka
                return Marka
            elif name.startswith("Helipad_"):
                return dcs.terrain.Airport  # use base-class if airport was removed
        
        # Afghanistan terrain airports
        if module == "dcs.terrain.afghanistan.airports":
            if name == "Khost_Heliport":
                from dcs.terrain.afghanistan.airports import FOB_Salerno
                return FOB_Salerno
        
        # Falklands terrain airports
        if module == "dcs.terrain.falklands.airports":
            if name == "Aerodromo_De_Tolhuin":
                from dcs.terrain.falklands.airports import Tolhuin
                return Tolhuin
            elif name == "Porvenir_Airfield":
                from dcs.terrain.falklands.airports import Porvenir
                return Porvenir
            elif name == "Aeropuerto_de_Gobernador_Gregores":
                from dcs.terrain.falklands.airports import Gobernador_Gregores
                return Gobernador_Gregores
            elif name == "Aerodromo_O_Higgins":
                from dcs.terrain.falklands.airports import O_Higgins
                return O_Higgins
            elif name == "Hipico":
                from dcs.terrain.falklands.airports import Hipico_Flying_Club
                return Hipico_Flying_Club
        
        # Germany Cold War terrain airports
        if module == "dcs.terrain.germanycoldwar.airports":
            if name == "Leipzig_Halle":
                from dcs.terrain.germanycoldwar.airports import Schkeuditz
                return Schkeuditz
        
        return None

    def _handle_weather_classes(self, module: str, name: str) -> Any:
        """Handle migrations for weather-related classes"""
        if name == "NightMissions":
            from game.settings import NightMissions
            return NightMissions
        if name == "Conditions":
            from game.weather.conditions import Conditions
            return Conditions
        if name == "AtmosphericConditions":
            from game.weather.atmosphericconditions import AtmosphericConditions
            return AtmosphericConditions
        if name == "WindConditions":
            from game.weather.wind import WindConditions
            return WindConditions
        if name == "Clouds":
            from game.weather.clouds import Clouds
            return Clouds
        if name == "Fog":
            from game.weather.fog import Fog
            return Fog
        if name == "ClearSkies":
            from game.weather.weather import ClearSkies
            return ClearSkies
        if name == "Cloudy":
            from game.weather.weather import Cloudy
            return Cloudy
        if name == "Raining":
            from game.weather.weather import Raining
            return Raining
        if name == "Thunderstorm":
            from game.weather.weather import Thunderstorm
            return Thunderstorm
        
        return None

    def _handle_ch_russian_assets(self, module: str, name: str) -> Any:
        """Handle migrations for Russian military assets pack"""
        if module != "pydcs_extensions.russianmilitaryassetspack.russianmilitaryassetspack":
            return None
        
        if name == "Admiral_Gorshkov":
            from pydcs_extensions.russianmilitaryassetspack import CH_Admiral_Gorshkov
            return CH_Admiral_Gorshkov
        if name == "Karakurt_AShM":
            from pydcs_extensions.russianmilitaryassetspack import CH_Karakurt_AShM
            return CH_Karakurt_AShM
        if name == "Karakurt_LACM":
            from pydcs_extensions.russianmilitaryassetspack import CH_Karakurt_LACM
            return CH_Karakurt_LACM
        if name == "K300P":
            from pydcs_extensions.russianmilitaryassetspack import CH_K300P
            return CH_K300P
        if name == "MonolitB":
            from pydcs_extensions.russianmilitaryassetspack import CH_MonolitB
            return CH_MonolitB
        if name == "TorM2K":
            from pydcs_extensions.russianmilitaryassetspack import CH_TorM2K
            return CH_TorM2K
        if name == "PantsirS2":
            from pydcs_extensions.russianmilitaryassetspack import CH_PantsirS2
            return CH_PantsirS2
        if name == "CH_TOS1A":
            from dcs.vehicles import Artillery
            return Artillery.CHAP_TOS1A
        if name == "CH_Mi28N":
            from dcs.helicopters import Mi_28N
            return Mi_28N
        if name == "CH_Tu_95MSM":
            from dcs.planes import Tu_95MS
            return Tu_95MS
        if name == "PantsirS1":
            from dcs.vehicles import AirDefence
            return AirDefence.CHAP_PantsirS1
        if name == "TorM2":
            from dcs.vehicles import AirDefence
            return AirDefence.CHAP_TorM2
        if name == "TorM2M":
            from dcs.vehicles import AirDefence
            return AirDefence.CHAP_TorM2
        if name == "CH_T90A":
            from dcs.vehicles import Armor
            return Armor.CHAP_T90M
        if name == "CH_T90M":
            from dcs.vehicles import Armor
            return Armor.CHAP_T90M
        if name == "CH_IskanderM":
            from dcs.vehicles import MissilesSS
            return MissilesSS.CHAP_9K720_HE
        if name == "CH_Project22160":
            from dcs.ships import CHAP_Project22160
            return CHAP_Project22160
        
        return None
    
    def _handle_ch_usa_assets(self, module: str, name: str) -> Any:
        """Handle migrations for the US military assets pack: the MIM-104 Patriot
        classes were renamed with the pack's CH_ prefix (MIM104_* -> CH_MIM104_*), and
        the mod 2.4.x export refresh renamed/removed units (HIMARS M142 -> M270A1, the
        FMTV/M-ATV trucks, B-21) -> map old saves to the closest current class."""
        if module != "pydcs_extensions.usamilitaryassetspack.usamilitaryassetspack":
            return None
        from pydcs_extensions.usamilitaryassetspack import usamilitaryassetspack

        if name.startswith("MIM104_"):
            return getattr(usamilitaryassetspack, "CH_" + name, None)
        # Mod -> native DCS: ED shipped these as CHAP units, so migrate old saves to the
        # native class (mirrors the CH Russia handler above and the groundunittype
        # display-name migrator). The HIMARS variants ED didn't add (GLSDB / PrSM /
        # PrSM-AShM) fall back to the closest native CHAP HIMARS.
        from dcs.vehicles import Armor, Artillery, Unarmed

        native = {
            "M142_HIMARS_GLSDB": Artillery.CHAP_M142_GMLRS_M31,
            "M142_HIMARS_ATACMS": Artillery.CHAP_M142_ATACMS_M48,
            "M142_HIMARS_GMLRS": Artillery.CHAP_M142_GMLRS_M31,
            "M142_HIMARS_PRSM": Artillery.CHAP_M142_ATACMS_M48,
            "M142_HIMARS_PRSM_ASHM": Artillery.CHAP_M142_ATACMS_M48,
            "CH_FMTV_M1083": Unarmed.CHAP_M1083,
            "CH_OshkoshMATV_M2": Armor.CHAP_MATV,
        }
        if name in native:
            return native[name]
        # The B-21 has no native DCS equivalent -> a rename within the mod.
        if name == "B_21":
            return getattr(usamilitaryassetspack, "CH_B_21", None)
        return None

    def _handle_su30(self, module: str, name: str) -> Any:
        """Handle migrations for Su-30 aircraft variants"""
        if name == "Su_30MKA_AG":
            from pydcs_extensions.su30 import Su_30MKA
            return Su_30MKA
        if name == "Su_30MKI_AG":
            from pydcs_extensions.su30 import Su_30MKI
            return Su_30MKI
        if name == "Su_30SM_AG":
            from pydcs_extensions.su30 import Su_30SM
            return Su_30SM
        if name == "Su_30MKM_AG":
            from pydcs_extensions.su30 import Su_30MKM
            return Su_30MKM

        return None
    
    def _handle_misc(self, module: str, name: str) -> Any:
        """Handle migrations for mods"""
        if module == "pydcs_extensions.f4b.f4b":
            return pydcs_extensions.f4

        if module == "pydcs_extensions.irondome.irondome":
            if name in ["I9K57_URAGAN", "I9K51_GRAD", "I9K58_SMERCH"]:
                return None
            elif name == "ELM2048_MMR":
                return ELM2084_MMR_AD_RT
            elif name == "IRON_DOME_CP":
                return Iron_Dome_David_Sling_CP
        
        if module == "pydcs_extensions.swedishmilitaryassetspack.swedishmilitaryassetspack":
            if name == "BV410_RBS90":
                return RBS_90
            elif name == "BV410":
                return CH_BVS10
            elif name == "Artillerisystem08":
                return Artillerisystem08_M982
            elif name == "BV410_RBS70":
                return RBS_70
        
        if name == "Superbug_AITanker":
            return pydcs_extensions.fa18efg.FA_18ET
        
        if name in ["SaveManager", "SaveGameBundle"]:
            return DummyObject
        if name in ["CaletaTortel", "Caleta_Tortel_Airport"]:
            return dcs.terrain.Airport  # use base-class if airport was removed
        
        return None
    
    def _handle_default(self, module: str, name: str) -> Any:
        """Handle default class resolution with fallback logic"""
        # Special handling for vehicles and ships with case conversion
        if module in ["dcs.vehicles", "dcs.ships"]:
            try:
                return super().find_class(module, name)
            except AttributeError:
                alternate = name.split('.')[:-1] + [name.split('.')[-1][0].lower() + name.split('.')[-1][1:]]
                name = '.'.join(alternate)
        try:
            return super().find_class(module, name)
        except AttributeError:
            if "dcs.terrain" in module and "airports" not in module:
                module = f"{module}.airports"
            else:
                raise
        return super().find_class(module, name)
# fmt: on


def _create_dir_if_needed(path: Path) -> Path:
    if not path.exists():
        path.mkdir(0o755, parents=True)
    return path


def setup(user_folder: str, prefer_liberation_payloads: bool, port: int) -> None:
    global _dcs_saved_game_folder
    global _prefer_liberation_payloads
    global _server_port
    _dcs_saved_game_folder = user_folder
    _prefer_liberation_payloads = prefer_liberation_payloads
    _server_port = port
    _create_dir_if_needed(save_dir())


def base_path() -> Path:
    global _dcs_saved_game_folder
    assert _dcs_saved_game_folder
    return _create_dir_if_needed(Path(_dcs_saved_game_folder))


# These folders keep the name the fork was called when the player's campaigns, his
# factions, his layouts and his kneeboards were written into them. The application is
# DCS Escalation; the shelf his things are already on is still Retribution, and
# renaming it would hide every one of them.


def debug_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Debug")


def factions_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Factions")


def groups_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Groups")


def layouts_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Layouts")


def waypoint_debug_directory() -> Path:
    return _create_dir_if_needed(debug_dir() / "Waypoints")


def settings_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Settings")


def forced_options_path() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution") / "forced_options.lua"


def airwing_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "AirWing")


def data_cartridge_dir() -> Path:
    """Where DCS looks for .dtc files: one flat folder, not per campaign."""
    return _create_dir_if_needed(base_path() / "DTC")


def kneeboards_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Kneeboards")


def tile_cache_dir() -> Path:
    """Directory for cached basemap tiles used by recon kneeboards.

    Prefers ``<save_dir>/Retribution/TileCache`` under the Saved Games tree
    that escalation already writes to. When ``persistency.setup`` has not
    been called (standalone dev scripts, golden-image generators, ad-hoc
    test harnesses), falls back to the OS-conventional user cache location
    so the tile pipeline still works.

    Users may delete this directory at any time to reclaim space or force
    a fresh fetch.
    """
    global _dcs_saved_game_folder
    if _dcs_saved_game_folder:
        return _create_dir_if_needed(base_path() / "Retribution" / "TileCache")
    import os
    import platform

    if platform.system() == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = root / "retribution" / "tilecache"
    return _create_dir_if_needed(path)


def mission_archive_dir() -> Path:
    """Directory holding the archived copy of each generated mission.

    A subfolder of ``Missions`` rather than the Escalation tree, so DCS's own
    mission browser lists it and an archived turn opens straight from the game.
    """
    return _create_dir_if_needed(base_path() / "Missions" / "Retribution Archive")


def payload_backups_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "PayloadBackups")


def payloads_dir(backup: bool = False) -> Path:
    payloads = base_path() / "MissionEditor" / "UnitPayloads"
    if backup:
        return _create_dir_if_needed(payloads / "_retribution_backups")
    return _create_dir_if_needed(payloads)


def prefer_liberation_payloads() -> bool:
    global _prefer_liberation_payloads
    return _prefer_liberation_payloads


def user_custom_weapon_injections_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "WeaponInjections")


def save_dir() -> Path:
    return _create_dir_if_needed(base_path() / "Retribution" / "Saves")


def server_port() -> int:
    global _server_port
    return _server_port


def _temporary_save_file() -> str:
    return str(save_dir() / "tmpsave.retribution")


def _autosave_path() -> str:
    return str(save_dir() / "autosave.retribution")


def mission_path_for(name: str) -> Path:
    return base_path() / "Missions" / name


#: What the campaign looked like when it was last written to its save file. Kept here
#: rather than on the game because it is a fingerprint *of* the game: putting it on the
#: game would change the thing it describes.
_saved_signature: Optional[str] = None


def game_signature(game: Game) -> str:
    """A fingerprint of the campaign as a save file would hold it.

    Pickling a campaign of a few hundred objectives takes about fifty milliseconds and
    gives the same bytes for the same state, so this is an exact answer to "has anything
    changed", and cheap enough to ask when the window closes.
    """
    data = _unload_static_data(game)
    try:
        return hashlib.sha256(pickle.dumps(game)).hexdigest()
    finally:
        _restore_static_data(game, data)


def has_unsaved_changes(game: Optional[Game]) -> bool:
    """Whether closing now would lose something.

    A campaign that has never been saved has everything to lose. Anything that cannot
    be worked out -- no save yet, or a fingerprint that could not be taken -- counts as
    unsaved: being asked once too often costs a keystroke, and the other mistake costs
    the evening's campaign.
    """
    if game is None:
        logging.debug("Unsaved check: no campaign loaded")
        return False
    if _saved_signature is None:
        logging.debug("Unsaved check: no saved fingerprint")
        return True
    try:
        current_signature = game_signature(game)
        logging.debug(
            "Unsaved check: saved=%s current=%s",
            _saved_signature,
            current_signature,
        )
        if current_signature == _saved_signature:
            return False
    except Exception:
        logging.exception("Could not tell whether the campaign has been modified")
        return True
    return True


def load_game(path: str) -> Optional[Game]:
    global _saved_signature
    _saved_signature = None
    with open(path, "rb") as f:
        try:
            save = MigrationUnpickler(f).load()
            save.savepath = path
            return save
        except Exception:
            logging.exception("Invalid Save game")
            return None


def settle(game: Game) -> None:
    """Build what the first look at the campaign builds anyway.

    A flight's plan is laid out on demand -- and a package whose weapons have changed
    range since it was laid out has its waypoints rebuilt, join and IP and split
    re-rolled -- and the first thing to ask for any of that is the map drawing itself,
    moments after the campaign is loaded. Fingerprinting before that compares the
    campaign against a version of itself that stopped existing as soon as it was drawn,
    which is why closing an untouched campaign still asked whether to save it.

    Cheap: about fifty milliseconds over a full ATO, and none of it is work the map was
    not about to do.
    """
    from game.server.flights.models import FlightJs

    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            for flight in package.flights:
                try:
                    FlightJs.for_flight(flight, with_waypoints=True)
                except Exception:
                    logging.exception("Could not settle %s", flight)


def remember_saved_state(game: Game) -> None:
    """This is the campaign as it now sits in its save file."""
    global _saved_signature
    try:
        settle(game)
        _saved_signature = game_signature(game)
        logging.debug(
            "Remembered saved campaign: game=%s path=%s fingerprint=%s",
            id(game),
            getattr(game, "savepath", None),
            _saved_signature,
        )
    except Exception:
        logging.exception("Could not fingerprint the saved campaign")
        _saved_signature = None


def save_game(game: Game) -> bool:
    with logged_duration("Saving game"):
        try:
            with open(_temporary_save_file(), "wb") as f:
                data = _unload_static_data(game)
                pickle.dump(game, f)
                _restore_static_data(game, data)
            shutil.copy(_temporary_save_file(), game.savepath)
            remember_saved_state(game)
            return True
        except Exception:
            logging.exception("Could not save game")
            return False


def _restore_static_data(game: Game, data: dict[str, Any]) -> None:
    game.theater.landmap = data["landmap"]


def _unload_static_data(game: Game) -> dict[str, Any]:
    landmap = game.theater.landmap
    game.theater.landmap = None
    return {
        "landmap": landmap,
    }


def autosave(game: Game) -> bool:
    """
    Autosave to the autosave location
    :param game: Game to save
    :return: True if saved successfully
    """
    try:
        with open(_autosave_path(), "wb") as f:
            data = _unload_static_data(game)
            pickle.dump(game, f)
            _restore_static_data(game, data)
        return True
    except Exception:
        logging.exception("Could not save game")
        return False
