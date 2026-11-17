"""To-do list view and editor for the stored profiles."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfilerConfigEntry
from .engine import ProfilerEngine
from .entity import ProfilerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ProfilerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ProfilesTodo(entry.runtime_data)])


class ProfilesTodo(ProfilerEntity, TodoListEntity):
    """Every stored profile is one item: title = key, description = values as JSON."""

    _attr_translation_key = "profiles"
    _attr_icon = "mdi:playlist-star"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, engine: ProfilerEngine) -> None:
        super().__init__(engine, "profiles")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=key,
                summary=key,
                status=TodoItemStatus.NEEDS_ACTION,
                description=json.dumps(self.engine.store.get(key), ensure_ascii=False),
            )
            for key in self.engine.store.keys
        ]

    def _parse(self, description: str | None) -> dict[str, Any]:
        engine = self.engine
        if not description or not description.strip():
            values = engine.current_values()
            if not values:
                raise ServiceValidationError("The current values could not be read")
            return values
        try:
            values = json.loads(description)
        except ValueError as err:
            raise ServiceValidationError(f"The description is not valid JSON: {err}") from err
        if not isinstance(values, dict) or not values:
            raise ServiceValidationError("The description must be a JSON object entity_id -> value")
        unknown = [e for e in values if e not in engine.controls]
        if unknown:
            raise ServiceValidationError(f"Not a controlled entity: {', '.join(unknown)}")
        return values

    async def async_create_todo_item(self, item: TodoItem) -> None:
        key = (item.summary or "").strip()
        if not key:
            raise ServiceValidationError("A profile needs a key as title")
        self.engine.store.set(key, self._parse(item.description))
        self.engine._notify_listeners()  # noqa: SLF001

    async def async_update_todo_item(self, item: TodoItem) -> None:
        store = self.engine.store
        old = item.uid
        new = (item.summary or "").strip() or old
        if old is None or old not in store.keys:
            raise ServiceValidationError("Unknown profile")
        if new != old:
            store.rename(old, new)
        if item.description is not None:
            store.set(new, self._parse(item.description))
        self.engine._notify_listeners()  # noqa: SLF001

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            self.engine.store.delete(uid)
        self.engine._notify_listeners()  # noqa: SLF001
