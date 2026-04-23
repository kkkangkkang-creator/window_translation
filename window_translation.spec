# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 설정 파일.

빌드 방법:
    pyinstaller window_translation.spec

결과:
    dist/window_translation/window_translation.exe (+ 의존 파일들)
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# PySide6 의 동적 import 를 모두 포함하도록 helper 사용.
hiddenimports = [
    "window_translation",
    "window_translation.app",
    "window_translation.capture.selector",
    "window_translation.ocr.paddleocr_backend",
] + collect_submodules("PySide6")

a = Analysis(
    ["src/window_translation/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # paddle / numpy 등 선택적 의존성은 사용자가 설치돼 있을 때만 묶입니다.
        # 명시적으로 빼지 않음 (PyInstaller 가 알아서 미설치면 무시).
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="window_translation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # PySide6 dll 들은 upx 압축 시 깨질 수 있음
    console=False,  # GUI 트레이 앱 → 콘솔 창 숨김
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="window_translation",
)
