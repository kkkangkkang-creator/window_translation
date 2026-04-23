"""Export translation history to JSON or CSV."""

from __future__ import annotations

import csv
import json
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


__all__ = ["export_json", "export_csv", "CSV_FIELDS"]
