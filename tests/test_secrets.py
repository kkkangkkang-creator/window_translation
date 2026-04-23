"""Tests for the API-key store."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from window_translation.config import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets_mod, "default_config_dir", lambda: tmp_path)


def test_save_and_load_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secrets_mod.save_api_key("sk-secret-123")
    assert secrets_mod.load_api_key() == "sk-secret-123"


def test_env_var_overrides_file(monkeypatch: pytest.MonkeyPatch) -> None:
    secrets_mod.save_api_key("sk-file")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert secrets_mod.load_api_key() == "sk-env"


def test_load_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert secrets_mod.load_api_key() is None


def test_clear_api_key_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secrets_mod.clear_api_key()  # no file yet — should not raise
    secrets_mod.save_api_key("sk-x")
    secrets_mod.clear_api_key()
    assert secrets_mod.load_api_key() is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics only")
def test_saved_file_has_tight_permissions(tmp_path: Path) -> None:
    secrets_mod.save_api_key("sk-perm")
    path = tmp_path / "api_key"
    mode = stat.S_IMODE(path.stat().st_mode)
    # Group/other bits must all be zero.
    assert mode & 0o077 == 0
