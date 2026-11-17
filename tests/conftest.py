"""Fixtures for the Entertainment Profiler tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entertainment_profiler.const import (
    CONF_CONTROLS,
    CONF_KEY_DEBOUNCE,
    CONF_KEY_STABLE,
    CONF_LEARN_STABLE,
    CONF_NAME,
    CONF_RECEIVER,
    CONF_SOURCES,
    CONF_VOLUME_MAX,
    CONF_VOLUME_MIN,
    DOMAIN,
)

RECEIVER = "media_player.receiver"
PLEX = "media_player.plex"
STREAM = "media_player.stream"
SUB_LEVEL = "number.sub_level"
SUB_SWITCH = "switch.sub"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


def make_entry(**options) -> MockConfigEntry:
    base = {
        CONF_KEY_DEBOUNCE: 0,
        CONF_LEARN_STABLE: 30,
        CONF_KEY_STABLE: 40,
        CONF_VOLUME_MIN: 30,
        CONF_VOLUME_MAX: 70,
        CONF_SOURCES: [
            {
                "id": "a",
                "label": "SmartTube",
                "player": STREAM,
                "receiver_source": "TV Audio",
                "title_mode": "none",
                "require_playing": False,
                "learn": False,
            },
            {
                "id": "b",
                "label": "Plex",
                "player": PLEX,
                "title_mode": "auto",
                "require_playing": True,
                "learn": True,
            },
        ],
    }
    base.update(options)
    return MockConfigEntry(
        domain=DOMAIN,
        title="Wohnzimmer",
        unique_id="wohnzimmer",
        data={
            CONF_NAME: "Wohnzimmer",
            CONF_RECEIVER: RECEIVER,
            CONF_CONTROLS: [RECEIVER, SUB_LEVEL, SUB_SWITCH],
        },
        options=base,
    )


def set_receiver(hass, *, state="on", source="TV Audio", volume=0.5, mode="Stereo"):
    hass.states.async_set(
        RECEIVER,
        state,
        {
            "source": source,
            "volume_level": volume,
            "sound_mode": mode,
            "sound_mode_list": ["Stereo", "Movie", "Music"],
        },
    )
