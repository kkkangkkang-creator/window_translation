"""Bootstrap logging before importing Qt; supports packaged smoke checks."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback


def self_test(output: Path) -> int:
    """Exercise bundled Qt widgets and real OCR, without a paid API request."""
    report = {"ok": False}
    try:
        from PySide6.QtWidgets import QApplication
        from PIL import Image, ImageDraw, ImageFont
        from .config import AppSettings
        from .overlay import ResultOverlay, SettingsDialog
        from .ocr.tesseract import TesseractOCR, resolve_tesseract
        import subprocess

        app = QApplication.instance() or QApplication([])
        overlay = ResultOverlay()
        settings = SettingsDialog(AppSettings())
        overlay.show_translation("Hello", "안녕하세요")
        app.processEvents()
        settings.close()
        overlay.close()
        executable = resolve_tesseract()
        if executable is None:
            raise RuntimeError("Bundled Tesseract not found")
        data = executable.parent / "tessdata"
        result = subprocess.run([str(executable), "--list-langs", "--tessdata-dir", str(data)],
                                capture_output=True, text=True, timeout=15,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result.check_returncode()
        languages = set(result.stdout.splitlines()[1:])
        if not {"eng", "jpn", "chi_sim", "chi_tra"}.issubset(languages):
            raise RuntimeError("Missing OCR languages: " + result.stdout)
        img = Image.new("RGB", (700, 100), "white")
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"), 40)
        ImageDraw.Draw(img).text((20, 20), "HELLO WORLD", fill="black", font=font)
        text = TesseractOCR(languages="eng").run(img).text
        if "HELLO" not in text.upper() or "WORLD" not in text.upper():
            raise RuntimeError("OCR smoke check failed: " + text)
        report.update(ok=True, ocr=text, languages=sorted(languages), qt=True)
    except Exception:
        report["error"] = traceback.format_exc()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def main() -> int:
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        return self_test(Path(sys.argv[index + 1]))
    log_path = None
    try:
        from .config import default_config_dir
        log_path = default_config_dir() / "application.log"
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                            handlers=[RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
                            force=True)
        from .app import main as run_app
        return run_app()
    except Exception:
        logging.exception("Application failed to start")
        message = "프로그램을 시작하지 못했습니다. ZIP 전체를 새 폴더에 압축 해제해주세요."
        if log_path:
            message += f"\n오류 기록: {log_path}"
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Window Translation", 0x10)
        elif sys.stderr:
            traceback.print_exc()
        return 1
