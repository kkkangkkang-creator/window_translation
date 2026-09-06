"""Application entry point — wires together capture, OCR, translation, overlay.

Run with:

    python -m window_translation

or (after install):

    window-translation
"""

from __future__ import annotations

import logging
import hashlib
import copy
import sys
import traceback
from typing import Optional, Protocol

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QInputDialog,
    QMessageBox,
    QSystemTrayIcon,
)

from .capture import Region, RegionSelector, capture_region, perceptual_hash
from .capture.screen import hamming_distance
from .capture.window import list_windows, WindowCapture, relative_crop, crop_region
from .overlay.inline import InlineOverlay
from .ocr.tesseract import OCRBlock
from .config import AppSettings, default_history_path, load_settings
from .history import HistoryStore, export_csv, export_json, export_txt
from .ocr import build_ocr
from .overlay import HistoryViewer, ResultOverlay, SettingsDialog
from .translate import Translator, TranslationError, build_translator

log = logging.getLogger(__name__)


class _OCREngine(Protocol):
    """Tesseract / PaddleOCR 백엔드가 공통으로 만족해야 하는 인터페이스."""

    def run(self, img):  # noqa: D401, ANN001 — 런타임 PIL.Image 의존을 피함
        ...


# --------------------------------------------------------------------- worker
class TranslationWorker(QObject):
    """Runs OCR + translation off the GUI thread."""

    layout_ready = Signal(object, object)
    source_ready = Signal(str)
    finished = Signal(str, str)  # (source_text, translated_text)
    failed = Signal(str)

    def __init__(
        self,
        ocr: _OCREngine,
        translator: Translator,
        target_language: str,
    ) -> None:
        super().__init__()
        self._ocr = ocr
        self._translator = translator
        self._target_language = target_language
        self._image = None  # set via set_image
        self.inline = False
        self.memo = {}
        self.validate_image = None

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
                self.layout_ready.emit([], self._image.size)
                self.finished.emit("", "")
                return
            self.source_ready.emit(ocr_result.text)
            if self.inline:
                blocks = ocr_result.blocks or [OCRBlock(ocr_result.text, 0, 0, self._image.width, self._image.height)]
                results = []
                for block in blocks:
                    key = ' '.join(block.text.split())
                    if key not in self.memo:
                        self.memo[key] = self._translator.translate(block.text,
                            target_language=self._target_language, source_language=ocr_result.detected_language)
                        if len(self.memo) > 1000:
                            self.memo.pop(next(iter(self.memo)))
                    results.append((block, self.memo[key]))
                if self.validate_image:
                    latest = self.validate_image()
                    if latest is not None and latest.tobytes() != self._image.tobytes():
                        current = self._ocr.run(latest)
                        current_blocks = current.blocks or ([OCRBlock(current.text, 0, 0, latest.width, latest.height)] if current.text.strip() else [])
                        # Never place translations from an old page over a new page.
                        if [(b.text, b.left, b.top, b.width, b.height) for b in current_blocks] != [(b.text, b.left, b.top, b.width, b.height) for b in blocks]:
                            results = []
                self.layout_ready.emit(results, self._image.size)
                self.finished.emit(ocr_result.text, '\n'.join(t for _, t in results))
                return
            try:
                key = ' '.join(ocr_result.text.split())
                translated = self.memo.get(key)
                if translated is None:
                    translated = self._translator.translate(
                    ocr_result.text,
                    target_language=self._target_language,
                    source_language=ocr_result.detected_language,
                    )
                    self.memo[key] = translated
            except TranslationError as exc:
                self.failed.emit(f"번역 실패: {exc}")
                return
            self.finished.emit(ocr_result.text, translated)
        except TranslationError as exc:
            self.failed.emit(f"번역 실패: {exc}")
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
        self._inline = InlineOverlay(self._settings)
        self._window_capture = None
        self._target = None
        self._target_crop = (0, 0, 1, 1)
        self._generation = 0
        self._active_generation = -1
        self._memo = {}
        self._show_inline = True
        self._last_frame_key = None
        self._active_frame_key = None
        self._layout = None
        self._was_foreground = False
        self._visibility_timer = QTimer(self)
        self._visibility_timer.timeout.connect(self._sync_overlay)
        self._visibility_timer.start(150)

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

        self._toggle_hotkey = GlobalHotkey('<ctrl>+<alt>+<f10>', self)
        self._toggle_hotkey.activated.connect(self.toggle_inline)
        self._toggle_hotkey.start()

        # 앱 내 히스토리 뷰어 (싱글톤)
        self._history_viewer: Optional[HistoryViewer] = None
        self._settings_dialog = None
        self._quitting = False
        self._capture_pending = False
        self._active_region = None
        QTimer.singleShot(0, self.open_settings)

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
        choose_app = QAction("번역할 앱 선택…", self)
        choose_app.triggered.connect(self.choose_window)
        menu.addAction(choose_app)
        screen_mode = QAction("앱 지정 해제 · 화면 영역 사용", self)
        screen_mode.triggered.connect(self.clear_window)
        menu.addAction(screen_mode)
        toggle_overlay = QAction("원문 보기 / 번역 표시", self)
        toggle_overlay.triggered.connect(self.toggle_inline)
        menu.addAction(toggle_overlay)

        self._act_pin = QAction("현재 영역 핀 (자동 재번역)", self)
        self._act_pin.setCheckable(True)
        self._act_pin.toggled.connect(self._toggle_pin_mode)
        menu.addAction(self._act_pin)

        menu.addSeparator()
        act_settings = QAction("설정…", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        act_history = QAction("번역 라이브러리…", self)
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

        self._tray_menu = menu  # Keep the Python-owned menu alive.
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

    def choose_window(self):
        windows = list_windows()
        if not windows:
            self._notify("선택할 앱이 없습니다. 번역할 앱을 먼저 열어주세요.")
            return
        labels = [f"{w.title}  ·  {w.pid}/{w.hwnd}" for w in windows]
        label, ok = QInputDialog.getItem(None, "번역할 앱 선택", "다른 창에 가려져도 이 앱을 계속 읽습니다.", labels, 0, False)
        if not ok:
            return
        target = windows[labels.index(label)]
        try:
            bounds = target.bounds()
            capture = WindowCapture(target)
        except Exception as exc:
            self._notify(f"앱 캡처 시작 실패: {exc}")
            return
        self.clear_window()
        self._target, self._window_capture = target, capture
        self._target_crop = (0, 0, 1, 1)
        self._last_region = self._pinned_region = bounds
        self._act_pin.setChecked(True)
        self._pin_timer.start(max(300, self._settings.pin_mode_interval_ms))
        self._tray.setToolTip(f"번역 중: {target.title}")
        self._notify("앱 전체 자동 번역을 시작합니다. 앱으로 돌아가 단축키를 누르면 번역 영역을 좁힐 수 있습니다.")

    def clear_window(self):
        self._generation += 1
        self._memo = {}
        self._last_frame_key = None
        self._layout = None
        self._inline.clear()
        self._overlay.hide()
        self._act_pin.setChecked(False)
        if self._window_capture:
            self._window_capture.stop()
        self._window_capture = self._target = None
        self._last_region = self._pinned_region = None
        self._tray.setToolTip("Window Translation")

    def toggle_inline(self):
        self._show_inline = not self._show_inline
        self._sync_overlay()

    def _sync_overlay(self):
        if self._target:
            foreground = self._target.foreground()
            if foreground and not self._was_foreground:
                # Recheck current content before revealing stored overlays on return.
                self._inline.clear()
                self._last_frame_key = None
            self._was_foreground = foreground
            if not self._target.valid():
                self.clear_window()
                self._notify("번역 대상 앱이 닫혔습니다.")
                return
            try:
                region = crop_region(self._target.bounds(), self._target_crop)
                self._pinned_region = self._last_region = region
                self._inline.place(region)
            except RuntimeError:
                self._inline.hide(); self._overlay.hide(); return
        visible = (self._show_inline and self._selector is None and not self._capture_pending
                   and (self._target is None or self._target.foreground()))
        if self._settings.inline_overlay:
            self._overlay.hide()
            if visible and self._inline.blocks:
                self._inline.show()
            else:
                self._inline.hide()
        elif not visible:
            self._overlay.hide()
        elif self._last_frame_key is not None:
            self._overlay.show()

    def _capture_image(self, region):
        if self._window_capture:
            return self._window_capture.image(self._target_crop)
        return capture_region(region)

    @staticmethod
    def _frame_key(image):
        return hashlib.sha256(image.tobytes()).digest()

    # ---------------------------------------------------------- region flow
    def start_region_selection(self) -> None:
        if self._selector is not None and self._selector.isVisible():
            return
        self._inline.hide()
        selector = RegionSelector()
        selector.region_selected.connect(self._on_region_selected)
        selector.cancelled.connect(lambda: setattr(self, "_selector", None))
        selector.destroyed.connect(lambda *_: setattr(self, "_selector", None))
        selector.show()
        selector.raise_()
        selector.activateWindow()
        self._selector = selector

    def _on_region_selected(self, region: Region) -> None:
        self._selector = None
        if self._target:
            try:
                self._target_crop = relative_crop(region, self._target.bounds())
                region = crop_region(self._target.bounds(), self._target_crop)
            except (ValueError, RuntimeError) as exc:
                self._notify(str(exc)); return
        self._generation += 1
        self._memo = {}
        self._last_frame_key = None
        self._inline.clear()
        self._last_region = region
        self._act_pin.setChecked(True)
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
            self._last_frame_key = None
            interval = max(300, int(self._settings.pin_mode_interval_ms))
            self._pin_timer.start(interval)
        else:
            self._pin_timer.stop()
            self._pinned_region = None
            self._pinned_hash = None

    def _pin_tick(self) -> None:
        if self._pinned_region is None or self._capture_pending or self._selector is not None:
            return
        if self._worker_thread is not None:
            return
        # Desktop capture must not OCR our own output. Window capture excludes it.
        if self._window_capture is None and (self._inline.isVisible() or self._overlay.isVisible()):
            self._capture_pending = True
            self._inline.hide(); self._overlay.hide()
            QTimer.singleShot(100, self._pin_after_hide)
            return
        self._pin_after_hide()

    def _pin_after_hide(self):
        self._capture_pending = False
        if not self._act_pin.isChecked() or self._pinned_region is None or self._quitting or self._worker_thread is not None:
            return
        try:
            image = self._capture_image(self._pinned_region)
        except Exception as exc:
            self._act_pin.setChecked(False)
            self._inline.clear()
            self._notify(f"캡처가 중지됐습니다: {exc}")
            return
        if image is None:
            return
        key = self._frame_key(image)
        if key == self._last_frame_key:
            self._sync_overlay()
            if not self._settings.inline_overlay and (not self._target or self._target.foreground()):
                self._overlay.show()
            return
        self._inline.clear()
        self._run_translation(self._pinned_region, initial=False, prefetched_image=image)

    # ---------------------------------------------------------- pipeline
    def _run_translation(
        self,
        region: Region,
        *,
        initial: bool,
        prefetched_image=None,
    ) -> None:
        if self._worker_thread is not None:
            log.info("Translation already running; skipping.")
            return

        if prefetched_image is None:
            if self._capture_pending:
                return
            self._capture_pending = True
            self._overlay.hide()
            self._inline.hide()
            generation = self._generation
            QTimer.singleShot(100, lambda: self._capture_and_translate(region, initial) if generation == self._generation else setattr(self, "_capture_pending", False))
            return

        image = prefetched_image
        self._active_frame_key = self._frame_key(image)
        self._active_generation = self._generation
        self._overlay.clear_source()

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
            self._on_translation_failed(f"번역기 오류: {exc}")
            return

        worker = TranslationWorker(ocr, translator, self._settings.target_language)
        worker.inline = self._settings.inline_overlay
        worker.memo = self._memo
        if self._window_capture:
            capture, crop = self._window_capture, self._target_crop
            worker.validate_image = lambda: capture.image(crop)
        if worker.inline and hasattr(ocr, 'psm'):
            ocr.psm = 3
        worker.layout_ready.connect(self._on_layout_ready)
        worker.set_image(image)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        self._active_region = region
        worker.source_ready.connect(self._on_source_ready)
        worker.finished.connect(self._on_translation_finished)
        worker.failed.connect(self._on_translation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_worker_thread_finished)

        self._worker = worker
        self._worker_thread = thread
        if initial:
            self._overlay._place_near(region)
            self._overlay.show_status("OCR + 번역 중…")
        thread.start()

    def _capture_and_translate(self, region: Region, initial: bool) -> None:
        self._capture_pending = False
        if self._quitting:
            return
        try:
            image = self._capture_image(region)
            if image is None:
                return
        except Exception as exc:
            self._overlay.show_status(f"캡처 실패: {exc}")
            return
        self._run_translation(region, initial=initial, prefetched_image=image)

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        # finished may be emitted before the native thread completes TLS cleanup.
        thread = self._worker_thread
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self._worker = None
        self._worker_thread = None
        if self._quitting:
            self._finish_quit()

    @Slot(str)
    def _on_source_ready(self, source: str) -> None:
        if self._active_generation != self._generation:
            return
        self._overlay.show_source(source, near_region=self._active_region)
        self._sync_overlay()

    @Slot(str, str)
    def _on_translation_finished(self, source: str, translated: str) -> None:
        if self._active_generation != self._generation:
            return
        self._last_frame_key = self._active_frame_key
        if not source:
            self._inline.clear()
            self._overlay.hide()
            return
        self._overlay.show_translation(source, translated, near_region=self._active_region)
        self._sync_overlay()

    @Slot(object, object)
    def _on_layout_ready(self, blocks, image_size):
        if self._active_generation != self._generation:
            return
        self._inline.present(blocks, image_size, self._last_region or self._active_region)
        self._sync_overlay()

    @Slot(str)
    def _on_translation_failed(self, message: str) -> None:
        if self._active_generation != self._generation:
            return
        self._inline.clear()
        self._overlay.show_status(message)
        # A failed API must not be retried and billed indefinitely by the timer.
        self._act_pin.setChecked(False)
        self._notify(message)

    # ---------------------------------------------------------- misc
    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self._settings)
            self._settings_dialog.settings_applied.connect(self._apply_settings)
            self._settings_dialog.capture_requested.connect(self.start_region_selection)
            self._settings_dialog.app_requested.connect(self.choose_window)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _apply_settings(self) -> None:
        self._generation += 1
        self._memo = {}
        self._last_frame_key = None
        self._inline.clear()
        self._inline.settings = self._settings
        self._hotkey.stop()
        self._hotkey = GlobalHotkey(self._settings.hotkey, self)
        self._hotkey.activated.connect(self.start_region_selection)
        if not self._hotkey.start():
            self._notify("단축키를 등록할 수 없습니다. 다른 조합으로 바꾸거나 영역 선택 버튼을 사용해주세요.")
        self._overlay.close()
        self._overlay.deleteLater()
        self._overlay = self._build_overlay()
        if self._pin_timer.isActive():
            self._pin_timer.setInterval(max(300, int(self._settings.pin_mode_interval_ms)))

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
            self._visibility_timer.stop()
            self._toggle_hotkey.stop()
            if self._window_capture:
                self._window_capture.stop()
            self._hotkey.stop()
        finally:
            self._quitting = True
            self._finish_quit()

    def _finish_quit(self) -> None:
        connection_running = self._settings_dialog is not None and self._settings_dialog._connection_thread is not None
        if self._worker_thread is not None or connection_running:
            self._overlay.show_status("진행 중인 작업을 마치고 종료합니다…")
            QTimer.singleShot(100, self._finish_quit)
        else:
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
