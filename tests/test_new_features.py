"""txt 내보내기와 PaddleOCR 백엔드 인터페이스 테스트."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from window_translation.history import HistoryStore, export_txt
from window_translation.ocr import build_ocr
from window_translation.ocr.paddleocr_backend import PaddleOCREngine, _pick_paddle_lang
from window_translation.ocr.tesseract import TesseractOCR


# -------------------------------------------------------- txt export
def test_export_txt_format(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.sqlite3")
    store.add("Hello world", "안녕 세계", target_language="Korean")
    store.add("foo\nbar", "푸\n바", target_language="Korean")
    out = tmp_path / "hist.txt"
    n = export_txt(store.all(), out)
    assert n == 2
    content = out.read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln]
    assert len(lines) == 2
    # 형식: [YYYY-MM-DD HH:MM:SS] 원문 → 번역
    pat = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] .+ → .+$")
    for ln in lines:
        assert pat.match(ln), ln
    # 줄바꿈은 ⏎ 로 치환
    assert "⏎" in content


def test_export_txt_empty(tmp_path: Path) -> None:
    out = tmp_path / "empty.txt"
    n = export_txt([], out)
    assert n == 0
    assert out.read_text(encoding="utf-8") == ""


# -------------------------------------------------------- paddle helpers
def test_pick_paddle_lang_priority() -> None:
    # CJK 우선
    assert _pick_paddle_lang("eng+jpn+chi_sim") == "japan"
    assert _pick_paddle_lang("eng+kor") == "korean"
    assert _pick_paddle_lang("eng") == "en"
    assert _pick_paddle_lang("chi_sim") == "ch"
    assert _pick_paddle_lang("chi_tra") == "chinese_cht"


def test_pick_paddle_lang_fallback() -> None:
    # 빈 입력은 영어로 폴백
    assert _pick_paddle_lang("") == "en"
    # 알 수 없는 입력은 그대로 전달
    assert _pick_paddle_lang("custom_lang") == "custom_lang"


# -------------------------------------------------------- factory
def test_build_ocr_returns_tesseract_by_default() -> None:
    ocr = build_ocr("tesseract", languages="eng")
    assert isinstance(ocr, TesseractOCR)


def test_build_ocr_returns_paddle_for_paddleocr() -> None:
    ocr = build_ocr("paddleocr", languages="eng+kor")
    assert isinstance(ocr, PaddleOCREngine)


def test_build_ocr_unknown_falls_back_to_tesseract() -> None:
    ocr = build_ocr("nonsense", languages="eng")
    assert isinstance(ocr, TesseractOCR)


# -------------------------------------------------------- paddle interface
def test_paddleocr_engine_has_run_method() -> None:
    """OCR 엔진은 같은 인터페이스(`run(image) -> OCRResult`)를 제공해야 한다."""
    eng = PaddleOCREngine(languages="eng")
    assert hasattr(eng, "run")
    assert callable(eng.run)
    assert eng.languages == "eng"


def test_paddleocr_engine_run_raises_when_not_installed(monkeypatch) -> None:
    """paddleocr 미설치 시 사용자에게 친절한 RuntimeError 가 나야 한다."""
    if PaddleOCREngine.is_available():
        pytest.skip("paddleocr가 실제로 설치되어 있어 미설치 시나리오를 검증할 수 없음")
    eng = PaddleOCREngine(languages="eng")
    # 가짜 이미지(불필요): 그 전에 reader 가져오는 단계에서 실패해야 함.
    with pytest.raises(RuntimeError) as excinfo:
        eng._get_reader()
    assert "PaddleOCR" in str(excinfo.value)
