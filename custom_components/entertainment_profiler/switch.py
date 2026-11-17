"""Switches: automatic apply and learning."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ProfilerConfigEntry
from .engine import ProfilerEngine
from .entity import ProfilerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ProfilerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine = entry.runtime_data
    async_add_entities(
        [
            ProfilerSwitch(engine, "auto_apply", "mdi:auto-fix"),
            ProfilerSwitch(engine, "learning", "mdi:school"),
        ]
    )


class ProfilerSwitch(ProfilerEntity, SwitchEntity, RestoreEntity):
    """Switch backed by a boolean attribute of the engine."""

    def __init__(self, engine: ProfilerEngine, attribute: str, icon: str) -> None:
        super().__init__(engine, attribute)
        self._attribute = attribute
        self._attr_translation_key = attribute
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            setattr(self.engine, self._attribute, last.state != "off")

    @property
    def is_on(self) -> bool:
        return getattr(self.engine, self._attribute)

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.engine, self._attribute, True)
        self.engine._notify_listeners()  # noqa: SLF001

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.engine, self._attribute, False)
        self.engine._notify_listeners()  # noqa: SLF001
