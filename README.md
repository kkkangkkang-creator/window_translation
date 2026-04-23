# Window Translation

> Windows 화면의 일부를 캡처해 OCR로 글자를 읽고, OpenAI 등 AI 번역기로 한국어로
> 번역해서 항상 위에 떠있는 작은 창으로 보여주는 데스크톱 유틸리티입니다.
> **외국어 게임, 디스코드 채팅, 외국어 웹사이트** 같이 자체 번역 기능이 없는 곳에서
> 유용합니다.

[스크린샷 추가 예정]

---

## 1. 프로그램 소개

- **단축키 한 번**으로 화면의 어떤 영역이든 번역 가능 (기본 `Ctrl+Shift+T`).
- **핀 모드**: 한 번 잡은 영역을 자동으로 다시 캡처/번역. 채팅이나 자막처럼
  내용이 계속 바뀌는 곳에서 유용합니다. 픽셀이 실제로 바뀌었을 때만
  AI를 호출하므로 API 비용이 절약됩니다.
- **OCR 엔진**: Tesseract 또는 PaddleOCR (설정에서 선택).
- **번역 제공자**: OpenAI, Azure OpenAI, OpenRouter, Groq, Ollama, LM Studio,
  그리고 OpenAI 호환 프록시(LiteLLM, vLLM 등) 모두 지원.
- **번역 히스토리**: 모든 번역이 로컬 SQLite에 저장됩니다. 같은 텍스트는 캐시에서
  바로 가져오므로 API 비용 0. 앱 안에서 바로 검색·복사·내보내기 가능.
- **항상 위에 뜨는 오버레이**에 [복사] / [재번역] / [닫기] 버튼.
- **트레이 앱** — 평소엔 시스템 트레이에만 떠 있고 작업을 방해하지 않습니다.

---

## 2. 빠른 시작 (.exe 사용 — 코딩 몰라도 됨)

> 이 방법이 가장 쉽습니다. Python 같은 거 몰라도 됩니다.

1. 이 저장소의 [Releases 페이지](../../releases)에서 최신 버전의
   `window_translation-vX.Y.Z.zip` 파일을 다운로드합니다.
