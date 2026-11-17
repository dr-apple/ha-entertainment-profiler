"""Buttons: apply the profile now / save the current values."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfilerConfigEntry
from .engine import ProfilerEngine
from .entity import ProfilerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ProfilerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine = entry.runtime_data
    async_add_entities([ApplyButton(engine), SaveButton(engine)])


class ApplyButton(ProfilerEntity, ButtonEntity):
    _attr_translation_key = "apply_now"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, engine: ProfilerEngine) -> None:
        super().__init__(engine, "apply_now")

    async def async_press(self) -> None:
        if not await self.engine.async_apply():
            raise ServiceValidationError("There is no profile for what is playing right now")


class SaveButton(ProfilerEntity, ButtonEntity):
    _attr_translation_key = "save_current"
    _attr_icon = "mdi:content-save-cog-outline"

    def __init__(self, engine: ProfilerEngine) -> None:
        super().__init__(engine, "save_current")

    async def async_press(self) -> None:
        if self.engine.key is None:
            raise ServiceValidationError("Nothing is playing right now")
        await self.engine.async_learn(force=True)
