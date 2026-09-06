"""Regression checks for portable executable startup and OCR resolution."""
import sys
from pathlib import Path

from window_translation.ocr.tesseract import resolve_tesseract


def test_frozen_engine_precedes_system_install(tmp_path, monkeypatch):
    bundled = tmp_path / 'tesseract' / 'tesseract.exe'
    bundled.parent.mkdir()
    bundled.touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr('shutil.which', lambda _: '/some/system/tesseract')
    assert resolve_tesseract() == bundled


def test_explicit_directory_and_invalid_path(tmp_path):
    import os
    executable = tmp_path / ('tesseract.exe' if os.name == 'nt' else 'tesseract')
    executable.touch()
    assert resolve_tesseract(str(tmp_path)) == executable
    assert resolve_tesseract(str(tmp_path / 'missing')) is None


def test_gui_constructs_and_renders(monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from window_translation.config import AppSettings
    from window_translation.overlay import ResultOverlay, SettingsDialog
    app = QApplication.instance() or QApplication([])
    overlay = ResultOverlay()
    settings = SettingsDialog(AppSettings())
    overlay.show_translation('Hello', '안녕하세요')
    app.processEvents()
    assert overlay._translation_view.toPlainText() == '안녕하세요'
    settings.close()
    overlay.close()


def test_source_remains_visible_when_translation_fails(monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from window_translation.app import TranslationWorker
    from window_translation.ocr.tesseract import OCRResult
    from window_translation.overlay import ResultOverlay
    from window_translation.translate import TranslationError
    app = QApplication.instance() or QApplication([])
    overlay = ResultOverlay()
    events = []
    class OCR:
        def run(self, image):
            return OCRResult('Hello world', 'en')
    class FailingTranslator:
        def translate(self, *args, **kwargs):
            assert events == ['source']
            raise TranslationError('bad response')
    worker = TranslationWorker(OCR(), FailingTranslator(), 'Korean')
    worker.set_image(object())
    worker.source_ready.connect(lambda text: (events.append('source'), overlay.show_source(text)))
    worker.failed.connect(overlay.show_status)
    worker.run()
    assert overlay._source_view.toPlainText() == 'Hello world'
    assert 'bad response' in overlay._translation_view.toPlainText()
    overlay.close()


def test_settings_is_nonmodal_and_remembers_provider_drafts(monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from window_translation.config import AppSettings
    from window_translation.overlay import SettingsDialog
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(AppSettings())
    dialog.show()
    app.processEvents()
    assert not dialog.isModal()
    assert QApplication.activeModalWidget() is None
    dialog._api_key.setText('openai-test')
    dialog._provider.setCurrentIndex(dialog._provider.findData('anthropic'))
    assert dialog._endpoint.text() == 'https://api.anthropic.com/v1/messages'
    assert dialog._api_key.text() == ''
    dialog._api_key.setText('claude-test')
    dialog._model.setEditText('custom-claude-model')
    dialog._provider.setCurrentIndex(dialog._provider.findData('openai'))
    assert dialog._api_key.text() == 'openai-test'
    dialog._provider.setCurrentIndex(dialog._provider.findData('anthropic'))
    assert dialog._api_key.text() == 'claude-test'
    assert dialog._model.currentText() == 'custom-claude-model'
    dialog.close()


def test_hotkey_opens_selector_with_settings_visible(monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from PIL import Image
    import window_translation.app as module
    from window_translation.config import AppSettings
    from window_translation.ocr.tesseract import OCRResult
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module.GlobalHotkey, 'start', lambda self: True)
    monkeypatch.setattr(module, 'load_settings', lambda: AppSettings(provider='stub', history_enabled=False))
    monkeypatch.setattr(module, 'capture_region', lambda r: Image.new('RGB', (100, 100)))
    class OCR:
        def run(self, img):
            return OCRResult('Hello from browser', 'en')
    monkeypatch.setattr(module, 'build_ocr', lambda *a, **kw: OCR())
    controller = module.TranslatorApp(app)
    app.processEvents()
    assert controller._settings_dialog.isVisible()
    controller._hotkey.activated.emit()
    app.processEvents()
    selector = controller._selector
    assert selector.isVisible()
    assert QApplication.activeModalWidget() is None
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, pos=QPoint(120, 120))
    for _ in range(100):
        QTest.qWait(20)
        if controller._worker_thread is None and 'Hello from browser' in controller._overlay._translation_view.toPlainText():
            break
    assert 'Hello from browser' in controller._overlay._translation_view.toPlainText()
    assert controller._settings_dialog.isVisible()
    controller._settings_dialog.close()
    controller._overlay.close()
    controller._tray.hide()
    controller._hotkey.stop()
