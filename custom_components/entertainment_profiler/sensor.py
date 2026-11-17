"""Sensors: active profile key and stored profiles."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfilerConfigEntry
from .const import CONF_SRC_LABEL, CONF_SRC_PLAYER
from .engine import ProfilerEngine
from .entity import ProfilerEntity

NONE_STATE = "none"


async def async_setup_entry(
    hass: HomeAssistant, entry: ProfilerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine = entry.runtime_data
    async_add_entities([ActiveKeySensor(engine), ProfileCountSensor(engine)])


class ActiveKeySensor(ProfilerEntity, SensorEntity):
    """Which app / series / movie the profiler currently sees."""

    _attr_translation_key = "active_key"
    _attr_icon = "mdi:movie-open-cog"
    _unrecorded_attributes = frozenset({"profile"})

    def __init__(self, engine: ProfilerEngine) -> None:
        super().__init__(engine, "active_key")

    @property
    def native_value(self) -> str:
        return self.engine.key or NONE_STATE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        engine = self.engine
        values, is_default = engine.profile_for(engine.key) if engine.key else (None, False)
        player = engine.source.get(CONF_SRC_PLAYER) if engine.source else None
        player_state = self.hass.states.get(player) if player else None
        return {
            "source": engine.source[CONF_SRC_LABEL] if engine.source else None,
            "title": engine.title,
            "has_profile": values is not None and not is_default,
            "uses_default_profile": values is not None and is_default,
            "profile": values,
            "applying": engine.applying,
            "last_applied": engine.last_applied,
            "last_learned": engine.last_learned,
            "media_player": player,
            "media_content_type": (
                player_state.attributes.get("media_content_type") if player_state else None
            ),
            "media_kind": engine.current_media_kind(engine.source),
        }


class ProfileCountSensor(ProfilerEntity, SensorEntity):
    """Number of stored profiles; the keys are in the attributes."""

    _attr_translation_key = "profile_count"
    _attr_icon = "mdi:playlist-star"
    _attr_state_class = None
    _unrecorded_attributes = frozenset({"keys"})

    def __init__(self, engine: ProfilerEngine) -> None:
        super().__init__(engine, "profile_count")

    @property
    def native_value(self) -> int:
        return len(self.engine.store.keys)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"keys": self.engine.store.keys}
