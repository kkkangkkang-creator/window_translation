"""Tests for the translation history store + export + cache decorator."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Optional

import pytest

from window_translation.history import (
    HistoryStore,
    export_csv,
    export_json,
    hash_source,
)
from window_translation.translate.base import Translator, TranslationError
from window_translation.translate.cache import CachingTranslator


# -------------------------------------------------------- fakes
class _RecordingTranslator(Translator):
    def __init__(self, reply: str = "번역결과") -> None:
        self.calls: List[dict] = []
        self.reply = reply
        self._few_shot_examples: List = []

    def translate(
        self,
        text: str,
        target_language: str = "Korean",
        source_language: Optional[str] = None,
    ) -> str:
        self.calls.append(
            {
                "text": text,
                "target_language": target_language,
                "source_language": source_language,
                "examples": list(self._few_shot_examples),
            }
        )
        return self.reply

    def set_few_shot_examples(self, examples) -> None:
        self._few_shot_examples = list(examples or [])


class _RaisingTranslator(Translator):
    def translate(self, text, target_language="Korean", source_language=None):
        raise TranslationError("boom")


# -------------------------------------------------------- hash
def test_hash_source_is_whitespace_normalised() -> None:
    assert hash_source("hello world") == hash_source("  hello   world ")
    assert hash_source("hello world") == hash_source("hello\nworld")
    assert hash_source("hello") != hash_source("hell0")


# -------------------------------------------------------- store
def test_history_store_add_and_lookup(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    entry = store.add(
        "Hello",
        "안녕하세요",
        target_language="Korean",
        model="gpt-4o-mini",
        provider="openai",
    )
    assert entry.id > 0
    hit = store.lookup("Hello", "Korean", model="gpt-4o-mini")
    assert hit is not None
    assert hit.translated_text == "안녕하세요"


def test_history_store_lookup_misses_on_different_model(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("Hello", "A", target_language="Korean", model="m1")
    assert store.lookup("Hello", "Korean", model="m1") is not None
    assert store.lookup("Hello", "Korean", model="m2") is None


def test_history_store_lookup_model_agnostic_when_empty(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("Hi", "안녕", target_language="Korean", model="m1")
    hit = store.lookup("Hi", "Korean", model="")
    assert hit is not None and hit.translated_text == "안녕"


def test_history_recent_order_newest_first(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("a", "A", target_language="Korean")
    store.add("b", "B", target_language="Korean")
    store.add("c", "C", target_language="Korean")
    recent = store.recent(limit=2, target_language="Korean")
    assert [e.source_text for e in recent] == ["c", "b"]


def test_history_recent_filter_by_target_language(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("a", "A", target_language="Korean")
    store.add("b", "B", target_language="English")
    ko = store.recent(limit=10, target_language="Korean")
    assert [e.source_text for e in ko] == ["a"]


def test_history_delete_all(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("a", "A", target_language="Korean")
    store.add("b", "B", target_language="Korean")
    assert store.count() == 2
    assert store.delete_all() == 2
    assert store.count() == 0


def test_history_rejects_empty(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    with pytest.raises(ValueError):
        store.add("", "result", target_language="Korean")
    with pytest.raises(ValueError):
        store.add("source", "   ", target_language="Korean")


# -------------------------------------------------------- export
def test_export_json_roundtrip(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("한국어", "Korean text", target_language="English", model="m1")
    out = tmp_path / "hist.json"
    n = export_json(store.all(), out)
    assert n == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["source_text"] == "한국어"
    assert data[0]["translated_text"] == "Korean text"
    assert data[0]["model"] == "m1"


def test_export_csv_roundtrip(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("a", "A", target_language="Korean")
    store.add("b", "B", target_language="Korean")
    out = tmp_path / "hist.csv"
    n = export_csv(store.all(), out)
    assert n == 2
    # utf-8-sig with BOM is readable via 'utf-8-sig'.
    with out.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert {r["source_text"] for r in rows} == {"a", "b"}


# -------------------------------------------------------- CachingTranslator
def test_caching_translator_cache_hit_avoids_call(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("Hello", "안녕하세요", target_language="Korean", model="gpt-4o-mini")
    inner = _RecordingTranslator(reply="SHOULD_NOT_BE_USED")
    t = CachingTranslator(inner, store, model="gpt-4o-mini", provider="openai")
    out = t.translate("Hello", target_language="Korean")
    assert out == "안녕하세요"
    assert inner.calls == []  # no upstream call


def test_caching_translator_cache_miss_calls_and_stores(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    inner = _RecordingTranslator(reply="안녕")
    t = CachingTranslator(inner, store, model="m", provider="openai")
    out = t.translate("Hi", target_language="Korean", source_language="en")
    assert out == "안녕"
    assert len(inner.calls) == 1
    # Round-trip: second call hits the cache.
    out2 = t.translate("Hi", target_language="Korean")
    assert out2 == "안녕"
    assert len(inner.calls) == 1  # still 1


def test_caching_translator_skips_empty(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    inner = _RecordingTranslator(reply="x")
    t = CachingTranslator(inner, store)
    assert t.translate("") == ""
    assert t.translate("   ") == ""
    assert inner.calls == []


def test_caching_translator_disabled_bypasses_cache(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("Hello", "OLD", target_language="Korean", model="m")
    inner = _RecordingTranslator(reply="NEW")
    t = CachingTranslator(inner, store, model="m", enabled=False)
    out = t.translate("Hello", target_language="Korean")
    assert out == "NEW"
    # And nothing new written (enabled=False disables writes too).
    assert store.count() == 1


def test_caching_translator_injects_few_shot_examples(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("prev src 1", "prev tgt 1", target_language="Korean", model="m")
    store.add("prev src 2", "prev tgt 2", target_language="Korean", model="m")
    inner = _RecordingTranslator(reply="새로운")
    t = CachingTranslator(
        inner, store, model="m", recent_context=2, provider="openai"
    )
    out = t.translate("new source", target_language="Korean")
    assert out == "새로운"
    examples = inner.calls[0]["examples"]
    # Chronological (oldest → newest).
    assert examples == [
        ("prev src 1", "prev tgt 1"),
        ("prev src 2", "prev tgt 2"),
    ]
    # Examples should be cleared after the call.
    assert inner._few_shot_examples == []


def test_caching_translator_recent_context_filters_by_target_language(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("ja", "JA", target_language="Japanese", model="m")
    store.add("en", "EN", target_language="English", model="m")
    inner = _RecordingTranslator(reply="OK")
    t = CachingTranslator(inner, store, model="m", recent_context=5)
    t.translate("something", target_language="English")
    examples = inner.calls[0]["examples"]
    assert examples == [("en", "EN")]


def test_caching_translator_does_not_store_on_inner_error(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    t = CachingTranslator(_RaisingTranslator(), store, model="m")
    with pytest.raises(TranslationError):
        t.translate("Hello", target_language="Korean")
    assert store.count() == 0


def test_caching_translator_zero_context_does_not_touch_translator(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("prev", "P", target_language="Korean", model="m")
    inner = _RecordingTranslator(reply="x")
    t = CachingTranslator(inner, store, model="m", recent_context=0)
    t.translate("new", target_language="Korean")
    # recent_context=0 means no examples set.
    assert inner.calls[0]["examples"] == []
