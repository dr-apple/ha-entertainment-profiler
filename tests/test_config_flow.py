"""Config / options flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.entertainment_profiler.const import DOMAIN

from .conftest import PLEX, RECEIVER, SUB_LEVEL, make_entry


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Kino", "receiver": RECEIVER, "controls": [RECEIVER, SUB_LEVEL]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["controls"] == [RECEIVER, SUB_LEVEL]


async def test_options_add_source(hass: HomeAssistant) -> None:
    hass.states.async_set(RECEIVER, "on", {"source_list": ["TV Audio", "Apple TV"]})
    hass.states.async_set(PLEX, "idle")
    entry = make_entry(sources=[])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources_menu"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_source"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "label": "Plex",
            "player": PLEX,
            "receiver_source": "Apple TV",
            "title_mode": "auto",
            "require_playing": True,
            "learn": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sources = entry.options["sources"]
    assert [s["label"] for s in sources] == ["Plex"]
    assert sources[0]["receiver_source"] == "Apple TV"


async def test_options_add_source_with_apps(hass: HomeAssistant) -> None:
    hass.states.async_set(RECEIVER, "on", {"source_list": ["Apple TV"]})
    hass.states.async_set(PLEX, "playing", {"app_name": "Rivulet", "source_list": ["Disney+"]})
    entry = make_entry(sources=[])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources_menu"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_source"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "label": "Plex",
            "player": PLEX,
            "apps": [" Rivulet ", ""],
            "title_mode": "custom",
            "title_attribute": "media_artist",
            "require_playing": True,
            "learn": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["sources"][0]["apps"] == ["Rivulet"]
