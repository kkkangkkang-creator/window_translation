"""Tesseract-based OCR wrapper with light image preprocessing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image

log = logging.getLogger(__name__)

# Rough unicode-range based language detection. This is a heuristic fallback
# used to pick the target language when the user hasn't configured one;
# full detection can be delegated to the translation model if desired.
_RE_JAPANESE = re.compile(r"[\u3040-\u30ff]")  # hiragana + katakana
_RE_CHINESE = re.compile(r"[\u4e00-\u9fff]")   # CJK unified ideographs
_RE_HANGUL = re.compile(r"[\uac00-\ud7af]")    # Korean


def detect_language(text: str) -> str:
    """Return a short language tag for ``text``: ja / zh / ko / en / unknown."""
    if not text or not text.strip():
        return "unknown"
    if _RE_JAPANESE.search(text):
        return "ja"
    if _RE_HANGUL.search(text):
        return "ko"
    if _RE_CHINESE.search(text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return "unknown"


def preprocess_for_ocr(img: "Image", upscale: float = 2.0) -> "Image":
    """Improve OCR legibility: grayscale + optional upscale + autocontrast.

    Kept intentionally simple — aggressive binarisation hurts as often as it
    helps on game/chat UI. A future iteration can pick a strategy based on
    measured contrast.
    """
    from PIL import Image as PILImage
    from PIL import ImageOps

    gray = img.convert("L")
    if upscale and upscale != 1.0:
        gray = gray.resize(
            (int(gray.width * upscale), int(gray.height * upscale)),
            PILImage.Resampling.LANCZOS,
        )
    gray = ImageOps.autocontrast(gray, cutoff=1)
    return gray


@dataclass
class OCRResult:
    """Outcome of a single OCR call."""

    text: str
    detected_language: str

    def is_empty(self) -> bool:
        return not self.text.strip()


class TesseractOCR:
    """Thin wrapper around :mod:`pytesseract`.

    Parameters
    ----------
    languages:
        Tesseract language codes, joined with ``+``. Examples:
        ``"eng"``, ``"eng+jpn+chi_sim"``.
    tesseract_cmd:
        Optional explicit path to the ``tesseract`` executable. Useful on
        Windows where Tesseract is not usually on ``PATH``.
    psm:
        Page segmentation mode passed to Tesseract. ``6`` (assume a single
        uniform block of text) works well for most capture regions.
    """

    def __init__(
        self,
        languages: str = "eng+jpn+chi_sim",
        tesseract_cmd: Optional[str] = None,
        psm: int = 6,
    ) -> None:
        self.languages = languages
        self.tesseract_cmd = tesseract_cmd or None
        self.psm = psm

    def _configure_binary(self) -> None:
        if not self.tesseract_cmd:
            return
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def run(self, img: "Image") -> OCRResult:
        """Run OCR on ``img`` and return the cleaned text + detected lang."""
        import pytesseract

        self._configure_binary()
        prepared = preprocess_for_ocr(img)
        config = f"--psm {self.psm}"
        try:
            raw = pytesseract.image_to_string(
                prepared, lang=self.languages, config=config
            )
        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract binary not found. Install Tesseract OCR and set "
                "`tesseract_cmd` in settings if it is not on PATH."
            ) from None

        text = _clean_ocr_text(raw)
        return OCRResult(text=text, detected_language=detect_language(text))


def _clean_ocr_text(text: str) -> str:
    """Normalise whitespace and drop obvious OCR noise."""
    # Collapse runs of whitespace but preserve line breaks, which often carry
    # meaning in subtitles / chat windows.
    lines = []
    for line in text.splitlines():
        stripped = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


__all__ = [
    "TesseractOCR",
    "OCRResult",
    "detect_language",
    "preprocess_for_ocr",
]
