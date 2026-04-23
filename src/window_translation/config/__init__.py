"""Configuration and API key management.

Settings are persisted to a JSON file in the user's config directory so that
they survive restarts without relying on Qt's QSettings (which makes the
module usable from non-GUI contexts such as unit tests).

The API key is stored separately under restrictive file permissions
(0o600 on POSIX; on Windows the user's AppData directory is already
per-user). This is not strong encryption — for production use, wire the key
through Windows DPAPI or a keyring — but it is a safe MVP default.
"""

from .settings import AppSettings, default_config_dir, load_settings, save_settings
from .secrets import load_api_key, save_api_key

__all__ = [
    "AppSettings",
    "default_config_dir",
    "load_settings",
    "save_settings",
    "load_api_key",
    "save_api_key",
]
