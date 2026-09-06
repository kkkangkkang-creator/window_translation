@echo off
setlocal
cd /d "%~dp0"
python -m venv .build-venv || goto :fail
set "BUILD_PY=%~dp0.build-venv\Scripts\python.exe"
"%BUILD_PY%" -m pip install -r requirements.txt "pyinstaller>=6.11,<7" pytest || goto :fail
powershell -NoProfile -File scripts\bundle_ocr.ps1 || goto :fail
"%BUILD_PY%" -m pytest -q || goto :fail
"%BUILD_PY%" -m PyInstaller --clean --noconfirm window_translation.spec || goto :fail
copy /Y QUICKSTART.txt dist\window_translation\QUICKSTART.txt >nul
powershell -NoProfile -Command "$p = Start-Process -FilePath 'dist\window_translation\window_translation.exe' -ArgumentList '--self-test smoke-test.json' -PassThru -Wait; exit $p.ExitCode" || goto :fail
powershell -NoProfile -Command "Compress-Archive -Path dist\window_translation -DestinationPath dist\window_translation-windows-x64.zip -Force" || goto :fail
echo Build complete: dist\window_translation-windows-x64.zip
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
