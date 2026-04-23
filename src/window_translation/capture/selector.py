"""Full-screen, translucent overlay used to drag-select a capture region."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .screen import Region


class RegionSelector(QWidget):
    """Modal, frameless, translucent widget for rubber-band region selection.

    Emits :attr:`region_selected` with a :class:`Region` on completion, or
    :attr:`cancelled` if the user presses Escape / right-clicks.
    """

    region_selected = Signal(object)  # Region
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._origin: Optional[tuple[int, int]] = None
        self._current: Optional[tuple[int, int]] = None

        # Cover the entire virtual desktop (all monitors).
        geom = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geom)

    # ------------------------------------------------------------------ events
    def paintEvent(self, event) -> None:  # noqa: D401 — Qt override
        painter = QPainter(self)
        # Dim the whole screen.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        rect = self._current_rect()
        if rect is not None and rect.isValid():
            # Clear the selected rectangle so the user sees through it.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            pen = QPen(QColor(60, 180, 255), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Size label
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                rect.x() + 6,
                max(rect.y() - 6, 14),
                f"{rect.width()} x {rect.height()}",
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            p = event.position().toPoint()
            self._origin = (p.x(), p.y())
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is None:
            return
        p = event.position().toPoint()
        self._current = (p.x(), p.y())
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        p = event.position().toPoint()
        self._current = (p.x(), p.y())
        rect = self._current_rect()
        self._origin = self._current = None
        self.update()

        if rect is None or rect.width() < 4 or rect.height() < 4:
            self._cancel()
            return

        # Translate widget-local coordinates back to virtual-desktop coords.
        top_left = self.mapToGlobal(rect.topLeft())
        region = Region(top_left.x(), top_left.y(), rect.width(), rect.height())
        self.region_selected.emit(region)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    # ---------------------------------------------------------------- helpers
    def _current_rect(self) -> Optional[QRect]:
        if self._origin is None or self._current is None:
            return None
        x0, y0 = self._origin
        x1, y1 = self._current
        return QRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

    def _cancel(self) -> None:
        self.cancelled.emit()
        self.close()


def select_region(on_selected: Callable[[Region], None], on_cancel: Optional[Callable[[], None]] = None) -> RegionSelector:
    """Convenience helper: create, show, and return a :class:`RegionSelector`.

    The caller must keep a reference to the returned widget (or rely on the
    Qt event loop) until one of the callbacks fires.
    """
    selector = RegionSelector()
    selector.region_selected.connect(on_selected)
    if on_cancel is not None:
        selector.cancelled.connect(on_cancel)
    selector.showFullScreen()
    selector.raise_()
    selector.activateWindow()
    return selector


__all__ = ["RegionSelector", "select_region"]
