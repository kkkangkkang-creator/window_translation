"""Window capture, snapshot identity, layout and library regression tests."""
import sqlite3
import sys
from types import SimpleNamespace
from PIL import Image
from window_translation.capture.screen import Region
from window_translation.capture.window import relative_crop, crop_region, WindowCapture
from window_translation.ocr.tesseract import OCRResult, OCRBlock, blocks_from_data
from window_translation.history import HistoryStore
from window_translation.translate.factory import build_translator
from window_translation.config import AppSettings


def test_relative_region_follows_move_and_resize():
    crop = relative_crop(Region(120, 140, 200, 100), Region(100, 100, 400, 200))
    assert crop_region(Region(-800, 50, 800, 400), crop) == Region(-760, 130, 400, 200)


def test_invalid_crop_does_not_capture_another_app():
    import pytest
    with pytest.raises(ValueError):
        relative_crop(Region(900, 900, 20, 20), Region(0, 0, 100, 100))


def test_word_coordinates_are_scaled_back_and_grouped():
    data = dict(text=['Hello', 'world', 'Next'], conf=[90, 90, 90],
        page_num=[1]*3, block_num=[1, 1, 2], par_num=[1]*3, line_num=[1]*3,
        left=[20, 100, 40], top=[40, 40, 200], width=[60, 80, 100], height=[30]*3)
    blocks = blocks_from_data(data)
    assert blocks == [OCRBlock('Hello world', 10, 20, 80, 15), OCRBlock('Next', 20, 100, 50, 15)]


def test_wgc_copies_native_buffer_and_uses_exact_handle(monkeypatch):
    import numpy as np
    class Native:
        def __init__(self, **kwargs):
            assert kwargs['window_hwnd'] == 123456
        def event(self, handler):
            setattr(self, handler.__name__, handler)
            return handler
        def start_free_threaded(self):
            return SimpleNamespace(stop=lambda: None)
    monkeypatch.setitem(sys.modules, 'windows_capture', SimpleNamespace(WindowsCapture=Native))
    target = SimpleNamespace(hwnd=123456, valid=lambda: True, minimized=lambda: False)
    capture = WindowCapture(target)
    buf = np.zeros((4, 4, 4), dtype='uint8'); buf[:, :, 2] = 255
    capture.capture.on_frame_arrived(SimpleNamespace(frame_buffer=buf), SimpleNamespace(stop=lambda: None))
    buf[:] = 0
    assert capture.image().getpixel((0, 0)) == (255, 0, 0)
    assert capture.image((.5, .5, .5, .5)).size == (2, 2)
    capture.stop()


def test_old_database_migrates_without_deleting_history(tmp_path):
    from window_translation.history.store import SCHEMA
    path = tmp_path/'old.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO translations(created_at,source_hash,source_text,translated_text) VALUES(1,'hash','Hello','안녕')")
    store = HistoryStore(path)
    assert store.all()[0].project == '기본'
    assert store.count() == 1


def test_project_and_prompt_changes_do_not_reuse_wrong_cache(tmp_path):
    store = HistoryStore(tmp_path/'history.sqlite')
    a = AppSettings(provider='stub', library_project='게임 A')
    first = build_translator(a, history_store=store)
    first.translate('Hello')
    first.translate('Hello')
    assert store.count() == 1
    a.library_project = '만화 B'
    build_translator(a, history_store=store).translate('Hello')
    a.system_prompt = 'A different translation style'
    build_translator(a, history_store=store).translate('Hello')
    assert store.count() == 3
    assert len(store.recent(project='게임 A')) == 1


def test_prefill_is_opt_in_and_sent_as_assistant_message():
    from window_translation.translate.openai_client import OpenAITranslator
    calls = []
    class Session:
        def post(self, *args, **kwargs):
            import json
            calls.append(json.loads(kwargs['data']))
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {'choices':[{'message':{'content':'번역'}}]})
    t = OpenAITranslator('key', session=Session())
    t._assistant_prefill = 'Translation:\n'
    assert t.translate('Hello') == '번역'
    assert calls[0]['messages'][-1] == {'role':'assistant', 'content':'Translation:\n'}


def test_unsupported_prefill_fails_before_request():
    import pytest
    from window_translation.translate.base import TranslationError
    with pytest.raises(TranslationError, match='프리필'):
        build_translator(AppSettings(provider='anthropic', model='claude-opus-4-6', assistant_prefill='Sure'), api_key='unused')


def test_worker_reuses_identical_text_and_drops_outdated_layout():
    from window_translation.app import TranslationWorker
    calls, layouts = [], []
    class OCR:
        def run(self, image):
            text = 'old' if image.getpixel((0,0)) == (255,255,255) else 'new'
            return OCRResult(text, 'en', [OCRBlock(text, 0, 0, 50, 20)])
    class Translator:
        def translate(self, text, **kwargs):
            calls.append(text); return '번역'
    worker = TranslationWorker(OCR(), Translator(), 'Korean')
    worker.inline = True
    worker.set_image(Image.new('RGB', (50,20), 'white'))
    worker.layout_ready.connect(lambda blocks, size: layouts.append(blocks))
    worker.run(); worker.run()
    assert calls == ['old']
    assert layouts[-1][0][1] == '번역'
    worker.validate_image = lambda: Image.new('RGB', (50,20), 'black')
    worker.run()
    assert layouts[-1] == []


def test_blank_page_clears_layout_without_stopping_worker():
    from window_translation.app import TranslationWorker
    worker = TranslationWorker(SimpleNamespace(run=lambda image: OCRResult('', 'unknown')), None, 'Korean')
    worker.set_image(Image.new('RGB', (10,10)))
    results, failures = [], []
    worker.finished.connect(lambda a,b: results.append((a,b)))
    worker.failed.connect(failures.append)
    worker.run()
    assert results == [('', '')] and not failures


def test_inline_window_is_click_through_and_does_not_take_focus(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from window_translation.overlay.inline import InlineOverlay
    app = QApplication.instance() or QApplication([])
    overlay = InlineOverlay(AppSettings())
    overlay.present([(OCRBlock('hello', 0,0,100,30), '안녕하세요')], (100,30), Region(0,0,200,60))
    overlay.show(); app.processEvents()
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert not overlay.grab().isNull()
    overlay.close()
