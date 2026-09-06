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
