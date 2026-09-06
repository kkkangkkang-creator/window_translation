"""Settings dialog — edit provider, model, API key, hotkey, OCR languages."""

from __future__ import annotations

from typing import Optional
import copy

from PySide6.QtCore import QThread, Signal, Slot, Qt

from PySide6.QtWidgets import (
    QMessageBox,
    QLabel,
    QScrollArea,
    QCompleter,
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
from ..translate.providers import PROVIDER_LABELS, list_models, api_endpoint
from ..translate import build_translator, TranslationError
from ..config.secrets import load_provider_key, save_provider_keys


class ConnectionTask(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, settings, key, mode, parent=None):
        super().__init__(parent)
        self.settings, self.key, self.mode = settings, key, mode

    def run(self):
        try:
            if self.mode == 'models':
                result = list_models(self.settings.provider, self.settings.endpoint, self.key)
            else:
                self.settings.history_enabled = False
                translator = build_translator(self.settings, api_key=self.key)
                result = translator.translate('Hello.', target_language='Korean', source_language='en')
            self.result.emit(result)
        except TranslationError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit('연결 확인 중 오류가 발생했습니다. 주소·키·모델을 확인해주세요.')



class SettingsDialog(QDialog):
    """Tabbed settings editor backed by :class:`AppSettings`."""

    settings_applied = Signal()
    capture_requested = Signal()

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Window Translation — 설정")
        self.setModal(False)
        self._settings = settings
        self._profiles = copy.deepcopy(settings.provider_profiles)
        self._keys = {}
        self._active_provider = settings.provider
        self._connection_thread = None
        self._request_snapshot = None
        self._last_auto_check = None


        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "일반")
        tabs.addTab(self._build_overlay_tab(), "오버레이")
        tabs.addTab(self._build_prompt_tab(), "프롬프트")
        tabs.addTab(self._build_history_tab(), "히스토리")

        check = QPushButton("OCR 준비 상태 확인")
        check.clicked.connect(self._check_ocr)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Apply
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("저장 후 닫기")
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("적용")
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        capture = QPushButton("영역 선택해서 번역")
        capture.clicked.connect(self._capture_from_settings)
        root.addWidget(capture)
        root.addWidget(check)
        root.addWidget(buttons)
        self.resize(660, min(740, self.screen().availableGeometry().height() - 40))

    # ------------------------------------------------------------------ tabs
    def _build_general_tab(self) -> QWidget:
        s = self._settings
        self._provider = QComboBox()
        for provider, label in PROVIDER_LABELS.items():
            self._provider.addItem(label, provider)
        idx = self._provider.findData(s.provider)
        self._provider.setCurrentIndex(max(0, idx))
        self._active_provider = self._provider.currentData()
        self._endpoint = QLineEdit(s.endpoint or ENDPOINT_PRESETS.get(self._active_provider, ''))
        self._endpoint.setPlaceholderText('API 기본 주소 또는 전체 주소')
        reset = QPushButton('기본 주소')
        reset.clicked.connect(lambda: self._endpoint.setText(ENDPOINT_PRESETS.get(self._provider.currentData(), '')))
        endpoint_row = QHBoxLayout()
        endpoint_row.addWidget(self._endpoint)
        endpoint_row.addWidget(reset)
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._model.lineEdit().setPlaceholderText('모델 목록에서 선택하거나 직접 입력')
        self._model.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._model.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self._model.setEditText(s.model)
        self._model.setMaxVisibleItems(16)
        self._api_key = QLineEdit(load_provider_key(self._active_provider) or '')
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText('선택한 제공자의 API 키를 붙여넣으세요')
        self._show_key = QCheckBox('API 키 보기')
        self._show_key.toggled.connect(lambda on: self._api_key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        self._connect_btn = QPushButton('연결 확인 · 모델 불러오기')
        self._connect_btn.clicked.connect(lambda: self._start_connection('models'))
        self._test_btn = QPushButton('번역 테스트 · 소액 요청')
        self._test_btn.setToolTip('Hello. 한 문장을 실제로 번역합니다. 제공자에 따라 소액의 사용료가 발생할 수 있습니다.')
        self._test_btn.clicked.connect(lambda: self._start_connection('translation'))
        connect_row = QHBoxLayout()
        connect_row.addWidget(self._connect_btn)
        connect_row.addWidget(self._test_btn)
        self._connection_status = QLabel('키 입력 후 연결 확인 → 모델 선택 → 적용. 목록 조회와 실제 번역 테스트는 별개입니다.')
        self._connection_status.setWordWrap(True)
        self._api_key.editingFinished.connect(self._auto_models)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        self._ocr_engine = QComboBox()
        self._ocr_engine.addItem('Tesseract (배포 ZIP에 포함)', 'tesseract')
        self._ocr_engine.addItem('PaddleOCR (소스 실행용 선택 설치)', 'paddleocr')
        self._ocr_engine.setCurrentIndex(max(0, self._ocr_engine.findData(s.ocr_engine)))
        self._ocr_langs = QLineEdit(s.ocr_languages)
        self._tesseract_cmd = QLineEdit(s.tesseract_cmd)
        self._tesseract_cmd.setPlaceholderText('보통 비워둡니다 · 포함된 OCR 자동 사용')
        self._target_lang = QLineEdit(s.target_language)
        self._hotkey = QLineEdit(s.hotkey)
        self._hotkey.setToolTip('기본 Ctrl+Alt+F9. 변경 후 적용을 누르세요.')
        self._theme = QComboBox()
        self._theme.addItems(list(THEME_NAMES))
        self._theme.setCurrentText(s.theme)
        self._interval = QSpinBox()
        self._interval.setRange(300, 60000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(' ms')
        self._interval.setValue(s.pin_mode_interval_ms)
        form = QFormLayout()
        form.addRow('번역 제공자', self._provider)
        form.addRow('API 주소', endpoint_row)
        form.addRow('API 키', self._api_key)
        form.addRow('', self._show_key)
        form.addRow('', connect_row)
        form.addRow('', self._connection_status)
        form.addRow('모델 · 직접 입력 가능', self._model)
        form.addRow('OCR 엔진', self._ocr_engine)
        form.addRow('OCR 언어', self._ocr_langs)
        form.addRow('Tesseract 경로', self._tesseract_cmd)
        form.addRow('번역 대상 언어', self._target_lang)
        form.addRow('테마', self._theme)
        form.addRow('단축키 · Ctrl+Alt+F9', self._hotkey)
        form.addRow('자동 확인 주기', self._interval)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _capture_from_settings(self):
        if self.apply_settings():
            self.capture_requested.emit()

    def _remember_provider(self):
        self._profiles[self._active_provider] = {
            'endpoint': self._endpoint.text().strip(),
            'model': self._model.currentText().strip(),
        }
        self._keys[self._active_provider] = self._api_key.text().strip()

    def _on_provider_changed(self, _index):
        self._remember_provider()
        provider = self._provider.currentData()
        self._active_provider = provider
        profile = self._profiles.get(provider, {})
        self._endpoint.setText(profile.get('endpoint', ENDPOINT_PRESETS.get(provider, '')))
        self._model.clear()
        self._model.setEditText(profile.get('model', ''))
        self._api_key.setText(self._keys.get(provider, load_provider_key(provider) or ''))
        self._connection_status.setText('제공자가 바뀌었습니다. 연결 확인으로 모델 목록을 불러오세요.')
        self._last_auto_check = None

    def _fingerprint(self):
        return (self._provider.currentData(), self._endpoint.text().strip(), self._api_key.text().strip())

    def _auto_models(self):
        fingerprint = self._fingerprint()
        if fingerprint[2] and fingerprint != self._last_auto_check:
            self._start_connection('models')

    def _start_connection(self, mode):
        if self._connection_thread is not None:
            return
        settings = copy.deepcopy(self._settings)
        settings.provider = self._provider.currentData()
        settings.endpoint = self._endpoint.text().strip()
        settings.model = self._model.currentText().strip()
        if mode == 'translation' and not settings.model and settings.provider != 'stub':
            self._connection_status.setText('먼저 모델을 선택하거나 직접 입력해주세요.')
            return
        self._last_auto_check = self._fingerprint()
        self._request_snapshot = (self._fingerprint(), mode, settings.model)
        self._connect_btn.setEnabled(False)
        self._test_btn.setEnabled(False)
        self._connection_status.setText('모델 목록을 불러오는 중…' if mode == 'models' else '선택한 모델로 짧은 번역을 테스트하는 중…')
        task = ConnectionTask(settings, self._api_key.text().strip(), mode, self)
        self._connection_thread = task
        task.result.connect(self._connection_result)
        task.failed.connect(self._connection_failed)
        task.finished.connect(self._connection_finished)
        task.start()

    def _request_is_current(self):
        fingerprint, mode, model = self._request_snapshot
        return fingerprint == self._fingerprint() and (mode == 'models' or model == self._model.currentText().strip())

    @Slot(object)
    def _connection_result(self, result):
        if not self._request_is_current():
            self._connection_status.setText('입력값이 바뀌었습니다. 다시 연결 확인을 눌러주세요.')
            return
        if self._request_snapshot[1] == 'models':
            current = self._model.currentText().strip()
            self._model.clear()
            self._model.addItems(result)
            if current:
                self._model.setEditText(current)
            self._connection_status.setText(f'모델 목록 {len(result)}개를 불러왔습니다. 모델을 선택하고 번역 테스트 또는 적용을 눌러주세요.')
        else:
            self._connection_status.setText('실제 번역 응답 확인: ' + str(result)[:200])

    @Slot(str)
    def _connection_failed(self, message):
        if self._request_is_current():
            self._connection_status.setText(message)

    @Slot()
    def _connection_finished(self):
        task = self._connection_thread
        self._connection_thread = None
        task.deleteLater()
        self._connect_btn.setEnabled(True)
        self._test_btn.setEnabled(True)

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

    def _check_ocr(self) -> None:
        from ..ocr.tesseract import resolve_tesseract
        import subprocess
        if self._ocr_engine.currentData() != "tesseract":
            QMessageBox.information(self, "OCR 확인", "이 배포본은 Tesseract를 포함합니다. PaddleOCR는 소스 실행 환경에서 별도로 설치해주세요.")
            return
        exe = resolve_tesseract(self._tesseract_cmd.text().strip())
        if exe is None:
            QMessageBox.warning(self, "OCR 확인", "OCR 엔진이 없습니다. ZIP 전체를 압축 해제하거나 실행파일 경로를 지정해주세요.")
            return
        try:
            args = [str(exe), "--list-langs"]
            if (exe.parent / "tessdata").is_dir():
                args += ["--tessdata-dir", str(exe.parent / "tessdata")]
            result = subprocess.run(args, capture_output=True, text=True, timeout=10,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError("OCR 엔진 실행 실패")
            available = set(result.stdout.splitlines()[1:])
            missing = set(self._ocr_langs.text().strip().split("+")) - available
            if missing:
                raise RuntimeError("언어 데이터가 없습니다: " + ", ".join(sorted(missing)))
            QMessageBox.information(self, "OCR 확인", "OCR 준비 완료! 선택한 언어를 사용할 수 있습니다.")
        except Exception as exc:
            QMessageBox.warning(self, "OCR 확인", str(exc))

    # ---------------------------------------------------- actions
    def apply_settings(self) -> bool:
        s = self._settings
        s.provider = self._provider.currentData() or "openai"
        s.endpoint = self._endpoint.text().strip()
        s.model = self._model.currentText().strip()
        s.ocr_engine = self._ocr_engine.currentData() or "tesseract"
        s.ocr_languages = self._ocr_langs.text().strip() or "eng"
        s.tesseract_cmd = self._tesseract_cmd.text().strip()
        s.target_language = self._target_lang.text().strip() or "Korean"
        s.hotkey = self._hotkey.text().strip() or "<ctrl>+<alt>+<f9>"
        s.hotkey_version = 1
        s.theme = self._theme.currentText().strip() or "light"
        s.pin_mode_interval_ms = int(self._interval.value())

        s.overlay_font_family = self._font_family.currentFont().family()
        s.overlay_font_size = int(self._font_size.value())
        s.overlay_line_spacing = int(self._line_spacing.value())
        s.overlay_opacity = max(0.3, min(1.0, self._opacity.value() / 100.0))

        s.system_prompt = self._prompt_edit.toPlainText().strip()

        s.history_enabled = bool(self._history_enabled.isChecked())
        s.history_recent_context = int(self._recent_context.value())

        self._remember_provider()
        s.provider_profiles = copy.deepcopy(self._profiles)
        try:
            save_provider_keys(self._keys)
            save_settings(s)
        except OSError:
            QMessageBox.warning(self, '설정 저장', '설정을 저장하지 못했습니다. 폴더 권한을 확인해주세요.')
            return False
        self.settings_applied.emit()
        return True

    def accept(self) -> None:
        if self.apply_settings():
            super().accept()

    @property
    def settings(self) -> AppSettings:
        return self._settings


__all__ = ["SettingsDialog"]
