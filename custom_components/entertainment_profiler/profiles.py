"""Profile storage and value helpers.

A *profile* is a plain dict ``{entity_id: value}`` where the value depends on
the entity domain:

========================  =====================================================
media_player              ``{"volume": 0-100, "sound_mode": "Movie"}``
number / input_number     ``-6.0``
switch / input_boolean    ``true`` / ``false``
select / input_select     ``"Option"``
light                     ``{"on": true, "brightness": 0-100}``
========================  =====================================================
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

_INVALID = ("unavailable", "unknown", "none", "")

FLOAT_TOLERANCE = 0.5


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_value(state: State | None) -> Any | None:
    """Return the profile value for the current state of an entity.

    ``None`` means "cannot be read right now" and is skipped when learning.
    """
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    domain = state.domain
    attrs = state.attributes
    if domain == "media_player":
        value: dict[str, Any] = {}
        volume = _float(attrs.get("volume_level"))
        if volume is not None:
            value["volume"] = round(volume * 100, 1)
        sound_mode = attrs.get("sound_mode")
        if sound_mode:
            value["sound_mode"] = str(sound_mode)
        return value or None
    if domain in ("number", "input_number"):
        number = _float(state.state)
        return None if number is None else round(number, 2)
    if domain in ("switch", "input_boolean"):
        return state.state == "on"
    if domain in ("select", "input_select"):
        return None if state.state in _INVALID else state.state
    if domain == "light":
        value = {"on": state.state == "on"}
        brightness = _float(attrs.get("brightness"))
        if state.state == "on" and brightness is not None:
            value["brightness"] = round(brightness / 255 * 100)
        return value
    return None


def values_equal(a: Any, b: Any) -> bool:
    """Compare two profile values with a small tolerance for numbers."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(values_equal(a[k], b[k]) for k in a)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    fa, fb = _float(a), _float(b)
    if fa is not None and fb is not None and not isinstance(a, str):
        return abs(fa - fb) <= FLOAT_TOLERANCE
    return a == b


def profiles_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Compare two whole profiles."""
    return set(a) == set(b) and all(values_equal(a[k], b[k]) for k in a)


def snapshot(
    hass: HomeAssistant, controls: list[str], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Read the current values of all controlled entities.

    Entities that cannot be read right now keep their previously stored value.
    """
    result: dict[str, Any] = {}
    for entity_id in controls:
        value = read_value(hass.states.get(entity_id))
        if value is None and previous and entity_id in previous:
            value = previous[entity_id]
        if value is not None:
            result[entity_id] = value
    return result


def describe(hass: HomeAssistant, values: dict[str, Any]) -> str:
    """Short human readable one-line description of a profile."""
    parts: list[str] = []
    for entity_id, value in values.items():
        state = hass.states.get(entity_id)
        name = state.name if state else entity_id
        if isinstance(value, dict):
            bits = []
            if "volume" in value:
                bits.append(f"{value['volume']:g}")
            if "sound_mode" in value:
                bits.append(str(value["sound_mode"]))
            if "on" in value:
                bits.append("on" if value["on"] else "off")
            if "brightness" in value:
                bits.append(f"{value['brightness']}%")
            text = ", ".join(bits)
        elif isinstance(value, bool):
            text = "on" if value else "off"
        else:
            text = f"{value:g}" if isinstance(value, (int, float)) else str(value)
        parts.append(f"{name}: {text}")
    return "; ".join(parts)


class ProfileStore:
    """Persistent key -> profile mapping."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.profiles"
        )
        self._profiles: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._profiles = (data or {}).get("profiles", {})

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"profiles": self._profiles}, 1)

    @property
    def keys(self) -> list[str]:
        return sorted(self._profiles, key=str.casefold)

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._profiles.get(key)
        return None if entry is None else dict(entry["values"])

    def meta(self, key: str) -> dict[str, Any]:
        entry = self._profiles.get(key) or {}
        return {k: v for k, v in entry.items() if k != "values"}

    def set(self, key: str, values: dict[str, Any], *, learned: bool = False) -> None:
        self._profiles[key] = {
            "values": values,
            "learned": learned,
            "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._save()

    def delete(self, key: str) -> bool:
        if key not in self._profiles:
            return False
        del self._profiles[key]
        self._save()
        return True

    def rename(self, old: str, new: str) -> None:
        if old in self._profiles and old != new:
            self._profiles[new] = self._profiles.pop(old)
            self._save()

    def all_values(self) -> dict[str, dict[str, Any]]:
        return {key: dict(entry["values"]) for key, entry in self._profiles.items()}

    def clear(self) -> None:
        self._profiles = {}
        self._save()

    async def async_remove(self) -> None:
        await self._store.async_remove()
