"""Settings dialog — edit provider, model, API key, hotkey, OCR languages."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings, load_api_key, save_api_key, save_settings
from ..config.secrets import clear_api_key


class SettingsDialog(QDialog):
    """Minimal settings editor backed by :class:`AppSettings`."""

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Window Translation — Settings")
        self.setModal(True)
        self._settings = settings

        # Provider / model
        self._provider = QComboBox()
        self._provider.addItems(["openai", "stub"])
        self._provider.setCurrentText(settings.provider)

        self._model = QLineEdit(settings.model)
        self._api_key = QLineEdit(load_api_key() or "")
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-...")

        self._show_key = QCheckBox("Show API key")
        self._show_key.toggled.connect(
            lambda on: self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )

        # OCR
        self._ocr_langs = QLineEdit(settings.ocr_languages)
        self._ocr_langs.setPlaceholderText("eng+jpn+chi_sim")
        self._tesseract_cmd = QLineEdit(settings.tesseract_cmd)
        self._tesseract_cmd.setPlaceholderText("(optional) path to tesseract binary")

        # UX
        self._target_lang = QLineEdit(settings.target_language)
        self._hotkey = QLineEdit(settings.hotkey)
        self._hotkey.setPlaceholderText("<ctrl>+<shift>+t")
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 48)
        self._font_size.setValue(settings.overlay_font_size)

        self._interval = QSpinBox()
        self._interval.setRange(300, 60000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(" ms")
        self._interval.setValue(settings.pin_mode_interval_ms)

        form = QFormLayout()
        form.addRow("Provider", self._provider)
        form.addRow("Model", self._model)
        form.addRow("API key", self._api_key)
        form.addRow("", self._show_key)
        form.addRow("OCR languages", self._ocr_langs)
        form.addRow("Tesseract path", self._tesseract_cmd)
        form.addRow("Target language", self._target_lang)
        form.addRow("Hotkey", self._hotkey)
        form.addRow("Overlay font size", self._font_size)
        form.addRow("Pin mode interval", self._interval)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    # ---------------------------------------------------- actions
    def accept(self) -> None:  # noqa: D401 — Qt override
        self._settings.provider = self._provider.currentText().strip() or "openai"
        self._settings.model = self._model.text().strip() or "gpt-4o-mini"
        self._settings.ocr_languages = self._ocr_langs.text().strip() or "eng"
        self._settings.tesseract_cmd = self._tesseract_cmd.text().strip()
        self._settings.target_language = self._target_lang.text().strip() or "Korean"
        self._settings.hotkey = self._hotkey.text().strip() or "<ctrl>+<shift>+t"
        self._settings.overlay_font_size = int(self._font_size.value())
        self._settings.pin_mode_interval_ms = int(self._interval.value())

        save_settings(self._settings)

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
