"""Shared entity base class."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .engine import ProfilerEngine


class ProfilerEntity(Entity):
    """Base for all entities of one profiler."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, engine: ProfilerEngine, key: str) -> None:
        self.engine = engine
        self._attr_unique_id = f"{engine.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, engine.entry.entry_id)},
            name=engine.entry.title,
            manufacturer="dr-apple",
            model="Entertainment Profiler",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.engine.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
