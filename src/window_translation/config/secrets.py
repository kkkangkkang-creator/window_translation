"""API-key storage.

The key is stored in a separate file from regular settings and (on POSIX)
has its file mode tightened to 0o600. For strong protection on Windows you
should wire in DPAPI (``win32crypt.CryptProtectData``) — this MVP keeps
things portable and dependency-free.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from .settings import default_config_dir

SECRET_FILENAME = "api_key"


def _secret_path() -> Path:
    return default_config_dir() / SECRET_FILENAME


def load_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    """Return the API key, preferring the environment variable.

    Order of precedence:
    1. ``env_var`` environment variable
    2. Stored secret file in the user's config directory
    """
    from_env = os.environ.get(env_var)
    if from_env:
        return from_env.strip() or None

    path = _secret_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def save_api_key(key: str) -> None:
    """Persist ``key`` to disk with restrictive permissions."""
    path = _secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(key.strip(), encoding="utf-8")
    # Tighten permissions before the atomic replace so the final file inherits them.
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows / filesystems without POSIX permissions — best-effort only.
        pass
    os.replace(tmp, path)


def clear_api_key() -> None:
    """Remove the stored API key, if any."""
    path = _secret_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _provider_keys() -> dict:
    import json
    path = default_config_dir() / 'api_keys.json'
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}
    # Legacy key belongs only to the saved provider, never a newly selected one.
    from .settings import load_settings
    old = load_api_key()
    return {load_settings().provider: old} if old else {}


def load_provider_key(provider: str) -> Optional[str]:
    value = _provider_keys().get(provider)
    return value if isinstance(value, str) and value else None


def save_provider_keys(changes: dict) -> None:
    import json
    data = _provider_keys()
    data.update({k: v.strip() for k, v in changes.items() if isinstance(v, str)})
    path = default_config_dir() / 'api_keys.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data), encoding='utf-8')
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, path)
