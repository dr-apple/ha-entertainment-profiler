"""Core logic: detect what is playing, apply and learn profiles."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_APPLY_DELAY,
    CONF_CONTROLS,
    CONF_IDLE_LABEL,
    CONF_KEY_DEBOUNCE,
    CONF_KEY_STABLE,
    CONF_LEARN_STABLE,
    CONF_NOTIFY_APPLY,
    CONF_NOTIFY_ENTITY,
    CONF_NOTIFY_LEARN,
    CONF_RECEIVER,
    CONF_SETTLE_TIMEOUT,
    CONF_SOURCES,
    CONF_SRC_LABEL,
    CONF_SRC_LEARN,
    CONF_SRC_PLAYER,
    CONF_SRC_RECEIVER_SOURCE,
    CONF_SRC_REQUIRE_PLAYING,
    CONF_SRC_TITLE_ATTRIBUTE,
    CONF_SRC_TITLE_MODE,
    CONF_VOLUME_MAX,
    CONF_VOLUME_MIN,
    DEFAULT_APPLY_DELAY,
    DEFAULT_IDLE_LABEL,
    DEFAULT_KEY_DEBOUNCE,
    DEFAULT_KEY_STABLE,
    DEFAULT_LEARN_STABLE,
    DEFAULT_PROFILE_KEY,
    DEFAULT_SETTLE_TIMEOUT,
    DEFAULT_VOLUME_MAX,
    DEFAULT_VOLUME_MIN,
    KEY_SEPARATOR,
    PLAYING_STATES,
    TITLE_AUTO,
    TITLE_CUSTOM,
    TITLE_NONE,
    TITLE_SERIES,
    TITLE_TITLE,
)
from .profiles import ProfileStore, describe, profiles_equal, read_value, snapshot

_LOGGER = logging.getLogger(__name__)

VOLUME_TOLERANCE = 1.0
RAMP_STABLE_SECONDS = 3
RAMP_MAX_SECONDS = 90


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_title(state: State | None, mode: str, attribute: str | None) -> str | None:
    """Pick the title (series / movie name) out of a media player state."""
    if state is None or mode == TITLE_NONE:
        return None
    attrs = state.attributes
    if mode == TITLE_SERIES:
        return _text(attrs.get("media_series_title"))
    if mode == TITLE_TITLE:
        return _text(attrs.get("media_title"))
    if mode == TITLE_CUSTOM:
        return _text(attrs.get(attribute)) if attribute else None
    if mode == TITLE_AUTO:
        return _text(attrs.get("media_series_title")) or _text(attrs.get("media_title"))
    return None


class ProfilerEngine:
    """One engine per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: ProfileStore) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store

        self.auto_apply = True
        self.learning = True

        self.key: str | None = None
        self.source: dict[str, Any] | None = None
        self.title: str | None = None
        self.key_since: datetime = dt_util.utcnow()
        self.applying = False
        self.last_applied: str | None = None
        self.last_learned: str | None = None

        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._debounce_cancel: CALLBACK_TYPE | None = None
        self._learn_cancel: CALLBACK_TYPE | None = None
        self._apply_cancel: CALLBACK_TYPE | None = None
        self._apply_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ config
    @property
    def _opts(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _opt(self, name: str, default: Any) -> Any:
        value = self._opts.get(name)
        return default if value is None else value

    @property
    def receiver(self) -> str | None:
        return self._opts.get(CONF_RECEIVER) or None

    @property
    def controls(self) -> list[str]:
        return list(self._opts.get(CONF_CONTROLS, []))

    @property
    def sources(self) -> list[dict[str, Any]]:
        return list(self._opts.get(CONF_SOURCES, []))

    @property
    def idle_label(self) -> str:
        return str(self._opt(CONF_IDLE_LABEL, DEFAULT_IDLE_LABEL)).strip()

    # --------------------------------------------------------------- lifecycle
    async def async_start(self) -> None:
        watched = set(self.controls)
        if self.receiver:
            watched.add(self.receiver)
        watched.update(s[CONF_SRC_PLAYER] for s in self.sources if s.get(CONF_SRC_PLAYER))
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, list(watched), self._on_state)
            )
        # Initial key: no apply after a restart, only remember what is active.
        self.key, self.source, self.title = self.compute_key()
        self.key_since = dt_util.utcnow()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for attr in ("_debounce_cancel", "_learn_cancel", "_apply_cancel"):
            cancel = getattr(self, attr)
            if cancel:
                cancel()
                setattr(self, attr, None)
        if self._apply_task and not self._apply_task.done():
            self._apply_task.cancel()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    # --------------------------------------------------------------- detection
    def compute_key(self) -> tuple[str | None, dict[str, Any] | None, str | None]:
        """Work out the profile key from the current states.

        Returns ``(key, source_definition, title)``.
        """
        receiver_source: str | None = None
        if self.receiver:
            receiver_state = self.hass.states.get(self.receiver)
            if receiver_state is None or receiver_state.state in (
                "off",
                "unavailable",
                "unknown",
                "standby",
            ):
                return None, None, None
            receiver_source = _text(receiver_state.attributes.get("source"))

        for src in self.sources:
            wanted = _text(src.get(CONF_SRC_RECEIVER_SOURCE))
            if wanted and (
                receiver_source is None or receiver_source.casefold() != wanted.casefold()
            ):
                continue
            player_state = self.hass.states.get(src.get(CONF_SRC_PLAYER, ""))
            require_playing = src.get(CONF_SRC_REQUIRE_PLAYING, True)
            if require_playing and (
                player_state is None or player_state.state not in PLAYING_STATES
            ):
                continue
            label = str(src[CONF_SRC_LABEL])
            title = resolve_title(
                player_state,
                src.get(CONF_SRC_TITLE_MODE, TITLE_NONE),
                src.get(CONF_SRC_TITLE_ATTRIBUTE),
            )
            key = f"{label}{KEY_SEPARATOR}{title}" if title else label
            return key, src, title

        if self.idle_label:
            return self.idle_label, None, None
        return None, None, None

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]

        if (
            entity_id in self.controls
            and new_state is not None
            and old_state is not None
            and read_value(new_state) != read_value(old_state)
        ):
            self._schedule_learn()

        # Any change of receiver / player may change the key.
        self._schedule_key_check()

    @callback
    def _schedule_key_check(self) -> None:
        debounce = float(self._opt(CONF_KEY_DEBOUNCE, DEFAULT_KEY_DEBOUNCE))
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None
        if debounce <= 0:
            self._check_key()
            return
        self._debounce_cancel = async_call_later(self.hass, debounce, self._debounced_check)

    @callback
    def _debounced_check(self, _now: datetime) -> None:
        self._debounce_cancel = None
        self._check_key()

    @callback
    def _check_key(self) -> None:
        key, source, title = self.compute_key()
        if key == self.key:
            # Title attributes may update without changing the key.
            if source is not self.source or title != self.title:
                self.source, self.title = source, title
                self._notify_listeners()
            return
        _LOGGER.debug("Profile key changed: %s -> %s", self.key, key)
        self.key, self.source, self.title = key, source, title
        self.key_since = dt_util.utcnow()
        # A pending learn belongs to the old key.
        if self._learn_cancel:
            self._learn_cancel()
            self._learn_cancel = None
        self._notify_listeners()
        if key is not None and self.auto_apply:
            self._schedule_apply(key)

    # ------------------------------------------------------------------- apply
    @callback
    def _schedule_apply(self, key: str) -> None:
        if self._apply_cancel:
            self._apply_cancel()
            self._apply_cancel = None
        delay = float(self._opt(CONF_APPLY_DELAY, DEFAULT_APPLY_DELAY))
        if delay <= 0:
            self._start_apply(key)
            return

        @callback
        def _go(_now: datetime) -> None:
            self._apply_cancel = None
            self._start_apply(key)

        self._apply_cancel = async_call_later(self.hass, delay, _go)

    @callback
    def _start_apply(self, key: str) -> None:
        # A new switch restarts a running apply (like automation mode "restart").
        if self._apply_task and not self._apply_task.done():
            self._apply_task.cancel()
        self._apply_task = self.entry.async_create_background_task(
            self.hass, self.async_apply(key), f"{self.entry.title} apply {key}"
        )

    def profile_for(self, key: str) -> tuple[dict[str, Any] | None, bool]:
        """Return ``(values, is_default)`` for a key."""
        values = self.store.get(key)
        if values is not None:
            return values, False
        return self.store.get(DEFAULT_PROFILE_KEY), True

    async def async_apply(self, key: str | None = None) -> bool:
        """Apply the profile for ``key`` (default: the current key)."""
        key = key or self.key
        if key is None:
            return False
        values, is_default = self.profile_for(key)
        if values is None:
            _LOGGER.debug("No profile (and no %r profile) for %s", DEFAULT_PROFILE_KEY, key)
            return False
        self.applying = True
        self._notify_listeners()
        try:
            await self._apply_values(values)
        finally:
            self.applying = False
            self._notify_listeners()
        self.last_applied = key
        self._notify_listeners()
        await self._notify(
            CONF_NOTIFY_APPLY,
            "applied_default" if is_default else "applied",
            key,
            values,
        )
        return True

    def _clamp_volume(self, volume: float) -> float:
        low = float(self._opt(CONF_VOLUME_MIN, DEFAULT_VOLUME_MIN))
        high = float(self._opt(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX))
        return max(low, min(high, volume))

    async def _apply_values(self, values: dict[str, Any]) -> None:
        volume_targets: list[tuple[str, float]] = []
        controls = set(self.controls)
        for entity_id, value in values.items():
            if entity_id not in controls:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                continue
            domain = entity_id.split(".")[0]
            try:
                if domain == "media_player":
                    target = await self._apply_media_player(entity_id, state, value)
                    if target is not None:
                        volume_targets.append((entity_id, target))
                elif domain in ("number", "input_number"):
                    await self._apply_number(entity_id, state, value)
                elif domain in ("switch", "input_boolean"):
                    await self._apply_switch(entity_id, state, value)
                elif domain in ("select", "input_select"):
                    await self._apply_select(entity_id, state, value)
                elif domain == "light":
                    await self._apply_light(entity_id, value)
            except Exception:  # noqa: BLE001 - one broken entity must not stop the rest
                _LOGGER.warning("Could not apply %s for %s", value, entity_id, exc_info=True)

        for entity_id, target in volume_targets:
            await self._ensure_volume(entity_id, target)

    async def _call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        await self.hass.services.async_call(domain, service, data, blocking=True)

    async def _apply_media_player(
        self, entity_id: str, state: State, value: dict[str, Any]
    ) -> float | None:
        mode = value.get("sound_mode")
        if mode and mode != state.attributes.get("sound_mode"):
            if mode in (state.attributes.get("sound_mode_list") or []):
                await self._call(
                    "media_player",
                    "select_sound_mode",
                    {"entity_id": entity_id, "sound_mode": mode},
                )
            else:
                _LOGGER.warning("%s does not offer sound mode %r", entity_id, mode)
        if "volume" not in value:
            return None
        target = self._clamp_volume(float(value["volume"]))
        await self._call(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": round(target / 100, 4)},
        )
        return target

    async def _apply_number(self, entity_id: str, state: State, value: Any) -> None:
        number = float(value)
        low = state.attributes.get("min")
        high = state.attributes.get("max")
        if low is not None:
            number = max(float(low), number)
        if high is not None:
            number = min(float(high), number)
        domain = entity_id.split(".")[0]
        await self._call(domain, "set_value", {"entity_id": entity_id, "value": number})

    async def _apply_switch(self, entity_id: str, state: State, value: Any) -> None:
        domain = entity_id.split(".")[0]
        want_on = bool(value)
        if (state.state == "on") == want_on:
            return
        await self._call(domain, "turn_on" if want_on else "turn_off", {"entity_id": entity_id})

    async def _apply_select(self, entity_id: str, state: State, value: Any) -> None:
        options = state.attributes.get("options") or []
        if value not in options or state.state == value:
            return
        domain = entity_id.split(".")[0]
        await self._call(domain, "select_option", {"entity_id": entity_id, "option": value})

    async def _apply_light(self, entity_id: str, value: dict[str, Any]) -> None:
        if not value.get("on", True):
            await self._call("light", "turn_off", {"entity_id": entity_id})
            return
        data: dict[str, Any] = {"entity_id": entity_id}
        if "brightness" in value:
            data["brightness_pct"] = int(value["brightness"])
        await self._call("light", "turn_on", data)

    # Receivers often ramp the volume themselves or ignore a command while they
    # are switching inputs, so verify the result and correct it if needed.
    def _volume_ok(self, entity_id: str, target: float) -> bool:
        state = self.hass.states.get(entity_id)
        if state is None:
            return True
        level = state.attributes.get("volume_level")
        if level is None:
            return True
        return abs(float(level) * 100 - target) <= VOLUME_TOLERANCE

    async def _ensure_volume(self, entity_id: str, target: float) -> None:
        settle = float(self._opt(CONF_SETTLE_TIMEOUT, DEFAULT_SETTLE_TIMEOUT))
        if await self._wait_for(entity_id, lambda: self._volume_ok(entity_id, target), settle):
            return
        _LOGGER.debug("%s did not reach volume %s, resending", entity_id, target)
        await self._call(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": round(target / 100, 4)},
        )
        await self._wait_stable(entity_id, RAMP_STABLE_SECONDS, RAMP_MAX_SECONDS)
        if not self._volume_ok(entity_id, target):
            await self._call(
                "media_player",
                "volume_set",
                {"entity_id": entity_id, "volume_level": round(target / 100, 4)},
            )

    async def _wait_for(
        self, entity_id: str, predicate: Callable[[], bool], timeout: float
    ) -> bool:
        if predicate():
            return True
        done: asyncio.Future[None] = self.hass.loop.create_future()

        @callback
        def _changed(_event: Event[EventStateChangedData]) -> None:
            if not done.done() and predicate():
                done.set_result(None)

        unsub = async_track_state_change_event(self.hass, [entity_id], _changed)
        try:
            async with asyncio.timeout(timeout):
                await done
            return True
        except TimeoutError:
            return predicate()
        finally:
            unsub()

    async def _wait_stable(self, entity_id: str, stable: float, maximum: float) -> None:
        """Wait until the entity has not changed for ``stable`` seconds."""
        loop = self.hass.loop
        deadline = loop.time() + maximum
        while loop.time() < deadline:
            changed: asyncio.Future[None] = loop.create_future()

            @callback
            def _changed(_event: Event[EventStateChangedData], fut=changed) -> None:
                if not fut.done():
                    fut.set_result(None)

            unsub = async_track_state_change_event(self.hass, [entity_id], _changed)
            try:
                async with asyncio.timeout(stable):
                    await changed
            except TimeoutError:
                return
            finally:
                unsub()

    # ------------------------------------------------------------------- learn
    @callback
    def _schedule_learn(self) -> None:
        if self._learn_cancel:
            self._learn_cancel()
            self._learn_cancel = None
        stable = float(self._opt(CONF_LEARN_STABLE, DEFAULT_LEARN_STABLE))
        self._learn_cancel = async_call_later(self.hass, stable, self._learn_due)

    @callback
    def _learn_due(self, _now: datetime) -> None:
        self._learn_cancel = None
        self.hass.async_create_task(self.async_learn(), eager_start=True)

    def can_learn(self) -> bool:
        if not self.learning or self.applying or self.key is None:
            return False
        if self.source is None:  # idle label
            return False
        if not self.source.get(CONF_SRC_LEARN, True):
            return False
        key_stable = float(self._opt(CONF_KEY_STABLE, DEFAULT_KEY_STABLE))
        # Skip automatic changes that happen right after a new title started.
        return (dt_util.utcnow() - self.key_since).total_seconds() >= key_stable

    async def async_learn(self, *, force: bool = False, key: str | None = None) -> bool:
        """Store the current values as profile for the key.

        Without ``force`` this only happens when learning is allowed and the
        values actually differ from the stored profile.
        """
        key = key or self.key
        if key is None:
            return False
        if not force and not self.can_learn():
            return False
        previous = self.store.get(key)
        current = snapshot(self.hass, self.controls, previous)
        if not current:
            return False
        if previous is not None and profiles_equal(previous, current):
            return False
        self.store.set(key, current, learned=not force)
        self.last_learned = key
        self._notify_listeners()
        await self._notify(
            CONF_NOTIFY_LEARN, "updated" if previous is not None else "created", key, current
        )
        return True

    # ------------------------------------------------------------------ notify
    async def _notify(self, option: str, kind: str, key: str, values: dict[str, Any]) -> None:
        target = self._opts.get(CONF_NOTIFY_ENTITY)
        if not target or not self._opts.get(option, False):
            return
        german = (self.hass.config.language or "en").startswith("de")
        shown = key.replace(KEY_SEPARATOR, " - ")
        text = describe(self.hass, values)
        titles = {
            "applied": ("Profil", f"Profil {shown}: {text}")
            if german
            else ("Profile", f"Profile {shown}: {text}"),
            "applied_default": ("Profil", f"Standardprofil für {shown}: {text}")
            if german
            else ("Profile", f"Default profile for {shown}: {text}"),
            "created": ("Profil", f"Neues Profil gespeichert für {shown}: {text}")
            if german
            else ("Profile", f"New profile saved for {shown}: {text}"),
            "updated": ("Profil", f"Profil aktualisiert für {shown}: {text}")
            if german
            else ("Profile", f"Profile updated for {shown}: {text}"),
        }
        title, message = titles[kind]
        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"title": title, "message": message},
                target={"entity_id": target},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not send notification to %s", target, exc_info=True)

    # ----------------------------------------------------------------- helpers
    def current_values(self) -> dict[str, Any]:
        return snapshot(self.hass, self.controls)
