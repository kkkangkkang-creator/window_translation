"""PaddleOCR 기반 OCR 백엔드.

PaddleOCR는 별도 시스템 바이너리가 필요 없이 Python 패키지(`paddleocr`,
`paddlepaddle`) 만 설치하면 동작하므로, 사용자가 Tesseract 설치를 건너뛰고
싶을 때 유용합니다. 한/일/중 정확도가 Tesseract보다 좋은 경우가 많습니다.

용량이 크기 때문에 의존성은 ``requirements-optional.txt`` 로 분리되어 있고,
설치돼 있지 않으면 :class:`PaddleOCREngine` 생성 시 친절한 ``RuntimeError`` 가
발생합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from .tesseract import OCRResult, _clean_ocr_text, detect_language

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image

log = logging.getLogger(__name__)


# PaddleOCR 의 언어 코드는 Tesseract 와 다릅니다.
# 우리는 다국어를 동시에 인식하기 어려우므로 사용자의 OCR 언어 설정 중
# 가장 적합한 *단일* 언어 모델을 선택합니다.
_TESS_TO_PADDLE = {
    "eng": "en",
    "kor": "korean",
    "jpn": "japan",
    "chi_sim": "ch",
    "chi_tra": "chinese_cht",
}

# 우선순위: CJK가 포함되어 있으면 CJK 모델이 영어도 인식하므로 CJK 우선.
_PRIORITY = ["kor", "jpn", "chi_sim", "chi_tra", "eng"]


def _pick_paddle_lang(tesseract_langs: str) -> str:
    """``"eng+jpn+chi_sim"`` 같은 Tesseract 언어 문자열에서 Paddle 언어 코드를 고른다."""
    parts = {p.strip().lower() for p in tesseract_langs.split("+") if p.strip()}
    for code in _PRIORITY:
        if code in parts:
            return _TESS_TO_PADDLE[code]
    # 직접 Paddle 코드를 줬을 수도 있으니 그대로 사용.
    if tesseract_langs.strip():
        return tesseract_langs.strip()
    return "en"


class PaddleOCREngine:
    """:class:`window_translation.ocr.TesseractOCR` 와 동일한 인터페이스.

    - ``run(image) -> OCRResult``
    - ``languages`` 속성은 Tesseract 표기법(``"eng+jpn+chi_sim"``)을 그대로
      받습니다. 내부에서 PaddleOCR 코드로 변환합니다.
    """

    # 한 번 만들면 재사용 (모델 로딩이 매우 느림). 언어가 바뀌면 다시 생성.
    _shared_reader = None
    _shared_lang: Optional[str] = None

    def __init__(self, languages: str = "eng+jpn+chi_sim", **_: object) -> None:
        self.languages = languages
        # 호환성을 위해 Tesseract 백엔드의 추가 인자(tesseract_cmd 등)는 무시합니다.

    @classmethod
    def is_available(cls) -> bool:
        """``paddleocr`` / ``paddlepaddle`` 설치 여부 확인."""
        try:
            import paddleocr  # noqa: F401
            import paddle  # noqa: F401
        except Exception:
            return False
        return True

    def _get_reader(self):
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception as exc:  # pragma: no cover — 환경 의존
            raise RuntimeError(
                "PaddleOCR가 설치되어 있지 않습니다. "
                "`pip install -r requirements-optional.txt` 로 설치하거나 "
                "설정에서 OCR 엔진을 Tesseract 로 변경하세요."
            ) from exc

        lang = _pick_paddle_lang(self.languages)
        cls = type(self)
        if cls._shared_reader is None or cls._shared_lang != lang:
            log.info("PaddleOCR reader 초기화 (lang=%s)", lang)
            cls._shared_reader = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            cls._shared_lang = lang
        return cls._shared_reader

    def run(self, img: "Image") -> OCRResult:
        import numpy as np  # paddle 설치 시 함께 들어옴

        reader = self._get_reader()
        # PaddleOCR 는 numpy ndarray (RGB) 를 받습니다.
        arr = np.array(img.convert("RGB"))
        try:
            raw = reader.ocr(arr, cls=True)
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR 실행 중 오류가 발생했습니다: {exc}") from exc

        # raw 형태: [[ [box, (text, conf)], ... ]]  (버전에 따라 약간 다름)
        lines = []
        if raw:
            page = raw[0] if raw and isinstance(raw[0], list) else raw
            for item in page or []:
                try:
                    # item == [box, (text, conf)] 또는 dict
                    if isinstance(item, dict):
                        text = str(item.get("text", "")).strip()
                    else:
                        text = str(item[1][0]).strip()
                except Exception:
                    continue
                if text:
                    lines.append(text)

        text = _clean_ocr_text("\n".join(lines))
        return OCRResult(text=text, detected_language=detect_language(text))


__all__ = ["PaddleOCREngine", "_pick_paddle_lang"]
