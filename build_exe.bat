@echo off
REM Window Translation 빌드 스크립트 (Windows)
REM 사용: build_exe.bat
REM 결과: dist\window_translation\window_translation.exe

setlocal

echo === [1/3] 의존성 설치 ===
python -m pip install --upgrade pip || goto :fail
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo === [2/3] 이전 빌드 정리 ===
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist

echo === [3/3] PyInstaller 빌드 ===
python -m PyInstaller --noconfirm window_translation.spec || goto :fail

echo.
echo [완료] dist\window_translation\window_translation.exe 생성됨
endlocal
exit /b 0

:fail
echo.
echo [실패] 빌드 중 오류가 발생했습니다. 위 메시지를 확인해주세요.
endlocal
exit /b 1
