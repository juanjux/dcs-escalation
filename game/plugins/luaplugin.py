from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Any

from game.settings import Settings

if TYPE_CHECKING:
    from game.missiongenerator.luagenerator import LuaGenerator


class LuaPluginWorkOrder:
    def __init__(
        self, parent_mnemonic: str, filename: str, mnemonic: str, disable: bool
    ) -> None:
        self.parent_mnemonic = parent_mnemonic
        self.filename = filename
        self.mnemonic = mnemonic
        self.disable = disable

    def work(self, lua_generator: LuaGenerator) -> None:
        if self.disable:
            lua_generator.bypass_plugin_script(self.mnemonic)
        else:
            lua_generator.inject_plugin_script(
                self.parent_mnemonic, self.filename, self.mnemonic
            )


class PluginSettings:
    def __init__(self, identifier: str, value: Any) -> None:
        self.identifier = identifier
        self.value = value
        self.settings = Settings()
        self.initialize_settings()

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.initialize_settings()

    def initialize_settings(self) -> None:
        # Plugin options are saved in the game's Settings, but it's possible for
        # plugins to change across loads. If new plugins are added or new
        # options added to those plugins, initialize the new settings.
        self.settings.initialize_plugin_option(self.identifier, self.value)

    @property
    def get_value(self) -> Any:
        return self.settings.plugin_option(self.identifier)

    def set_value(self, value: Any) -> None:
        self.settings.set_plugin_option(self.identifier, value)


class LuaPluginOption(PluginSettings):
    def __init__(
        self,
        identifier: str,
        name: str,
        min: Any,
        max: Any,
        value: Any,
        description: str = "",
        choices: Optional[List[tuple[str, Any]]] = None,
        display_unit: str = "",
    ) -> None:
        super().__init__(identifier, value)
        self.name = name
        self.description = description
        self.choices = choices or []
        # Presentation only: saved settings and Lua values stay in metres.
        if display_unit not in ("", "ft"):
            raise ValueError(f"Unsupported plugin display unit: {display_unit}")
        self.display_unit = display_unit
        if type(value) == int or type(value) == float:
            self.min, self.max = min, max
        else:
            self.min, self.max = None, None


@dataclass(frozen=True)
class LuaPluginDefinition:
    identifier: str
    name: str
    description: str
    present_in_ui: bool
    enabled_by_default: bool
    #: When set, this plugin has no switch of its own: it is on whenever any of
    #: these is. For the plumbing another plugin needs, which is a detail of that
    #: plugin rather than a choice anyone should have to make.
    enabled_with_any_of: List[str]
    options: List[LuaPluginOption]
    work_orders: List[LuaPluginWorkOrder]
    config_work_orders: List[LuaPluginWorkOrder]
    other_resource_files: List[str]

    @classmethod
    def from_json(cls, name: str, path: Path) -> LuaPluginDefinition:
        data = json.loads(path.read_text())

        options = []
        for option in data.get("specificOptions"):
            option_id = option["mnemonic"]
            options.append(
                LuaPluginOption(
                    identifier=f"{name}.{option_id}",
                    name=option.get("nameInUI", name),
                    min=option.get("minimumValue", 0),
                    max=option.get("maximumValue", 10000),
                    value=option.get("defaultValue"),
                    description=option.get("descriptionInUI", ""),
                    choices=[
                        (choice["label"], choice["value"])
                        for choice in option.get("choices", [])
                    ],
                    display_unit=option.get("displayUnit", ""),
                )
            )

        work_orders = []
        for work_order in data.get("scriptsWorkOrders"):
            work_orders.append(
                LuaPluginWorkOrder(
                    name,
                    work_order.get("file"),
                    work_order["mnemonic"],
                    work_order.get("disable", False),
                )
            )
        config_work_orders = []
        for work_order in data.get("configurationWorkOrders"):
            config_work_orders.append(
                LuaPluginWorkOrder(
                    name,
                    work_order.get("file"),
                    work_order["mnemonic"],
                    work_order.get("disable", False),
                )
            )

        return cls(
            identifier=name,
            name=data["nameInUI"],
            description=data.get("descriptionInUI", ""),
            present_in_ui=not data.get("skipUI", False),
            enabled_by_default=data.get("defaultValue", False),
            enabled_with_any_of=data.get("enabledWithAnyOf", []),
            options=options,
            work_orders=work_orders,
            config_work_orders=config_work_orders,
            other_resource_files=data.get("otherResourceFiles", []),
        )


def _manager() -> Any:
    # Imported here: the manager imports this module to build its plugins.
    from game.plugins.manager import LuaPluginManager

    return LuaPluginManager


class LuaPlugin(PluginSettings):
    def __init__(self, definition: LuaPluginDefinition) -> None:
        self.definition = definition
        super().__init__(self.definition.identifier, self.definition.enabled_by_default)

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def show_in_ui(self) -> bool:
        return self.definition.present_in_ui

    @property
    def options(self) -> List[LuaPluginOption]:
        return self.definition.options

    @property
    def enabled(self) -> bool:
        if self.definition.enabled_with_any_of:
            return any(
                plugin.enabled
                for plugin in _manager().plugins()
                if plugin.identifier in self.definition.enabled_with_any_of
            )
        return type(self.get_value) == bool and self.get_value

    @classmethod
    def from_json(cls, name: str, path: Path) -> Optional[LuaPlugin]:
        try:
            definition = LuaPluginDefinition.from_json(name, path)
        except KeyError:
            logging.exception("Required plugin configuration value missing")
            return None

        return cls(definition)

    def set_settings(self, settings: Settings) -> None:
        super().set_settings(settings)
        for option in self.definition.options:
            option.set_settings(self.settings)

    def inject_scripts(self, lua_generator: LuaGenerator) -> None:
        for work_order in self.definition.work_orders:
            work_order.work(lua_generator)

    @staticmethod
    def _lua_literal(value: Any) -> str:
        """Render a plugin option as Lua source.

        Booleans and numbers go out bare; anything else is a string and has to be
        quoted with its case intact. The previous blanket ``str(value).lower()``
        broke both ways at once: an unquoted ``3M24`` in the naval magazines' weapon
        patterns is a malformed Lua number, which killed the whole configuration
        block and left that plugin unloaded -- and the lowercasing would have stopped
        those patterns matching DCS's upper-case weapon type names even once quoted.
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def inject_configuration(self, lua_generator: LuaGenerator) -> None:
        # inject the plugin options
        if self.options:
            option_decls = []
            for option in self.options:
                name = option.identifier
                option_decls.append(
                    f"    dcsRetribution.plugins.{name} = "
                    f"{self._lua_literal(option.get_value)}"
                )

            joined_options = "\n".join(option_decls)

            lua = textwrap.dedent(f"""\
                -- {self.identifier} plugin configuration.

                if dcsRetribution then
                    if not dcsRetribution.plugins then
                        dcsRetribution.plugins = {{}}
                    end
                    dcsRetribution.plugins.{self.identifier} = {{}}
                    {joined_options}
                end

            """)

            lua_generator.inject_lua_trigger(
                lua, f"{self.identifier} plugin configuration"
            )

        for work_order in self.definition.config_work_orders:
            work_order.work(lua_generator)

    def inject_other_resource_files(self, lua_generator: LuaGenerator) -> None:
        for resource_file in self.definition.other_resource_files:
            # TODO: should probably deconflict names of resources
            lua_generator.inject_other_plugin_resources(
                self.definition.identifier, resource_file
            )
