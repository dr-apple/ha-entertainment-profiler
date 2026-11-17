"""Config and options flow."""

from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_APPLY_DELAY,
    CONF_CONTROLS,
    CONF_IDLE_LABEL,
    CONF_KEY_DEBOUNCE,
    CONF_KEY_STABLE,
    CONF_LEARN_STABLE,
    CONF_NAME,
    CONF_NOTIFY_APPLY,
    CONF_NOTIFY_ENTITY,
    CONF_NOTIFY_LEARN,
    CONF_RECEIVER,
    CONF_SETTLE_TIMEOUT,
    CONF_SOURCES,
    CONF_SRC_ID,
    CONF_SRC_LABEL,
    CONF_SRC_LEARN,
    CONF_SRC_PLAYER,
    CONF_SRC_RECEIVER_SOURCE,
    CONF_SRC_REQUIRE_PLAYING,
    CONF_SRC_TITLE_ATTRIBUTE,
    CONF_SRC_TITLE_MODE,
    CONF_VOLUME_MAX,
    CONF_VOLUME_MIN,
    CONTROL_DOMAINS,
    DEFAULT_APPLY_DELAY,
    DEFAULT_IDLE_LABEL,
    DEFAULT_KEY_DEBOUNCE,
    DEFAULT_KEY_STABLE,
    DEFAULT_LEARN_STABLE,
    DEFAULT_SETTLE_TIMEOUT,
    DEFAULT_VOLUME_MAX,
    DEFAULT_VOLUME_MIN,
    DOMAIN,
    TITLE_AUTO,
    TITLE_MODES,
)

DEFAULT_NAME = "Entertainment Profiler"


def _controls_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=CONTROL_DOMAINS, multiple=True)
    )


def _seconds(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _percent() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
        )
    )


class EntertainmentProfilerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: name, receiver and the entities a profile controls."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EntertainmentProfilerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            await self.async_set_unique_id(name.casefold())
            self._abort_if_unique_id_configured()
            if not user_input.get(CONF_CONTROLS):
                errors[CONF_CONTROLS] = "no_controls"
            else:
                data = {
                    CONF_NAME: name,
                    CONF_CONTROLS: user_input[CONF_CONTROLS],
                }
                if user_input.get(CONF_RECEIVER):
                    data[CONF_RECEIVER] = user_input[CONF_RECEIVER]
                return self.async_create_entry(title=name, data=data)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=(user_input or {}).get(CONF_NAME, DEFAULT_NAME)
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_RECEIVER,
                    description={"suggested_value": (user_input or {}).get(CONF_RECEIVER)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
                vol.Required(
                    CONF_CONTROLS, default=(user_input or {}).get(CONF_CONTROLS, [])
                ): _controls_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class EntertainmentProfilerOptionsFlow(OptionsFlow):
    """Manage sources, controlled entities and the timing / notification settings."""

    def __init__(self) -> None:
        self._source_id: str | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def _sources(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self.config_entry.options.get(CONF_SOURCES, [])]

    def _save(self, **changes: Any) -> ConfigFlowResult:
        options = {**self.config_entry.options, **changes}
        return self.async_create_entry(title="", data=options)

    def _receiver_sources(self) -> list[str]:
        receiver = self.config_entry.data.get(CONF_RECEIVER)
        state = self.hass.states.get(receiver) if receiver else None
        return list(state.attributes.get("source_list") or []) if state else []

    # --------------------------------------------------------------------- menu
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["sources_menu", "settings", "controls"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_sources_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_source"]
        if self._sources:
            menu += ["edit_source", "remove_source"]
        menu.append("init")
        return self.async_show_menu(step_id="sources_menu", menu_options=menu)

    # ----------------------------------------------------------------- controls
    async def async_step_controls(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options.get(
            CONF_CONTROLS, self.config_entry.data.get(CONF_CONTROLS, [])
        )
        if user_input is not None:
            if not user_input.get(CONF_CONTROLS):
                errors[CONF_CONTROLS] = "no_controls"
            else:
                return self._save(**user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONTROLS, default=(user_input or {}).get(CONF_CONTROLS, current)
                ): _controls_selector()
            }
        )
        return self.async_show_form(step_id="controls", data_schema=schema, errors=errors)

    # ----------------------------------------------------------------- settings
    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if CONF_NOTIFY_ENTITY not in user_input:
                user_input[CONF_NOTIFY_ENTITY] = None
            return self._save(**user_input)
        o = self.config_entry.options

        def d(name: str, default: Any) -> Any:
            return o.get(name, default)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VOLUME_MIN, default=d(CONF_VOLUME_MIN, DEFAULT_VOLUME_MIN)
                ): _percent(),
                vol.Required(
                    CONF_VOLUME_MAX, default=d(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX)
                ): _percent(),
                vol.Required(
                    CONF_KEY_DEBOUNCE, default=d(CONF_KEY_DEBOUNCE, DEFAULT_KEY_DEBOUNCE)
                ): _seconds(0, 30),
                vol.Required(
                    CONF_APPLY_DELAY, default=d(CONF_APPLY_DELAY, DEFAULT_APPLY_DELAY)
                ): _seconds(0, 120),
                vol.Required(
                    CONF_LEARN_STABLE, default=d(CONF_LEARN_STABLE, DEFAULT_LEARN_STABLE)
                ): _seconds(5, 600),
                vol.Required(
                    CONF_KEY_STABLE, default=d(CONF_KEY_STABLE, DEFAULT_KEY_STABLE)
                ): _seconds(0, 600),
                vol.Required(
                    CONF_SETTLE_TIMEOUT, default=d(CONF_SETTLE_TIMEOUT, DEFAULT_SETTLE_TIMEOUT)
                ): _seconds(1, 120),
                vol.Optional(
                    CONF_IDLE_LABEL, default=d(CONF_IDLE_LABEL, DEFAULT_IDLE_LABEL)
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_NOTIFY_ENTITY,
                    description={"suggested_value": o.get(CONF_NOTIFY_ENTITY)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="notify")),
                vol.Required(CONF_NOTIFY_APPLY, default=d(CONF_NOTIFY_APPLY, False)): bool,
                vol.Required(CONF_NOTIFY_LEARN, default=d(CONF_NOTIFY_LEARN, False)): bool,
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    # ------------------------------------------------------------------ sources
    def _source_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        receiver_sources = self._receiver_sources()
        return vol.Schema(
            {
                vol.Required(
                    CONF_SRC_LABEL, default=defaults.get(CONF_SRC_LABEL, "")
                ): selector.TextSelector(),
                vol.Required(
                    CONF_SRC_PLAYER, default=defaults.get(CONF_SRC_PLAYER, vol.UNDEFINED)
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
                vol.Optional(
                    CONF_SRC_RECEIVER_SOURCE,
                    description={"suggested_value": defaults.get(CONF_SRC_RECEIVER_SOURCE)},
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=receiver_sources,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SRC_TITLE_MODE, default=defaults.get(CONF_SRC_TITLE_MODE, TITLE_AUTO)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=TITLE_MODES,
                        translation_key="title_mode",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SRC_TITLE_ATTRIBUTE,
                    description={"suggested_value": defaults.get(CONF_SRC_TITLE_ATTRIBUTE)},
                ): selector.TextSelector(),
                vol.Required(
                    CONF_SRC_REQUIRE_PLAYING, default=defaults.get(CONF_SRC_REQUIRE_PLAYING, True)
                ): bool,
                vol.Required(CONF_SRC_LEARN, default=defaults.get(CONF_SRC_LEARN, True)): bool,
            }
        )

    @staticmethod
    def _clean_source(user_input: dict[str, Any]) -> dict[str, Any]:
        source = dict(user_input)
        source[CONF_SRC_LABEL] = source[CONF_SRC_LABEL].strip()
        for opt in (CONF_SRC_RECEIVER_SOURCE, CONF_SRC_TITLE_ATTRIBUTE):
            if not (source.get(opt) or "").strip():
                source.pop(opt, None)
            else:
                source[opt] = source[opt].strip()
        return source

    def _source_errors(self, source: dict[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not source[CONF_SRC_LABEL]:
            errors[CONF_SRC_LABEL] = "label_required"
        elif "|" in source[CONF_SRC_LABEL]:
            errors[CONF_SRC_LABEL] = "label_pipe"
        return errors

    async def async_step_add_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            source = self._clean_source(user_input)
            errors = self._source_errors(source)
            if not errors:
                source[CONF_SRC_ID] = uuid.uuid4().hex[:8]
                return self._save(**{CONF_SOURCES: [*self._sources, source]})
        return self.async_show_form(
            step_id="add_source",
            data_schema=self._source_schema(user_input or {}),
            errors=errors,
        )

    def _source_picker(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_SRC_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=s[CONF_SRC_ID],
                                label=f"{i + 1}. {s[CONF_SRC_LABEL]} ({s[CONF_SRC_PLAYER]})",
                            )
                            for i, s in enumerate(self._sources)
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

    async def async_step_edit_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._source_id = user_input[CONF_SRC_ID]
            return await self.async_step_edit_source_form()
        return self.async_show_form(step_id="edit_source", data_schema=self._source_picker())

    async def async_step_edit_source_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        sources = self._sources
        current = next((s for s in sources if s[CONF_SRC_ID] == self._source_id), None)
        if current is None:
            return await self.async_step_sources_menu()
        errors: dict[str, str] = {}
        if user_input is not None:
            updated = self._clean_source(user_input)
            errors = self._source_errors(updated)
            if not errors:
                updated[CONF_SRC_ID] = self._source_id
                sources = [updated if s[CONF_SRC_ID] == self._source_id else s for s in sources]
                return self._save(**{CONF_SOURCES: sources})
        return self.async_show_form(
            step_id="edit_source_form",
            data_schema=self._source_schema(user_input or current),
            errors=errors,
        )

    async def async_step_remove_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            sources = [s for s in self._sources if s[CONF_SRC_ID] != user_input[CONF_SRC_ID]]
            return self._save(**{CONF_SOURCES: sources})
        return self.async_show_form(step_id="remove_source", data_schema=self._source_picker())
