"""Application entry point — wires together capture, OCR, translation, overlay.

Run with:

    python -m window_translation

or (after install):

    window-translation
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from .capture import Region, RegionSelector, capture_region, perceptual_hash
from .capture.screen import hamming_distance
from .config import AppSettings, default_history_path, load_settings
from .history import HistoryStore, export_csv, export_json, export_txt
from .ocr import build_ocr
from .overlay import HistoryViewer, ResultOverlay, SettingsDialog
from .translate import Translator, TranslationError, build_translator

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- worker
class TranslationWorker(QObject):
    """Runs OCR + translation off the GUI thread."""

    finished = Signal(str, str)  # (source_text, translated_text)
    failed = Signal(str)

    def __init__(
        self,
        ocr,
        translator: Translator,
        target_language: str,
    ) -> None:
        super().__init__()
        self._ocr = ocr
        self._translator = translator
        self._target_language = target_language
        self._image = None  # set via set_image

    def set_image(self, image) -> None:
        self._image = image

    def run(self) -> None:
        try:
            if self._image is None:
                self.failed.emit("번역할 이미지가 없습니다.")
                return
            try:
                ocr_result = self._ocr.run(self._image)
            except RuntimeError as exc:
                # Tesseract 미설치, PaddleOCR 미설치 등 사용자에게 친절한 메시지.
                self.failed.emit(str(exc))
                return
            if ocr_result.is_empty():
                self.failed.emit("OCR에서 텍스트를 찾지 못했습니다. 영역을 더 크게 잡아보세요.")
                return
            try:
                translated = self._translator.translate(
                    ocr_result.text,
                    target_language=self._target_language,
                    source_language=ocr_result.detected_language,
                )
            except TranslationError as exc:
                self.failed.emit(f"번역 실패: {exc}")
                return
            self.finished.emit(ocr_result.text, translated)
        except Exception as exc:  # pragma: no cover — guard against thread-killing crashes
            log.exception("Worker crashed")
            self.failed.emit(f"예상치 못한 오류: {exc}")


# --------------------------------------------------------------- global hotkey
class GlobalHotkey(QObject):
    """Bridge from :mod:`pynput` (background thread) to Qt's event loop."""

    activated = Signal()

    def __init__(self, hotkey: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._hotkey_str = hotkey
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as exc:  # pragma: no cover — platform-specific
            log.warning("Global hotkey disabled: %s", exc)
            return False

        try:
            self._listener = keyboard.GlobalHotKeys(
                {self._hotkey_str: self.activated.emit}
            )
            self._listener.start()
            return True
        except Exception as exc:
            log.warning("Failed to bind hotkey %r: %s", self._hotkey_str, exc)
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._listener = None


# ----------------------------------------------------------------- main object
class TranslatorApp(QObject):
    """Top-level orchestrator kept alive for the lifetime of the Qt app."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._settings: AppSettings = load_settings()
        self._history: Optional[HistoryStore] = None

        self._overlay = self._build_overlay()

        # Active capture region for region-pin mode.
        self._pinned_region: Optional[Region] = None
        self._pinned_hash: Optional[int] = None
        self._pin_timer = QTimer(self)
        self._pin_timer.timeout.connect(self._pin_tick)

        # One live selector / worker at a time.
        self._selector: Optional[RegionSelector] = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[TranslationWorker] = None
        self._last_region: Optional[Region] = None

        # System tray
        self._tray = self._build_tray()
        self._tray.show()

        # Global hotkey
        self._hotkey = GlobalHotkey(self._settings.hotkey, self)
        self._hotkey.activated.connect(self.start_region_selection)
        if not self._hotkey.start():
            self._notify(
                "전역 단축키를 등록할 수 없습니다. 트레이 메뉴를 사용해주세요."
            )

        # 앱 내 히스토리 뷰어 (싱글톤)
        self._history_viewer: Optional[HistoryViewer] = None

    # ---------------------------------------------------------- overlay factory
    def _build_overlay(self) -> ResultOverlay:
        overlay = ResultOverlay(
            font_size=self._settings.overlay_font_size,
            opacity=self._settings.overlay_opacity,
            font_family=self._settings.overlay_font_family,
            line_spacing_percent=self._settings.overlay_line_spacing,
            theme=self._settings.theme,
        )
        overlay.retranslate_requested.connect(self._on_retranslate_requested)
        return overlay

    def _on_retranslate_requested(self) -> None:
        """오버레이 [재번역] 버튼: 마지막 영역을 다시 캡처해 번역."""
        if self._last_region is None:
            self._notify("재번역할 영역이 없습니다. 먼저 영역을 선택해주세요.")
            return
        # pin 모드의 해시는 무효화하여 즉시 재실행되게 한다.
        self._pinned_hash = None
        self._run_translation(self._last_region, initial=True)

    # ---------------------------------------------------------- history store
    def _history_store(self) -> HistoryStore:
        """Return the shared history store, creating it on first use."""
        if getattr(self, "_history", None) is None:
            self._history = HistoryStore(default_history_path())
        return self._history

    # ---------------------------------------------------------- tray / menu
    def _build_tray(self) -> QSystemTrayIcon:
        icon = self._fallback_icon()
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Window Translation")

        menu = QMenu()
        act_translate = QAction("영역 번역…", self)
        act_translate.triggered.connect(self.start_region_selection)
        menu.addAction(act_translate)

        self._act_pin = QAction("현재 영역 핀 (자동 재번역)", self)
        self._act_pin.setCheckable(True)
        self._act_pin.toggled.connect(self._toggle_pin_mode)
        menu.addAction(self._act_pin)

        menu.addSeparator()
        act_settings = QAction("설정…", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        act_history = QAction("히스토리 보기…", self)
        act_history.triggered.connect(self.show_history)
        menu.addAction(act_history)

        act_export = QAction("히스토리 내보내기…", self)
        act_export.triggered.connect(self.export_history)
        menu.addAction(act_export)

        act_clear = QAction("히스토리 삭제", self)
        act_clear.triggered.connect(self.clear_history)
        menu.addAction(act_clear)

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        return tray

    def _fallback_icon(self) -> QIcon:
        # Tiny procedurally-generated icon — avoids shipping an asset file.
        pix = QPixmap(32, 32)
        pix.fill()  # white
        return QIcon(pix)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_region_selection()

    # ---------------------------------------------------------- region flow
    def start_region_selection(self) -> None:
        if self._selector is not None and self._selector.isVisible():
            return
        selector = RegionSelector()
        selector.region_selected.connect(self._on_region_selected)
        selector.cancelled.connect(lambda: setattr(self, "_selector", None))
        selector.destroyed.connect(lambda *_: setattr(self, "_selector", None))
        selector.showFullScreen()
        selector.raise_()
        selector.activateWindow()
        self._selector = selector

    def _on_region_selected(self, region: Region) -> None:
        self._selector = None
        self._last_region = region
        if self._act_pin.isChecked():
            self._pinned_region = region
            self._pinned_hash = None  # force retranslate immediately
        self._run_translation(region, initial=True)

    # ---------------------------------------------------------- pin mode
    def _toggle_pin_mode(self, on: bool) -> None:
        if on:
            if self._last_region is None:
                self._notify(
                    "선택된 영역이 없습니다. 먼저 단축키로 영역을 한 번 잡은 뒤 핀을 켜주세요."
                )
                self._act_pin.setChecked(False)
                return
            self._pinned_region = self._last_region
            self._pinned_hash = None
            interval = max(300, int(self._settings.pin_mode_interval_ms))
            self._pin_timer.start(interval)
        else:
            self._pin_timer.stop()
            self._pinned_region = None
            self._pinned_hash = None

    def _pin_tick(self) -> None:
        if self._pinned_region is None:
            return
        # Don't start a new job while one is in flight.
        if self._worker_thread is not None and self._worker_thread.isRunning():
            return
        try:
            image = capture_region(self._pinned_region)
        except Exception as exc:
            log.warning("Pinned capture failed: %s", exc)
            return
        new_hash = perceptual_hash(image)
        if (
            self._pinned_hash is not None
            and hamming_distance(self._pinned_hash, new_hash)
            <= max(0, int(self._settings.pin_mode_change_threshold))
        ):
            return  # Image hasn't meaningfully changed.
        self._pinned_hash = new_hash
        self._run_translation(self._pinned_region, initial=False, prefetched_image=image)

    # ---------------------------------------------------------- pipeline
    def _run_translation(
        self,
        region: Region,
        *,
        initial: bool,
        prefetched_image=None,
    ) -> None:
        if self._worker_thread is not None and self._worker_thread.isRunning():
            log.info("Translation already running; skipping.")
            return

        if initial:
            self._overlay.show_status("캡처 중…")
            self._overlay._place_near(region)

        try:
            image = prefetched_image if prefetched_image is not None else capture_region(region)
        except Exception as exc:
            self._overlay.show_status(f"캡처 실패: {exc}")
            return

        ocr = build_ocr(
            self._settings.ocr_engine,
            languages=self._settings.ocr_languages,
            tesseract_cmd=self._settings.tesseract_cmd,
        )
        try:
            translator = build_translator(
                self._settings,
                history_store=self._history_store(),
            )
        except TranslationError as exc:
            self._overlay.show_status(f"번역기 오류: {exc}")
            return

        worker = TranslationWorker(ocr, translator, self._settings.target_language)
        worker.set_image(image)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda src, tgt: self._on_translation_finished(region, src, tgt))
        worker.failed.connect(self._on_translation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_worker_thread_finished)

        self._worker = worker
        self._worker_thread = thread
        if initial:
            self._overlay.show_status("OCR + 번역 중…")
        thread.start()

    def _on_worker_thread_finished(self) -> None:
        self._worker = None
        self._worker_thread = None

    def _on_translation_finished(self, region: Region, source: str, translated: str) -> None:
        self._overlay.show_translation(source, translated, near_region=region)

    def _on_translation_failed(self, message: str) -> None:
        self._overlay.show_status(message)

    # ---------------------------------------------------------- misc
    def open_settings(self) -> None:
        dlg = SettingsDialog(self._settings)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            # Restart hotkey and refresh overlay style.
            self._hotkey.stop()
            self._hotkey = GlobalHotkey(self._settings.hotkey, self)
            self._hotkey.activated.connect(self.start_region_selection)
            if not self._hotkey.start():
                self._notify("단축키를 다시 등록할 수 없습니다. 트레이 메뉴를 사용해주세요.")
            # Re-style overlay by recreating it (simpler than hot-swapping styles).
            self._overlay = self._build_overlay()

    def show_history(self) -> None:
        """앱 내 히스토리 뷰어 창을 띄운다."""
        store = self._history_store()
        if self._history_viewer is None:
            self._history_viewer = HistoryViewer(store)
        else:
            self._history_viewer.reload()
        self._history_viewer.show()
        self._history_viewer.raise_()
        self._history_viewer.activateWindow()

    def export_history(self) -> None:
        """파일을 선택해 번역 히스토리를 저장한다."""
        store = self._history_store()
        if store.count() == 0:
            self._notify("히스토리가 비어있어 내보낼 항목이 없습니다.")
            return
        path_str, chosen = QFileDialog.getSaveFileName(
            None,
            "번역 히스토리 내보내기",
            "translation_history.json",
            "JSON (*.json);;CSV (*.csv);;Text (*.txt)",
        )
        if not path_str:
            return
        from pathlib import Path

        path = Path(path_str)
        try:
            entries = store.all()
            if chosen.startswith("CSV") or path.suffix.lower() == ".csv":
                n = export_csv(entries, path)
            elif chosen.startswith("Text") or path.suffix.lower() == ".txt":
                n = export_txt(entries, path)
            else:
                n = export_json(entries, path)
        except OSError as exc:
            self._notify(f"내보내기 실패: {exc}")
            return
        self._notify(f"{n}건을 {path} 에 저장했습니다.")

    def clear_history(self) -> None:
        store = self._history_store()
        count = store.count()
        if count == 0:
            self._notify("히스토리가 이미 비어있습니다.")
            return
        reply = QMessageBox.question(
            None,
            "히스토리 전체 삭제",
            f"저장된 {count}건의 번역을 모두 삭제할까요? 이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            removed = store.delete_all()
            self._notify(f"{removed}건을 삭제했습니다.")

    def _notify(self, message: str) -> None:
        if self._tray.isVisible():
            self._tray.showMessage("Window Translation", message)
        else:
            QMessageBox.information(None, "Window Translation", message)

    def _quit(self) -> None:
        try:
            self._pin_timer.stop()
            self._hotkey.stop()
        finally:
            self._app.quit()


# ----------------------------------------------------------------- entry point
def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Window Translation")
    app.setQuitOnLastWindowClosed(False)  # tray-only app

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "Window Translation",
            "이 시스템에서 시스템 트레이를 사용할 수 없습니다.",
        )
        return 1

    def _excepthook(exc_type, exc, tb):  # pragma: no cover — last-resort guard
        log.error("Uncaught exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = _excepthook

    translator_app = TranslatorApp(app)  # noqa: F841 — kept alive by Qt
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
