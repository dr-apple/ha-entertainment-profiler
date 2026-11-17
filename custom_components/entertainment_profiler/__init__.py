"""Entertainment Profiler: remembers volume, sound and more per app / series / movie."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ENTRY_ID,
    ATTR_KEY,
    ATTR_PROFILES,
    ATTR_REPLACE,
    ATTR_VALUES,
    DOMAIN,
    PLATFORMS,
    SERVICE_APPLY_PROFILE,
    SERVICE_DELETE_PROFILE,
    SERVICE_IMPORT_PROFILES,
    SERVICE_LIST_PROFILES,
    SERVICE_SAVE_PROFILE,
)
from .engine import ProfilerEngine
from .profiles import ProfileStore

_LOGGER = logging.getLogger(__name__)

type ProfilerConfigEntry = ConfigEntry[ProfilerEngine]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_ENTRY = {vol.Optional(ATTR_ENTRY_ID): cv.string}
SAVE_SCHEMA = vol.Schema(
    {**_ENTRY, vol.Optional(ATTR_KEY): cv.string, vol.Optional(ATTR_VALUES): dict}
)
APPLY_SCHEMA = vol.Schema({**_ENTRY, vol.Optional(ATTR_KEY): cv.string})
DELETE_SCHEMA = vol.Schema({**_ENTRY, vol.Required(ATTR_KEY): cv.string})
LIST_SCHEMA = vol.Schema({**_ENTRY})
IMPORT_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Required(ATTR_PROFILES): dict,
        vol.Optional(ATTR_REPLACE, default=False): cv.boolean,
    }
)


def _engine(hass: HomeAssistant, call: ServiceCall) -> ProfilerEngine:
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if hasattr(e, "runtime_data")]
    wanted = call.data.get(ATTR_ENTRY_ID)
    if wanted:
        for entry in entries:
            if entry.entry_id == wanted or entry.title == wanted:
                return entry.runtime_data
        raise ServiceValidationError(f"Unknown entry {wanted}")
    if len(entries) == 1:
        return entries[0].runtime_data
    if not entries:
        raise ServiceValidationError("Entertainment Profiler is not set up")
    raise ServiceValidationError("Several profilers are set up, pass entry_id")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the integration-wide services."""

    async def save_profile(call: ServiceCall) -> None:
        engine = _engine(hass, call)
        key = call.data.get(ATTR_KEY) or engine.key
        if not key:
            raise ServiceValidationError("No key given and nothing is playing right now")
        values = call.data.get(ATTR_VALUES)
        if values is None:
            await engine.async_learn(force=True, key=key)
            if engine.store.get(key) is None:
                raise HomeAssistantError("Current values could not be read")
            return
        engine.store.set(key, _validate_values(engine, values))
        engine._notify_listeners()  # noqa: SLF001

    async def apply_profile(call: ServiceCall) -> None:
        engine = _engine(hass, call)
        if not await engine.async_apply(call.data.get(ATTR_KEY)):
            raise ServiceValidationError("There is no profile to apply")

    async def delete_profile(call: ServiceCall) -> None:
        engine = _engine(hass, call)
        if not engine.store.delete(call.data[ATTR_KEY]):
            raise ServiceValidationError(f"No profile {call.data[ATTR_KEY]!r}")
        engine._notify_listeners()  # noqa: SLF001

    async def list_profiles(call: ServiceCall) -> ServiceResponse:
        engine = _engine(hass, call)
        return {ATTR_PROFILES: engine.store.all_values(), "current_key": engine.key}

    async def import_profiles(call: ServiceCall) -> ServiceResponse:
        engine = _engine(hass, call)
        if call.data[ATTR_REPLACE]:
            engine.store.clear()
        count = 0
        for key, values in call.data[ATTR_PROFILES].items():
            engine.store.set(str(key), _validate_values(engine, values))
            count += 1
        engine._notify_listeners()  # noqa: SLF001
        return {"imported": count}

    hass.services.async_register(DOMAIN, SERVICE_SAVE_PROFILE, save_profile, SAVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPLY_PROFILE, apply_profile, APPLY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_PROFILE, delete_profile, DELETE_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_PROFILES,
        list_profiles,
        LIST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_PROFILES,
        import_profiles,
        IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


def _validate_values(engine: ProfilerEngine, values: Any) -> dict[str, Any]:
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError as err:
            raise ServiceValidationError(f"Profile is not valid JSON: {err}") from err
    if not isinstance(values, dict) or not values:
        raise ServiceValidationError("A profile must be a non-empty mapping entity_id -> value")
    unknown = [e for e in values if e not in engine.controls]
    if unknown:
        raise ServiceValidationError(
            f"Not a controlled entity of this profiler: {', '.join(unknown)}"
        )
    return values


async def async_setup_entry(hass: HomeAssistant, entry: ProfilerConfigEntry) -> bool:
    store = ProfileStore(hass, entry.entry_id)
    await store.async_load()
    engine = ProfilerEngine(hass, entry, store)
    entry.runtime_data = engine
    await engine.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(engine.async_stop)
    return True


async def _async_reload(hass: HomeAssistant, entry: ProfilerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ProfilerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ProfilerConfigEntry) -> None:
    await ProfileStore(hass, entry.entry_id).async_remove()
