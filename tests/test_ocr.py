"""Tests for OCR text cleanup + heuristic language detection."""

from window_translation.ocr.tesseract import _clean_ocr_text, detect_language


def test_detect_language_japanese() -> None:
    assert detect_language("こんにちは") == "ja"


def test_detect_language_chinese() -> None:
    assert detect_language("你好世界") == "zh"


def test_detect_language_korean() -> None:
    assert detect_language("안녕하세요") == "ko"


def test_detect_language_english() -> None:
    assert detect_language("Hello there, traveller.") == "en"


def test_detect_language_unknown() -> None:
    assert detect_language("   ") == "unknown"
    assert detect_language("123 456") == "unknown"


def test_clean_ocr_text_collapses_whitespace_preserves_lines() -> None:
    raw = "  Hello   world  \n\n  Line  two  \n"
    assert _clean_ocr_text(raw) == "Hello world\nLine two"
