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


class SettingsDialog(QDialog):
    """Tabbed settings editor backed by :class:`AppSettings`."""

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Window Translation — Settings")
        self.setModal(True)
        self._settings = settings

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_overlay_tab(), "Overlay")
        tabs.addTab(self._build_prompt_tab(), "Prompt")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)
        self.resize(520, 520)

    # ------------------------------------------------------------------ tabs
    def _build_general_tab(self) -> QWidget:
        s = self._settings

        self._provider = QComboBox()
        self._provider.addItems(["openai", "stub"])
        self._provider.setCurrentText(s.provider)

        self._model = QLineEdit(s.model)

        self._api_key = QLineEdit(load_api_key() or "")
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-...")
        self._show_key = QCheckBox("Show API key")
        self._show_key.toggled.connect(
            lambda on: self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )

        self._ocr_langs = QLineEdit(s.ocr_languages)
        self._ocr_langs.setPlaceholderText("eng+jpn+chi_sim")
        self._tesseract_cmd = QLineEdit(s.tesseract_cmd)
        self._tesseract_cmd.setPlaceholderText("(optional) path to tesseract binary")

        self._target_lang = QLineEdit(s.target_language)
        self._hotkey = QLineEdit(s.hotkey)
        self._hotkey.setPlaceholderText("<ctrl>+<shift>+t")

        self._interval = QSpinBox()
        self._interval.setRange(300, 60000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(" ms")
        self._interval.setValue(s.pin_mode_interval_ms)

        form = QFormLayout()
        form.addRow("Provider", self._provider)
        form.addRow("Model", self._model)
        form.addRow("API key", self._api_key)
        form.addRow("", self._show_key)
        form.addRow("OCR languages", self._ocr_langs)
        form.addRow("Tesseract path", self._tesseract_cmd)
        form.addRow("Target language", self._target_lang)
        form.addRow("Hotkey", self._hotkey)
        form.addRow("Pin mode interval", self._interval)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

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
        form.addRow("Font family", self._font_family)
        form.addRow("Font size", self._font_size)
        form.addRow("Line spacing", self._line_spacing)
        form.addRow("Window opacity", self._opacity)

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

        reset_btn = QPushButton("Reset to default")
        reset_btn.clicked.connect(
            lambda: self._prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        )
        clear_btn = QPushButton("Use built-in default (leave empty)")
        clear_btn.clicked.connect(self._prompt_edit.clear)

        hint = QLineEdit(
            "Placeholders available: {target_language}, {source_language}"
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

    # ---------------------------------------------------- actions
    def accept(self) -> None:  # noqa: D401 — Qt override
        s = self._settings
        s.provider = self._provider.currentText().strip() or "openai"
        s.model = self._model.text().strip() or "gpt-4o-mini"
        s.ocr_languages = self._ocr_langs.text().strip() or "eng"
        s.tesseract_cmd = self._tesseract_cmd.text().strip()
        s.target_language = self._target_lang.text().strip() or "Korean"
        s.hotkey = self._hotkey.text().strip() or "<ctrl>+<shift>+t"
        s.pin_mode_interval_ms = int(self._interval.value())

        s.overlay_font_family = self._font_family.currentFont().family()
        s.overlay_font_size = int(self._font_size.value())
        s.overlay_line_spacing = int(self._line_spacing.value())
        s.overlay_opacity = max(0.3, min(1.0, self._opacity.value() / 100.0))

        s.system_prompt = self._prompt_edit.toPlainText().strip()

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
