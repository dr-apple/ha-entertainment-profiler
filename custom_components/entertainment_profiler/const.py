"""Constants for Entertainment Profiler."""

from __future__ import annotations

DOMAIN = "entertainment_profiler"

PLATFORMS = ["sensor", "switch", "button", "todo"]

# --- config entry data -------------------------------------------------------
CONF_NAME = "name"
CONF_RECEIVER = "receiver"
CONF_CONTROLS = "controls"

# --- options -----------------------------------------------------------------
CONF_SOURCES = "sources"
CONF_VOLUME_MIN = "volume_min"
CONF_VOLUME_MAX = "volume_max"
CONF_KEY_DEBOUNCE = "key_debounce"
CONF_APPLY_DELAY = "apply_delay"
CONF_LEARN_STABLE = "learn_stable"
CONF_KEY_STABLE = "key_stable"
CONF_SETTLE_TIMEOUT = "settle_timeout"
CONF_IDLE_LABEL = "idle_label"
CONF_NOTIFY_ENTITY = "notify_entity"
CONF_NOTIFY_APPLY = "notify_apply"
CONF_NOTIFY_LEARN = "notify_learn"

# --- source definition -------------------------------------------------------
CONF_SRC_ID = "id"
CONF_SRC_LABEL = "label"
CONF_SRC_PLAYER = "player"
CONF_SRC_RECEIVER_SOURCE = "receiver_source"
CONF_SRC_TITLE_MODE = "title_mode"
CONF_SRC_TITLE_ATTRIBUTE = "title_attribute"
CONF_SRC_REQUIRE_PLAYING = "require_playing"
CONF_SRC_LEARN = "learn"

TITLE_NONE = "none"
TITLE_AUTO = "auto"
TITLE_SERIES = "series"
TITLE_TITLE = "title"
TITLE_CUSTOM = "custom"
TITLE_MODES = [TITLE_NONE, TITLE_AUTO, TITLE_SERIES, TITLE_TITLE, TITLE_CUSTOM]

# --- defaults ----------------------------------------------------------------
DEFAULT_VOLUME_MIN = 0
DEFAULT_VOLUME_MAX = 100
DEFAULT_KEY_DEBOUNCE = 1
DEFAULT_APPLY_DELAY = 0
DEFAULT_LEARN_STABLE = 30
DEFAULT_KEY_STABLE = 40
DEFAULT_SETTLE_TIMEOUT = 20
DEFAULT_IDLE_LABEL = ""

# A stored profile with this key is used when the current key has no profile.
DEFAULT_PROFILE_KEY = "Standard"

KEY_SEPARATOR = "|"

# Entity domains that can be part of a profile.
CONTROL_DOMAINS = [
    "media_player",
    "number",
    "input_number",
    "switch",
    "input_boolean",
    "select",
    "input_select",
    "light",
]

PLAYING_STATES = ("playing", "paused", "buffering")

STORAGE_VERSION = 1

SERVICE_SAVE_PROFILE = "save_profile"
SERVICE_APPLY_PROFILE = "apply_profile"
SERVICE_DELETE_PROFILE = "delete_profile"
SERVICE_LIST_PROFILES = "list_profiles"
SERVICE_IMPORT_PROFILES = "import_profiles"

ATTR_ENTRY_ID = "entry_id"
ATTR_KEY = "key"
ATTR_VALUES = "values"
ATTR_PROFILES = "profiles"
ATTR_REPLACE = "replace"
