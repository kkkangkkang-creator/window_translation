"""OCR engine wrappers."""

from .tesseract import TesseractOCR, OCRResult, preprocess_for_ocr

__all__ = ["TesseractOCR", "OCRResult", "preprocess_for_ocr"]