2. 다운로드한 zip 파일을 **마우스 우클릭 → "압축 풀기"** 로 적당한 폴더에 풉니다.
   (예: `C:\Tools\window_translation\`)
3. 풀린 폴더 안의 **`window_translation.exe` 를 더블클릭**해서 실행합니다.
   - Windows Defender SmartScreen 경고가 뜨면 "추가 정보" → "실행" 을 누르세요.
4. 화면 오른쪽 아래 **트레이 아이콘**(시계 옆)에 흰색 사각형 모양 아이콘이
   생깁니다. 그 아이콘을 **우클릭 → "설정…"** 으로 들어갑니다.
5. **OpenAI API 키**(아래 4번 항목 참고)를 "API 키" 칸에 붙여넣고 **확인**.
6. 끝! 이제 어디서든 **Ctrl+Shift+T** 를 누르고 번역하고 싶은 영역을
   드래그하면 옆에 한국어 번역이 뜹니다.

---

## 3. 소스에서 실행하기 (개발자용)

`.exe` 가 아닌 파이썬 소스로 직접 돌리고 싶을 때 (또는 코드 수정 시)
사용하는 방법입니다.

### 3-1. Python 3.10 이상 설치

[python.org/downloads](https://www.python.org/downloads/) 에서 최신 Python을
받아 설치합니다.

> ⚠️ 설치 화면 첫 페이지에서 **반드시 "Add Python to PATH" 체크박스를
> 켜고** "Install Now"를 누르세요. 안 그러면 명령 프롬프트에서 `python`
> 명령이 인식되지 않습니다.

설치 후 명령 프롬프트(시작 메뉴 → "cmd")에서 `python --version` 을 쳤을 때
`Python 3.10.x` 같은 게 나오면 OK.

### 3-2. Tesseract OCR 설치 (PaddleOCR 만 쓸 거면 건너뛰어도 됨)

[UB-Mannheim Tesseract 빌드](https://github.com/UB-Mannheim/tesseract/wiki) 에서
`tesseract-ocr-w64-setup-x.x.x.exe` 를 다운로드해 설치합니다.

> ⚠️ 설치 중 **"Additional language data (download)"** 항목에서
> **Korean / Japanese / Chinese (Simplified)** 를 꼭 체크하세요.
> 안 체크하면 한국어/일본어/중국어 OCR이 안 됩니다.

기본 설치 경로는 `C:\Program Files\Tesseract-OCR\` 입니다. 이 경로를
설정 다이얼로그의 "Tesseract 경로" 칸에 넣어두면 안전합니다.
(`tesseract.exe` 가 PATH에 있으면 비워둬도 됩니다.)

### 3-3. 저장소 다운로드

GitHub 페이지 우측 상단 **"Code" → "Download ZIP"** 으로 받거나, git이
설치돼 있다면:

```cmd
git clone https://github.com/kkkangkkang-creator/window_translation.git
cd window_translation
```

### 3-4. 가상환경 만들고 의존성 설치

명령 프롬프트에서 (위 폴더로 이동한 상태):

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> PaddleOCR도 쓰고 싶으면 추가로:
> ```cmd
> pip install -r requirements-optional.txt
> ```
> (용량이 1GB 이상으로 큽니다. Tesseract 만 쓸 거면 건너뛰세요.)

### 3-5. 실행

```cmd
python -m window_translation
```

트레이에 아이콘이 생깁니다. 끝.

---

## 4. OpenAI API 키 발급 방법

1. [platform.openai.com/api-keys](https://platform.openai.com/api-keys) 에
   접속해 OpenAI 계정으로 로그인합니다 (없으면 회원가입).
2. 좌측 메뉴 **"Billing"** 에서 신용카드를 등록하고 최소 $5 정도 충전합니다.
   (충전을 안 하면 API가 동작하지 않습니다.)
3. 메뉴 **"API keys" → "Create new secret key"** 를 누르고 키 이름을
   적당히 입력 (예: `window_translation`). **Create** 후 화면에 뜨는
   `sk-...` 로 시작하는 문자열을 복사해 둡니다. **이 화면을 닫으면 다시 볼 수 없으므로**
   바로 메모장에 붙여 두세요.
4. 트레이 메뉴 **설정… → API 키** 칸에 붙여넣고 **확인**.

### 비용 안내 (대략)
- 기본 모델은 **gpt-4o-mini** 로 설정되어 있어 매우 저렴합니다.
- 짧은 채팅 한 줄(원문+번역 합 ~200토큰) 기준 **0.0001달러 미만** 정도.
  하루 종일 게임을 번역해도 보통 $1을 넘기 어렵습니다.
- 같은 텍스트는 캐시에서 바로 반환되므로 반복 비용은 0입니다.

---

## 5. GUI 사용법

### 단축키
- 기본: **Ctrl+Shift+T**
- 누르면 화면 전체가 어두워지고 영역 드래그 모드가 됩니다.
- 마우스로 사각형을 드래그하면 그 영역이 번역됩니다.
- 취소: **Esc** 또는 마우스 **우클릭**.
- 단축키는 설정에서 변경 가능 (`<ctrl>+<shift>+t` 같은 [pynput
  포맷](https://pynput.readthedocs.io/en/latest/keyboard.html#pynput.keyboard.HotKey.parse)).

### 영역 선택
드래그 → 손을 떼면 그 영역이 번역됩니다. 결과는 영역 바로 아래(또는 공간이
없으면 위/옆)에 작은 창으로 뜹니다.

### 번역 결과 오버레이
- 우상단 **[복사]** : 번역문을 클립보드에 복사.
- 우상단 **[재번역]** : 같은 영역을 다시 캡처해서 OCR + 번역을 다시 실행.
- 우상단 **[×]** : 창 닫기 (번역 자체는 히스토리에 남습니다).
- 창 자체를 드래그해서 위치 이동 가능.

### 핀 모드 (자동 재번역)
1. 한 번 번역을 한 뒤
2. 트레이 메뉴 **"현재 영역 핀 (자동 재번역)"** 체크
3. 그 영역의 픽셀이 바뀔 때마다 자동으로 다시 OCR + 번역됩니다
   (디스코드 채팅창이나 게임 자막에 유용).
4. 다시 클릭해서 끄기.

### 설정 다이얼로그 탭별 설명

#### 일반
- **번역 제공자**: openai / openrouter / groq / ollama / lm-studio /
  azure-openai / custom / stub (테스트용 가짜 번역기).
- **Endpoint URL**: 위 제공자에 맞게 자동으로 채워집니다. 직접 프록시를
  쓰면 여기에 URL을 적습니다.
- **모델**: 예) `gpt-4o-mini`, `gpt-4o`, `claude-3-haiku-20240307` (OpenRouter 경유) 등.
- **API 키**: 위 4번 항목에서 받은 `sk-...` 키. 비밀번호처럼 가려져 표시됩니다.
- **OCR 엔진**: `Tesseract` 또는 `PaddleOCR`. PaddleOCR 사용 시 별도
  Tesseract 설치 불필요.
- **OCR 언어**: Tesseract 언어 코드를 `+` 로 묶음. 기본 `eng+jpn+chi_sim`.
  한국어가 필요하면 `eng+kor+jpn+chi_sim`.
- **Tesseract 경로**: `tesseract.exe` 가 PATH에 없을 때 적어두면 안전합니다.
- **번역 대상 언어**: 보통 `Korean` 으로 둡니다.
- **테마**: light / dark.
- **단축키**: 위 단축키 항목 참고.
- **핀 모드 주기**: 핀 모드에서 화면을 다시 검사하는 간격(ms).

#### 오버레이
- 글꼴 / 글자 크기 / 줄 간격 / 창 투명도 조정.

#### 프롬프트
- 번역에 쓰이는 system prompt 를 직접 편집할 수 있습니다.
- `{target_language}`, `{source_language}` 같은 변수가 들어갑니다.
- 비워두면 내장 기본 프롬프트가 사용됩니다.

#### 히스토리
- 캐시/히스토리 ON/OFF.
- "최근 예시 개수" > 0 으로 두면 최근 번역 N건을 few-shot 예시로 함께 보내
  용어/말투 일관성이 좋아집니다 (대신 토큰 비용이 늘어납니다).

### 트레이 메뉴
- **영역 번역…** : 단축키와 동일.
- **현재 영역 핀** : 위 핀 모드.
- **설정…** : 위 설정 다이얼로그.
- **히스토리 보기…** : 앱 안에서 모든 번역을 표로 봅니다.
  - 검색창에 단어를 입력하면 원문/번역에서 부분 일치로 필터링.
  - 행을 **더블클릭** 하면 해당 번역이 클립보드에 복사됩니다.
  - 우상단 **내보내기** / **전체 삭제** 버튼.
- **히스토리 내보내기…** : JSON / CSV / TXT 중 선택.
- **히스토리 삭제** : 전체 삭제.
- **종료** : 앱 종료.

---

## 6. 자주 묻는 질문 (FAQ)

**Q. 게임에서 단축키가 안 먹어요.**
A. 일부 게임의 안티치트(특히 풀스크린 + 입력 후킹 차단)는 전역 단축키나
   화면 캡처를 차단합니다. **창 모드** 또는 **테두리 없는 창모드(Borderless
   Windowed)** 로 게임을 실행해 보세요. 그래도 안 되면 트레이 메뉴 →
   "영역 번역…" 으로 직접 띄울 수 있습니다.

**Q. OCR이 글자를 잘 못 읽어요.**
A. 다음을 시도해 보세요:
   1. 영역을 더 크게 잡아주세요 (글자 주변 여백 포함).
   2. 게임/앱 자체 글자 크기를 키워보세요.
   3. 설정에서 OCR 언어에 해당 언어를 추가했는지 확인 (한국어면 `kor` 포함).
   4. 설정에서 OCR 엔진을 **PaddleOCR** 로 바꿔 보세요. 한·일·중은 종종
      Tesseract 보다 정확합니다.

**Q. API 비용을 더 아끼고 싶어요.**
A.
   - 기본 모델 `gpt-4o-mini` 가 충분히 저렴합니다. 더 큰 모델로 바꾸지 마세요.
   - 핀 모드는 픽셀이 바뀐 경우에만 호출하므로 효율적입니다.
   - 같은 문장은 캐시로 처리되므로 반복 비용은 0입니다.
   - 무료 옵션이 필요하면 설정 → 제공자 = `ollama` (로컬 LLM) 로 바꿀 수 있습니다.

**Q. 단축키가 다른 앱과 충돌해요.**
A. 설정 → 단축키 칸에서 바꿀 수 있습니다. 형식 예시:
   `<ctrl>+<alt>+y`, `<ctrl>+<shift>+1`. 설정 저장 후 자동으로 새 단축키가
   적용됩니다.

**Q. 번역창이 자꾸 엉뚱한 곳에 떠요.**
A. 번역창은 마우스로 드래그해 위치를 옮길 수 있습니다. 새 번역이 떠도
   기본적으로는 영역 근처에 다시 자리 잡습니다. 모니터 끝에 너무 붙어 있을
   때만 화면 안으로 자동 보정됩니다.

**Q. "Tesseract가 설치되지 않았습니다" 에러가 떠요.**
A. 위 3-2 항목으로 Tesseract 를 설치하거나, 설정에서 OCR 엔진을
   **PaddleOCR** 로 바꾸고 `pip install -r requirements-optional.txt` 를
   실행하세요. (.exe 사용자는 PaddleOCR 옵션이 가장 간단합니다.)

---

## 7. PyInstaller로 .exe 직접 빌드

소스에서 직접 .exe 를 만들려면 (Windows에서):

```cmd
build_exe.bat
```

위 한 줄로 끝납니다. 결과물은 `dist\window_translation\window_translation.exe`
에 생성됩니다. 그 폴더 전체를 zip으로 묶어 배포하면 됩니다.

내부적으로는 `window_translation.spec` 파일을 사용해 PyInstaller 가
실행됩니다. 옵션을 바꾸려면 그 파일을 수정하세요.

> 참고: GitHub Actions 워크플로 (`.github/workflows/release.yml`) 가
> `vX.Y.Z` 형식의 태그를 푸시할 때 자동으로 위 빌드를 돌리고 zip을 만들어
> Releases 에 올려줍니다.
> ```cmd
> git tag v0.1.0
> git push origin v0.1.0
> ```

---

## 8. 라이선스 / 면책

- 라이선스: MIT (자세한 내용은 `pyproject.toml` 참조).
- 본 프로그램은 **개인 학습/편의 용도**로 만들어졌습니다. 사용 중 발생하는
  모든 문제(데이터 손실, 계정 정지, API 요금 등)에 대해 작성자는 책임지지
  않습니다.
- 일부 게임/서비스는 화면 캡처나 자동화를 약관으로 금지하고 있을 수 있습니다.
  사용 전 해당 서비스의 약관을 반드시 확인하세요.
- API 키는 본인 외에 절대 공유하지 마세요.

---

## 프로젝트 구조 (참고)

```
window_translation/
├─ src/window_translation/
│  ├─ __main__.py             # python -m window_translation 진입점
│  ├─ app.py                  # 트레이 / 단축키 / 오케스트레이터
│  ├─ capture/                # 화면 캡처 + 영역 선택
│  ├─ ocr/                    # Tesseract / PaddleOCR 백엔드
│  ├─ translate/              # OpenAI 호환 번역 + 캐시 + 스텁
│  ├─ overlay/                # 결과 창 / 설정 / 히스토리 뷰어
│  └─ config/                 # settings.json + API 키 저장
├─ tests/                     # pytest 모음 (디스플레이 불필요)
├─ requirements.txt           # 기본 의존성
├─ requirements-optional.txt  # PaddleOCR 등 무거운 의존성
├─ window_translation.spec    # PyInstaller 설정
├─ build_exe.bat              # Windows 빌드 스크립트
└─ .github/workflows/release.yml  # 태그 푸시 시 자동 빌드/Release
```
