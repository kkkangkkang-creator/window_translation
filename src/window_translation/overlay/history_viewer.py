"""앱 안에서 번역 히스토리를 보여주는 뷰어 창.

트레이 메뉴의 "히스토리 보기…" 항목으로 열린다. 검색, 행 더블클릭으로
클립보드 복사, 내보내기, 전체 삭제 기능을 제공한다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..history import HistoryEntry, HistoryStore, export_csv, export_json, export_txt


class HistoryViewer(QDialog):
    """히스토리 테이블 뷰어 (시각/원문/번역/모델)."""

    COLUMNS = ("시각", "원문", "번역", "모델")

    def __init__(
        self,
        store: HistoryStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Window Translation — 히스토리")
        self.setModal(False)
        self.resize(820, 520)

        self._store = store
        self._entries: List[HistoryEntry] = []

        # --- 상단: 검색 + 버튼들
        self._search = QLineEdit()
        self._search.setPlaceholderText("원문 / 번역에서 검색…")
        self._search.textChanged.connect(self._apply_filter)

        self._refresh_btn = QPushButton("새로고침")
        self._refresh_btn.clicked.connect(self.reload)

        self._export_btn = QPushButton("내보내기")
        self._export_btn.clicked.connect(self._export)

        self._clear_btn = QPushButton("전체 삭제")
        self._clear_btn.clicked.connect(self._clear_all)

        top = QHBoxLayout()
        top.addWidget(QLabel("검색:"))
        top.addWidget(self._search, 1)
        top.addWidget(self._refresh_btn)
        top.addWidget(self._export_btn)
        top.addWidget(self._clear_btn)

        # --- 테이블
        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.cellDoubleClicked.connect(self._on_double_click)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #888;")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._status)

        self.reload()

    # ---------------------------------------------------------- data
    def reload(self) -> None:
        try:
            self._entries = self._store.all()
        except Exception as exc:
            QMessageBox.warning(self, "Window Translation", f"히스토리를 불러오지 못했습니다: {exc}")
            self._entries = []
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._search.text().strip().lower()
        if query:
            rows = [
                e
                for e in self._entries
                if query in e.source_text.lower() or query in e.translated_text.lower()
            ]
        else:
            rows = list(self._entries)

        self._table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.created_at))
            items = [
                QTableWidgetItem(ts),
                QTableWidgetItem(_one_line(e.source_text)),
                QTableWidgetItem(_one_line(e.translated_text)),
                QTableWidgetItem(e.model or ""),
            ]
            # 더블클릭 시 원본 entry 를 복원할 수 있도록 행 0열에 인덱스 저장.
            items[0].setData(Qt.ItemDataRole.UserRole, e)
            for col, item in enumerate(items):
                self._table.setItem(i, col, item)

        total = len(self._entries)
        shown = len(rows)
        if total == shown:
            self._status.setText(f"{total}건")
        else:
            self._status.setText(f"{shown} / {total}건")

    # ---------------------------------------------------------- actions
    def _on_double_click(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        entry: HistoryEntry = item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(entry.translated_text)
        self._status.setText("번역을 클립보드에 복사했습니다.")

    def _export(self) -> None:
        if not self._entries:
            QMessageBox.information(self, "Window Translation", "내보낼 히스토리가 없습니다.")
            return
        path_str, chosen = QFileDialog.getSaveFileName(
            self,
            "히스토리 내보내기",
            "translation_history.json",
            "JSON (*.json);;CSV (*.csv);;Text (*.txt)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            n = _export_by_filter(self._entries, path, chosen)
        except OSError as exc:
            QMessageBox.warning(self, "Window Translation", f"내보내기 실패: {exc}")
            return
        QMessageBox.information(
            self, "Window Translation", f"{n}건을 {path} 에 저장했습니다."
        )

    def _clear_all(self) -> None:
        n = len(self._entries)
        if n == 0:
            return
        reply = QMessageBox.question(
            self,
            "히스토리 전체 삭제",
            f"저장된 {n}건의 번역을 모두 삭제할까요? 이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.delete_all()
        except Exception as exc:
            QMessageBox.warning(self, "Window Translation", f"삭제 실패: {exc}")
            return
        self.reload()


def _one_line(text: str) -> str:
    """테이블 셀에 들어가도록 줄바꿈을 ``⏎`` 로 치환."""
    return text.replace("\r", "").replace("\n", " ⏎ ")


def _export_by_filter(entries: List[HistoryEntry], path: Path, chosen: str) -> int:
    """파일 다이얼로그가 알려준 필터/확장자에 맞춰 적절한 export 함수 호출."""
    suffix = path.suffix.lower()
    if chosen.startswith("CSV") or suffix == ".csv":
        return export_csv(entries, path)
    if chosen.startswith("Text") or suffix == ".txt":
        return export_txt(entries, path)
    return export_json(entries, path)


__all__ = ["HistoryViewer"]
