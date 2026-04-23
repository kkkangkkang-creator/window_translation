"""번역 결과를 보여주는 프레임 없는 항상-위 오버레이 창."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPalette,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..capture import Region


class ResultOverlay(QWidget):
    """캡처 영역 옆에 원문과 번역문을 함께 보여주는 위젯.

    프레임이 없고 항상 위에 떠 있으며, 제목 영역을 드래그해 이동할 수 있다.
    우상단의 [복사], [재번역], [닫기] 버튼으로 빠르게 조작할 수 있다.
    """

    #: 사용자가 [재번역] 버튼을 눌렀을 때 발생.
    retranslate_requested = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        font_size: int = 14,
        opacity: float = 0.92,
        font_family: str = "",
        line_spacing_percent: int = 140,
        theme: str = "light",
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowOpacity(max(0.3, min(1.0, opacity)))

        from .theme import get_theme

        t = get_theme(theme)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(t["window_bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(t["window_fg"]))
        self.setAutoFillBackground(True)
        self.setPalette(palette)

        self._font_size = max(8, int(font_size))
        self._font_family = (font_family or "").strip()
        self._line_spacing_percent = max(100, min(300, int(line_spacing_percent)))

        font = QFont()
        if self._font_family:
            font.setFamily(self._font_family)
        font.setPointSize(self._font_size)

        self._title = QLabel("번역")
        self._title.setStyleSheet(
            f"color: {t['title_fg']}; padding: 4px 8px; font-weight: 600;"
        )

        btn_style = (
            f"QPushButton {{ color: {t['close_fg']}; background: transparent; "
            f"border: 1px solid {t['source_border']}; border-radius: 4px; "
            "padding: 1px 6px; font-size: 11px; }} "
            f"QPushButton:hover {{ color: {t['close_fg_hover']}; }}"
        )
        self._copy_btn = QPushButton("복사")
        self._copy_btn.setToolTip("번역 결과를 클립보드에 복사합니다")
        self._copy_btn.setStyleSheet(btn_style)
        self._copy_btn.clicked.connect(self._copy_translation)

        self._retranslate_btn = QPushButton("재번역")
        self._retranslate_btn.setToolTip("같은 영역을 다시 캡처해 번역합니다")
        self._retranslate_btn.setStyleSheet(btn_style)
        self._retranslate_btn.clicked.connect(self.retranslate_requested.emit)

        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ color: {t['close_fg']}; background: transparent; "
            f"border: none; font-size: 18px; }} "
            f"QPushButton:hover {{ color: {t['close_fg_hover']}; }}"
        )
        self._close_btn.clicked.connect(self.hide)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._copy_btn)
        header.addWidget(self._retranslate_btn)
        header.addWidget(self._close_btn)

        self._source_view = QTextEdit()
        self._source_view.setReadOnly(True)
        self._source_view.setFont(font)
        self._source_view.setStyleSheet(
            f"QTextEdit {{ background: {t['source_bg']}; color: {t['source_fg']}; "
            f"border: 1px solid {t['source_border']}; border-radius: 4px; "
            "padding: 6px; }}"
        )
        self._source_view.setMaximumHeight(120)

        self._translation_view = QTextEdit()
        self._translation_view.setReadOnly(True)
        self._translation_view.setFont(font)
        self._translation_view.setStyleSheet(
            f"QTextEdit {{ background: {t['trans_bg']}; color: {t['trans_fg']}; "
            f"border: 1px solid {t['trans_border']}; border-radius: 4px; "
            "padding: 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self._source_view)
        layout.addWidget(self._translation_view, 1)

        self.resize(420, 260)
        self._drag_offset: Optional[QPoint] = None

    # -------------------------------------------------------- public API
    def show_translation(
        self,
        source_text: str,
        translated_text: str,
        near_region: Optional[Region] = None,
    ) -> None:
        self._source_view.setPlainText(source_text)
        self._translation_view.setPlainText(translated_text)
        self._apply_line_spacing(self._source_view)
        self._apply_line_spacing(self._translation_view)
        if near_region is not None:
            self._place_near(near_region)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_status(self, message: str) -> None:
        """Show a transient status message in the translation pane."""
        self._translation_view.setPlainText(message)
        self._apply_line_spacing(self._translation_view)
        self.show()
        self.raise_()

    # -------------------------------------------------------- styling
    def _apply_line_spacing(self, view: QTextEdit) -> None:
        """Apply the configured line spacing to every block in ``view``."""
        block_fmt = QTextBlockFormat()
        # LineHeightTypes.ProportionalHeight == 1 (percentage-based).
        # Using the integer value keeps this compatible across PySide6 versions.
        block_fmt.setLineHeight(self._line_spacing_percent, 1)
        cursor = QTextCursor(view.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(block_fmt)

    # -------------------------------------------------------- placement
    def _place_near(self, region: Region) -> None:
        """Position the overlay next to ``region`` without leaving the screen."""
        screen = QGuiApplication.screenAt(QPoint(region.left, region.top))
        avail = (screen or QGuiApplication.primaryScreen()).availableGeometry()

        w, h = self.width(), self.height()
        # Prefer: directly below the region, left-aligned.
        x = region.left
        y = region.bottom + 8

        if y + h > avail.bottom():
            # Not enough room below — try above.
            y = region.top - h - 8
        if y < avail.top():
            # Still no room — align with region top, shifted right of it.
            y = max(region.top, avail.top())
            x = region.right + 8
        if x + w > avail.right():
            x = max(avail.right() - w, avail.left())
        if x < avail.left():
            x = avail.left()

        self.move(x, y)

    # -------------------------------------------------------- dragging
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None

    # -------------------------------------------------------- helpers
    def _copy_translation(self) -> None:
        text = self._translation_view.toPlainText()
        if not text:
            return
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(text)


__all__ = ["ResultOverlay"]
