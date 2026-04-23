"""번역 히스토리를 JSON / CSV / TXT로 내보내는 헬퍼."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Iterable

from .store import HistoryEntry, iter_entries

CSV_FIELDS = [
    "id",
    "created_at",
    "source_language",
    "target_language",
    "provider",
    "model",
    "source_text",
    "translated_text",
]


def export_json(entries: Iterable[HistoryEntry], path: Path) -> int:
    """Write ``entries`` as a UTF-8 JSON array. Returns the number written."""
    data = list(iter_entries(entries))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(data)


def export_csv(entries: Iterable[HistoryEntry], path: Path) -> int:
    """Write ``entries`` as CSV. Returns the number written."""
    rows = list(iter_entries(entries))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" is required for csv on Windows; utf-8-sig so Excel opens
    # Korean/Japanese characters correctly without manual encoding steps.
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def export_txt(entries: Iterable[HistoryEntry], path: Path) -> int:
    """히스토리를 사람이 읽기 쉬운 텍스트로 저장합니다.

    한 줄 형식: ``[YYYY-MM-DD HH:MM:SS] 원문 → 번역``
    여러 줄 텍스트의 줄바꿈은 ``⏎`` 로 치환해 한 줄을 유지합니다.
    """
    rows = list(entries)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for e in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.created_at))
        src = e.source_text.replace("\r", "").replace("\n", " ⏎ ")
        tgt = e.translated_text.replace("\r", "").replace("\n", " ⏎ ")
        lines.append(f"[{ts}] {src} → {tgt}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(rows)


__all__ = ["export_json", "export_csv", "export_txt", "CSV_FIELDS"]
