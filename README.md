# Window Translation

Windows 화면에서 선택한 영역을 OCR로 읽어 한국어로 번역하는 개인용 데스크톱 앱입니다.

## Windows에서 사용하기

1. [Releases](https://github.com/kkkangkkang-creator/window_translation/releases)에서 **window_translation-windows-x64.zip**을 받습니다. `Source code` ZIP은 실행 파일이 아닙니다.
2. ZIP 전체를 새 폴더에 압축 해제합니다. `window_translation.exe`와 `_internal` 폴더를 함께 두세요.
3. EXE를 실행하면 설정 창이 열립니다. **OCR 준비 상태 확인**을 누르세요.
4. 번역 제공자, 모델, API 키를 입력하고 확인을 누릅니다.
5. **Ctrl+Shift+T**를 누르고 번역할 영역을 드래그합니다.

Python 설치는 필요 없습니다. 배포 ZIP에는 Tesseract 실행 엔진과 영어·일본어·중국어 간체/번체 데이터가 포함됩니다. 온라인 번역에는 추출한 텍스트가 전송되고 제공자에 따라 사용료가 발생합니다. API 키는 ZIP에 포함되지 않습니다.

같은 영역은 번역창의 **재번역** 버튼으로 다시 읽을 수 있습니다. 시계 옆 트레이 메뉴에서 설정, 자동 재번역, 기록 보기, 종료를 선택하세요. 설정을 닫아도 앱은 트레이에 남습니다.

## 현재 범위와 제한

- 영역 선택, 단축키, 자동 재번역, 별도 결과 창, 번역 기록/캐시, 기록 내보내기를 지원합니다.
- 자동 감지는 이미지의 변화량을 비교하므로 전체 게임 화면의 작은 대사 변화를 놓치거나 배경 움직임을 감지할 수 있습니다. 먼저 작은 대사 영역에서 확인하세요.
- 만화 말풍선 순서, 세로쓰기와 혼합 레이아웃의 품질은 아직 보강이 필요합니다. 말풍선 위에 번역문을 직접 배치하지 않습니다.
- 게임 창 추적과 서로 다른 배율의 다중 모니터는 아직 별도 검증이 필요합니다.
- PaddleOCR는 소스 실행용 선택 기능이며 배포 ZIP에는 포함하지 않습니다.
- 로컬 서버는 Ollama/LM Studio 프리셋을 선택한 뒤 실제 설치한 모델명을 입력하세요.

## 오류가 날 때

EXE만 옮기지 말고 ZIP 전체를 새 폴더에 다시 풀어주세요. OCR 경로는 보통 비워둡니다. 직접 지정할 경우 `tesseract.exe` 파일 또는 그 파일이 있는 폴더를 선택하세요.

오류 기록은 `%APPDATA%\window_translation\application.log`에 저장됩니다. Win+R에서 이 경로를 열 수 있습니다.

## 소스 실행

Python 3.10 이상을 사용하세요. Windows 빌드는 Python 3.11에서 검사합니다.

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
python -m window_translation
```

소스 실행에서는 Tesseract와 필요한 언어 데이터를 별도로 설치해야 합니다. 테스트는 `python -m pip install pytest` 후 `python -m pytest -q`로 실행합니다.

## EXE 빌드

Windows에서 Tesseract를 기본 위치에 설치한 뒤 `build_exe.bat`을 실행합니다. 독립된 `.build-venv`를 만들고, OCR 엔진과 언어 데이터 준비 → 테스트 → PyInstaller → EXE의 실제 OCR 검사 → ZIP 포장을 수행합니다.

GitHub Actions도 같은 검사를 수행합니다. `codex/windows-portable` 브랜치 푸시 또는 버전 태그 푸시로 빌드를 시작하고, 검사에 통과한 ZIP과 SHA256을 미리보기 Release에 올립니다. 수동 실행은 Actions 결과물에 ZIP을 보관합니다.

자동 검사는 Qt 위젯 생성, 포함된 언어 데이터와 실제 영어 OCR을 확인합니다. 실제 게임 화면 캡처 및 온라인 번역 성공까지 보장하는 검사는 아닙니다.

Tesseract 및 언어 데이터의 라이선스 파일은 배포 폴더에 포함됩니다. 프로젝트 라이선스 선언은 `pyproject.toml`을 참고하세요.
