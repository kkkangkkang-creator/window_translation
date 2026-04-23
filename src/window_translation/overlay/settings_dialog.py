"""Settings dialog — edit provider, model, API key, hotkey, OCR languages."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings, load_api_key, save_api_key, save_settings
from ..config.secrets import clear_api_key
from ..translate.base import DEFAULT_SYSTEM_PROMPT
from ..translate.openai_client import ENDPOINT_PRESETS
from .theme import THEME_NAMES


class SettingsDialog(QDialog):
    """Tabbed settings editor backed by :class:`AppSettings`."""

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Window Translation — 설정")
        self.setModal(True)
        self._settings = settings

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "일반")
        tabs.addTab(self._build_overlay_tab(), "오버레이")
        tabs.addTab(self._build_prompt_tab(), "프롬프트")
        tabs.addTab(self._build_history_tab(), "히스토리")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)
        self.resize(560, 560)

    # ------------------------------------------------------------------ tabs
    def _build_general_tab(self) -> QWidget:
        s = self._settings

        # Provider preset dropdown — populated from ENDPOINT_PRESETS, plus "stub".
        self._provider = QComboBox()
        providers = list(ENDPOINT_PRESETS.keys()) + ["stub"]
        self._provider.addItems(providers)
        if s.provider in providers:
            self._provider.setCurrentText(s.provider)
        else:
            # Unknown provider string — treat as custom so the user can see
            # their endpoint.
            self._provider.setCurrentText("custom")
        self._provider.currentTextChanged.connect(self._on_provider_changed)

        self._model = QLineEdit(s.model)

        # Endpoint URL — auto-filled from preset when empty, editable.
        self._endpoint = QLineEdit(s.endpoint)
        self._endpoint.setPlaceholderText(
            ENDPOINT_PRESETS.get(self._provider.currentText(), "")
            or "https://your-proxy.example.com/v1/chat/completions"
        )

        self._api_key = QLineEdit(load_api_key() or "")
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-...")
        self._show_key = QCheckBox("Show API key")
        self._show_key.toggled.connect(
            lambda on: self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )

        self._ocr_engine = QComboBox()
        self._ocr_engine.addItem("Tesseract (별도 설치 필요)", "tesseract")
        self._ocr_engine.addItem("PaddleOCR (Python 패키지)", "paddleocr")
        idx = self._ocr_engine.findData(s.ocr_engine or "tesseract")
        self._ocr_engine.setCurrentIndex(idx if idx >= 0 else 0)

        self._ocr_langs = QLineEdit(s.ocr_languages)
        self._ocr_langs.setPlaceholderText("eng+jpn+chi_sim")
        self._tesseract_cmd = QLineEdit(s.tesseract_cmd)
        self._tesseract_cmd.setPlaceholderText("(선택) tesseract 실행파일 경로")

        self._target_lang = QLineEdit(s.target_language)
        self._hotkey = QLineEdit(s.hotkey)
        self._hotkey.setPlaceholderText("<ctrl>+<shift>+t")

        self._theme = QComboBox()
        self._theme.addItems(list(THEME_NAMES))
        self._theme.setCurrentText(s.theme if s.theme in THEME_NAMES else THEME_NAMES[0])

        self._interval = QSpinBox()
        self._interval.setRange(300, 60000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(" ms")
        self._interval.setValue(s.pin_mode_interval_ms)

        form = QFormLayout()
        form.addRow("번역 제공자", self._provider)
        form.addRow("Endpoint URL", self._endpoint)
        form.addRow("모델", self._model)
        form.addRow("API 키", self._api_key)
        form.addRow("", self._show_key)
        form.addRow("OCR 엔진", self._ocr_engine)
        form.addRow("OCR 언어", self._ocr_langs)
        form.addRow("Tesseract 경로", self._tesseract_cmd)
        form.addRow("번역 대상 언어", self._target_lang)
        form.addRow("테마", self._theme)
        form.addRow("단축키", self._hotkey)
        form.addRow("핀 모드 주기", self._interval)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _on_provider_changed(self, provider: str) -> None:
        """When the user switches provider, update endpoint helper text.

        If the endpoint field is empty or matches a known preset, we also
        overwrite it with the new preset so users aren't stuck with a stale
        URL. Their custom URL is preserved if it doesn't match any preset.
        """
        preset = ENDPOINT_PRESETS.get(provider, "")
        self._endpoint.setPlaceholderText(
            preset or "https://your-proxy.example.com/v1/chat/completions"
        )
        current = self._endpoint.text().strip()
        if not current or current in ENDPOINT_PRESETS.values():
            self._endpoint.setText(preset)

    def _build_overlay_tab(self) -> QWidget:
        s = self._settings

        self._font_family = QFontComboBox()
        if s.overlay_font_family:
            self._font_family.setCurrentText(s.overlay_font_family)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 48)
        self._font_size.setSuffix(" pt")
        self._font_size.setValue(s.overlay_font_size)

        self._line_spacing = QSpinBox()
        self._line_spacing.setRange(100, 300)
        self._line_spacing.setSingleStep(5)
        self._line_spacing.setSuffix(" %")
        self._line_spacing.setValue(s.overlay_line_spacing)

        self._opacity = QSpinBox()
        self._opacity.setRange(30, 100)
        self._opacity.setSuffix(" %")
        self._opacity.setValue(int(round(s.overlay_opacity * 100)))

        form = QFormLayout()
        form.addRow("글꼴", self._font_family)
        form.addRow("글자 크기", self._font_size)
        form.addRow("줄 간격", self._line_spacing)
        form.addRow("창 투명도", self._opacity)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_prompt_tab(self) -> QWidget:
        s = self._settings

        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setPlaceholderText(DEFAULT_SYSTEM_PROMPT)
        # If a custom prompt is set, show it; otherwise leave the editor empty
        # (placeholder shows the default so the user can see what's active).
        if s.system_prompt:
            self._prompt_edit.setPlainText(s.system_prompt)

        reset_btn = QPushButton("기본값으로 되돌리기")
        reset_btn.clicked.connect(
            lambda: self._prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        )
        clear_btn = QPushButton("내장 기본 사용 (비우기)")
        clear_btn.clicked.connect(self._prompt_edit.clear)

        hint = QLineEdit(
            "사용 가능한 변수: {target_language}, {source_language}"
        )
        hint.setReadOnly(True)
        hint.setFrame(False)
        hint.setStyleSheet("color: #888;")

        btn_row = QHBoxLayout()
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(hint)
        layout.addWidget(self._prompt_edit, 1)
        layout.addLayout(btn_row)
        return page

    def _build_history_tab(self) -> QWidget:
        s = self._settings

        self._history_enabled = QCheckBox("번역 히스토리 / 캐시 사용")
        self._history_enabled.setChecked(bool(s.history_enabled))

        self._recent_context = QSpinBox()
        self._recent_context.setRange(0, 10)
        self._recent_context.setValue(int(s.history_recent_context))
        self._recent_context.setToolTip(
            "최근 번역 N건을 few-shot 예시로 함께 보내 용어/말투 일관성을 높입니다. 0이면 끔."
        )

        hint = QLineEdit(
            "동일한 원문은 캐시에서 즉시 반환됩니다 (API 비용 0). "
            "최근 예시 > 0 이면 일관성은 좋아지지만 토큰 비용이 늘어납니다."
        )
        hint.setReadOnly(True)
        hint.setFrame(False)
        hint.setStyleSheet("color: #888;")

        form = QFormLayout()
        form.addRow("", self._history_enabled)
        form.addRow("최근 예시 개수", self._recent_context)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------- actions
    def accept(self) -> None:  # noqa: D401 — Qt override
        s = self._settings
        s.provider = self._provider.currentText().strip() or "openai"
        s.endpoint = self._endpoint.text().strip()
        s.model = self._model.text().strip() or "gpt-4o-mini"
        s.ocr_engine = self._ocr_engine.currentData() or "tesseract"
        s.ocr_languages = self._ocr_langs.text().strip() or "eng"
        s.tesseract_cmd = self._tesseract_cmd.text().strip()
        s.target_language = self._target_lang.text().strip() or "Korean"
        s.hotkey = self._hotkey.text().strip() or "<ctrl>+<shift>+t"
        s.theme = self._theme.currentText().strip() or "light"
        s.pin_mode_interval_ms = int(self._interval.value())

        s.overlay_font_family = self._font_family.currentFont().family()
        s.overlay_font_size = int(self._font_size.value())
        s.overlay_line_spacing = int(self._line_spacing.value())
        s.overlay_opacity = max(0.3, min(1.0, self._opacity.value() / 100.0))

        s.system_prompt = self._prompt_edit.toPlainText().strip()

        s.history_enabled = bool(self._history_enabled.isChecked())
        s.history_recent_context = int(self._recent_context.value())

        save_settings(s)

        key = self._api_key.text().strip()
        if key:
            save_api_key(key)
        else:
            clear_api_key()
        super().accept()

    @property
    def settings(self) -> AppSettings:
        return self._settings


__all__ = ["SettingsDialog"]
