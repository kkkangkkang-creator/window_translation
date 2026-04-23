"""OCR engine wrappers."""

from .tesseract import TesseractOCR, OCRResult, preprocess_for_ocr


def build_ocr(engine: str, *, languages: str, tesseract_cmd: str = ""):
    """설정에서 선택한 ``engine`` 에 맞는 OCR 객체를 만들어 돌려준다.

    ``engine`` 은 ``"tesseract"`` 또는 ``"paddleocr"`` 이며, 알 수 없는 값은
    안전하게 Tesseract로 폴백한다.
    """
    name = (engine or "tesseract").strip().lower()
    if name in ("paddle", "paddleocr"):
        from .paddleocr_backend import PaddleOCREngine

        return PaddleOCREngine(languages=languages)
    return TesseractOCR(languages=languages, tesseract_cmd=tesseract_cmd or None)


__all__ = ["TesseractOCR", "OCRResult", "preprocess_for_ocr", "build_ocr"]
