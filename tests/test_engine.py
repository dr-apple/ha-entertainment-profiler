"""Tests for key detection, applying and learning."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.entertainment_profiler.const import DOMAIN

from .conftest import (
    PLEX,
    RECEIVER,
    STREAM,
    SUB_LEVEL,
    SUB_SWITCH,
    make_entry,
    set_receiver,
)

KEY_SENSOR = "sensor.wohnzimmer_active_profile"


async def _setup(hass: HomeAssistant, **options):
    hass.states.async_set(STREAM, "idle")
    hass.states.async_set(PLEX, "idle", {})
    hass.states.async_set(SUB_LEVEL, "0", {"min": -12, "max": 12})
    hass.states.async_set(SUB_SWITCH, "off")
    set_receiver(hass, source="Apple TV")
    entry = make_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_key_detection(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    assert engine.key is None

    # Receiver input decides, the player may be idle.
    set_receiver(hass, source="TV Audio")
    await hass.async_block_till_done()
    assert engine.key == "SmartTube"
    assert hass.states.get(KEY_SENSOR).state == "SmartTube"

    # Series title is appended.
    set_receiver(hass, source="Apple TV")
    hass.states.async_set(
        PLEX, "playing", {"media_series_title": "The Expanse", "media_title": "Ep 1"}
    )
    await hass.async_block_till_done()
    assert engine.key == "Plex|The Expanse"

    # A movie has no series title, the media title is used.
    hass.states.async_set(PLEX, "playing", {"media_title": "Dune"})
    await hass.async_block_till_done()
    assert engine.key == "Plex|Dune"

    # Receiver off: nothing is active.
    set_receiver(hass, state="off")
    await hass.async_block_till_done()
    assert engine.key is None
    assert hass.states.get(KEY_SENSOR).state == "none"


async def test_idle_label(hass: HomeAssistant) -> None:
    entry = await _setup(hass, idle_label="Leerlauf")
    await hass.async_block_till_done()
    set_receiver(hass, source="Apple TV", volume=0.51)
    await hass.async_block_till_done()
    assert entry.runtime_data.key == "Leerlauf"


async def test_apply_on_key_change(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    engine.store.set(
        "SmartTube",
        {
            RECEIVER: {"volume": 90, "sound_mode": "Movie"},
            SUB_LEVEL: -6,
            SUB_SWITCH: True,
        },
    )
    volume = async_mock_service(hass, "media_player", "volume_set")
    mode = async_mock_service(hass, "media_player", "select_sound_mode")
    number = async_mock_service(hass, "number", "set_value")
    switch = async_mock_service(hass, "switch", "turn_on")

    async def _reach_volume(call):
        hass.states.async_set(
            RECEIVER,
            "on",
            {**hass.states.get(RECEIVER).attributes, "volume_level": call.data["volume_level"]},
        )

    hass.services.async_register("media_player", "volume_set", _reach_volume)
    volume.clear()

    set_receiver(hass, source="TV Audio")
    await hass.async_block_till_done()

    assert mode[0].data["sound_mode"] == "Movie"
    assert number[0].data["value"] == -6
    assert switch[0].data["entity_id"] == SUB_SWITCH
    # volume limited to the configured maximum (70 %)
    assert hass.states.get(RECEIVER).attributes["volume_level"] == 0.7
    assert engine.last_applied == "SmartTube"


async def test_default_profile_used(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    engine.store.set("Standard", {SUB_LEVEL: 3})
    number = async_mock_service(hass, "number", "set_value")
    set_receiver(hass, source="TV Audio")
    await hass.async_block_till_done()
    assert number[0].data["value"] == 3


async def test_learning(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    hass.states.async_set(PLEX, "playing", {"media_series_title": "Severance"})
    set_receiver(hass, source="Apple TV", volume=0.5)
    await hass.async_block_till_done()
    assert engine.key == "Plex|Severance"

    # Key must be stable for 40 s before values are learned.
    future = dt_util.utcnow() + timedelta(seconds=45)
    engine.key_since = dt_util.utcnow() - timedelta(seconds=60)
    hass.states.async_set(SUB_LEVEL, "-4", {"min": -12, "max": 12})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()

    values = engine.store.get("Plex|Severance")
    assert values is not None
    assert values[SUB_LEVEL] == -4
    assert values[RECEIVER]["volume"] == 50.0


async def test_no_learning_right_after_key_change(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    hass.states.async_set(PLEX, "playing", {"media_series_title": "Severance"})
    await hass.async_block_till_done()
    hass.states.async_set(SUB_LEVEL, "5", {"min": -12, "max": 12})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=35))
    await hass.async_block_till_done()
    assert engine.store.get("Plex|Severance") is None


async def test_fixed_source_not_learned(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data
    set_receiver(hass, source="TV Audio")
    await hass.async_block_till_done()
    engine.key_since = dt_util.utcnow() - timedelta(seconds=120)
    hass.states.async_set(SUB_LEVEL, "2", {"min": -12, "max": 12})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=35))
    await hass.async_block_till_done()
    assert engine.store.get("SmartTube") is None


async def test_services_and_todo(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data

    result = await hass.services.async_call(
        DOMAIN,
        "import_profiles",
        {"profiles": {"Netflix": {SUB_LEVEL: 1}, "Plex|Foo": {SUB_SWITCH: True}}},
        blocking=True,
        return_response=True,
    )
    assert result == {"imported": 2}
    listed = await hass.services.async_call(
        DOMAIN, "list_profiles", {}, blocking=True, return_response=True
    )
    assert set(listed["profiles"]) == {"Netflix", "Plex|Foo"}
    assert hass.states.get("sensor.wohnzimmer_stored_profiles").state == "2"

    await hass.services.async_call(
        "todo",
        "add_item",
        {
            "entity_id": "todo.wohnzimmer_profiles",
            "item": "Disney+",
            "description": '{"number.sub_level": 2}',
        },
        blocking=True,
    )
    assert engine.store.get("Disney+") == {SUB_LEVEL: 2}

    await hass.services.async_call(DOMAIN, "delete_profile", {"key": "Netflix"}, blocking=True)
    assert engine.store.get("Netflix") is None
