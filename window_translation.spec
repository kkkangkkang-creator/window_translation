# -*- mode: python ; coding: utf-8 -*-
"""Windows portable build. OCR assets are prepared by bundle_ocr.ps1."""
from pathlib import Path

ocr_dir = Path(SPECPATH) / 'vendor' / 'tesseract'
if not (ocr_dir / 'tesseract.exe').is_file():
    raise RuntimeError('Run scripts/bundle_ocr.ps1 before building: bundled OCR is required.')

a = Analysis(
    ['src/window_translation/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[(str(ocr_dir), 'tesseract')],
    hiddenimports=['pynput.keyboard._win32', 'pynput.mouse._win32'],
    excludes=['paddle', 'paddleocr', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='window_translation',
          debug=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='window_translation')
