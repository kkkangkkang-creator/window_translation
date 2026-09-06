"""Tesseract-based OCR wrapper with light image preprocessing."""

from __future__ import annotations

import logging
import re
import os
import shutil
import sys
from pathlib import Path
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


def resolve_tesseract(explicit: Optional[str] = None) -> Optional[Path]:
    """Prefer an explicit path, then the bundled engine, then system installs."""
    if explicit:
        path = Path(explicit.strip().strip('"'))
        if path.is_dir():
            path /= "tesseract.exe" if os.name == "nt" else "tesseract"
        return path if path.is_file() else None
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.extend([
            Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "tesseract" / "tesseract.exe",
            Path(sys.executable).parent / "tesseract" / "tesseract.exe",
        ])
    installed = shutil.which("tesseract")
    if installed:
        candidates.append(Path(installed))
    if os.name == "nt":
        candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe")
    return next((p for p in candidates if p.is_file()), None)


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
        import pytesseract

        executable = resolve_tesseract(self.tesseract_cmd)
        if executable is None:
            raise RuntimeError("OCR 엔진을 찾지 못했습니다. ZIP 전체를 압축 해제하거나 설정에서 tesseract.exe 경로를 지정해주세요.")
        pytesseract.pytesseract.tesseract_cmd = str(executable)
        # Use the matching language data, including in the portable EXE.
        data = executable.parent / "tessdata"
        self._data_dir = data if data.is_dir() else None

    def run(self, img: "Image") -> OCRResult:
        """Run OCR on ``img`` and return the cleaned text + detected lang."""
        import pytesseract

        self._configure_binary()
        prepared = preprocess_for_ocr(img)
        config = f"--psm {self.psm}"
        previous_data = os.environ.get("TESSDATA_PREFIX")
        if self._data_dir is not None:
            os.environ["TESSDATA_PREFIX"] = str(self._data_dir)
        try:
            raw = pytesseract.image_to_string(
                prepared, lang=self.languages, config=config, timeout=30
            )
        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract binary not found. Install Tesseract OCR and set "
                "`tesseract_cmd` in settings if it is not on PATH."
            ) from None
        finally:
            if previous_data is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = previous_data

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
