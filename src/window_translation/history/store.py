"""SQLite-backed translation history + cache.

Schema is intentionally small and self-contained. We normalise the source
text (collapse whitespace) before hashing so trivially different inputs
still hit the cache. The store is safe to share across threads because we
open a fresh connection per call (SQLite serialises writes anyway, and the
app is translation-bound, not DB-bound).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      REAL    NOT NULL,
    source_hash     TEXT    NOT NULL,
    source_text     TEXT    NOT NULL,
    translated_text TEXT    NOT NULL,
    source_language TEXT    NOT NULL DEFAULT '',
    target_language TEXT    NOT NULL DEFAULT '',
    provider        TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_hash_lang_model
    ON translations(source_hash, target_language, model);
CREATE INDEX IF NOT EXISTS idx_created
    ON translations(created_at DESC);
"""

# How long (in seconds) to wait for the SQLite write lock before raising.
# Translation is latency-tolerant by design, but unbounded waits could
# deadlock the pin-mode timer if anything ever holds a long-running
# transaction, so we keep a small budget.
DB_CONNECTION_TIMEOUT = 5.0


def _normalise(text: str) -> str:
    """Collapse internal whitespace so near-identical OCR outputs hit cache."""
    return " ".join(text.split())


def hash_source(text: str) -> str:
    """Return a stable hash for a (whitespace-normalised) source string."""
    normalised = _normalise(text)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


@dataclass
class HistoryEntry:
    id: int
    created_at: float
    source_hash: str
    source_text: str
    translated_text: str
    source_language: str = ""
    target_language: str = ""
    provider: str = ""
    model: str = ""


class HistoryStore:
    """Thin SQLite wrapper for the translation history + cache."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Initialise schema up-front so every subsequent open is cheap.
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ infra
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=DB_CONNECTION_TIMEOUT)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------------------------------------------------------- cache helpers
    def lookup(
        self,
        source_text: str,
        target_language: str,
        model: str = "",
    ) -> Optional[HistoryEntry]:
        """Return the most recent cached translation, or ``None``.

        The lookup matches on ``(source_hash, target_language)`` and, when
        ``model`` is non-empty, also on ``model`` — different models can
        legitimately produce different translations, so we only coalesce
        within a model.
        """
        if not source_text or not source_text.strip():
            return None
        src_hash = hash_source(source_text)
        sql = (
            "SELECT * FROM translations "
            "WHERE source_hash = ? AND target_language = ?"
        )
        params: List[object] = [src_hash, target_language]
        if model:
            sql += " AND model = ?"
            params.append(model)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return _row_to_entry(row) if row else None

    # --------------------------------------------------------------- mutation
    def add(
        self,
        source_text: str,
        translated_text: str,
        *,
        source_language: str = "",
        target_language: str = "",
        provider: str = "",
        model: str = "",
    ) -> HistoryEntry:
        if not source_text.strip() or not translated_text.strip():
            raise ValueError("source_text and translated_text must be non-empty")
        src_hash = hash_source(source_text)
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO translations "
                "(created_at, source_hash, source_text, translated_text, "
                " source_language, target_language, provider, model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    src_hash,
                    source_text,
                    translated_text,
                    source_language,
                    target_language,
                    provider,
                    model,
                ),
            )
            new_id = int(cur.lastrowid or 0)
        return HistoryEntry(
            id=new_id,
            created_at=now,
            source_hash=src_hash,
            source_text=source_text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language,
            provider=provider,
            model=model,
        )

    def delete_all(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM translations")
            return cur.rowcount or 0

    # ------------------------------------------------------------- retrieval
    def recent(
        self,
        limit: int = 50,
        target_language: Optional[str] = None,
    ) -> List[HistoryEntry]:
        """Return the N most recent entries, newest first."""
        limit = max(0, int(limit))
        sql = "SELECT * FROM translations"
        params: Sequence[object] = ()
        if target_language:
            sql += " WHERE target_language = ?"
            params = (target_language,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params = tuple(params) + (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def all(self) -> List[HistoryEntry]:
        """Return every entry, newest first (for export)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM translations ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM translations"
            ).fetchone()
        return int(n)


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=int(row["id"]),
        created_at=float(row["created_at"]),
        source_hash=row["source_hash"],
        source_text=row["source_text"],
        translated_text=row["translated_text"],
        source_language=row["source_language"] or "",
        target_language=row["target_language"] or "",
        provider=row["provider"] or "",
        model=row["model"] or "",
    )


__all__ = ["HistoryStore", "HistoryEntry", "hash_source"]


# Convenience: iterate helper used by export writers.
def iter_entries(entries: Iterable[HistoryEntry]) -> Iterable[dict]:
    for e in entries:
        yield {
            "id": e.id,
            "created_at": e.created_at,
            "source_hash": e.source_hash,
            "source_text": e.source_text,
            "translated_text": e.translated_text,
            "source_language": e.source_language,
            "target_language": e.target_language,
            "provider": e.provider,
            "model": e.model,
        }
