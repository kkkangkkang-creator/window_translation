# window_translation

Capture any region of your Windows desktop, run OCR on it, translate the
result with an AI API, and display the translation as an always-on-top
overlay. Designed for **foreign games**, **Discord chat** in another
language, and other apps that don't have a built-in translator.

> **Status:** Early MVP. Phase 1–5 of the roadmap are implemented. Windows is
> the primary target; macOS/Linux may work but are untested.

---

## Features

- **One-shot translation** — press a global hotkey, drag a rectangle, read the
  translation in a popup next to the captured area.
- **Region-pin mode** — pin the last selection; the app re-captures it
  periodically and only re-translates when the pixels actually change (uses a
  perceptual hash to skip unchanged frames and avoid burning API credits).
- **Pluggable translators** — OpenAI-compatible Chat Completions endpoint
  (OpenAI, Azure OpenAI, local LLM gateways) plus an offline stub for
  testing.
- **Tesseract OCR** with English / Japanese / Simplified Chinese language
  packs by default; easy to extend.
- **System-tray app** with a settings dialog for provider, model, API key,
  hotkey, OCR languages, and overlay appearance.
- **Secret handling** — API key stored in a separate per-user file with
  `0600` permissions on POSIX; the `OPENAI_API_KEY` environment variable
  always takes precedence.

---

## Requirements

- Python ≥ 3.9
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on `PATH`
  (or configured in settings)
  - On Windows, install from the UB-Mannheim builds and tick the `jpn`,
    `chi_sim` language packs during setup.
- A translation API key (e.g. `OPENAI_API_KEY`). Without one, the app falls
  back to a visible "stub" translator.

## Install

```bash
# From a clone of this repo
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS/Linux
pip install -r requirements.txt
# (optional, for editable install + console script)
pip install -e .
```

## Run

```bash
python -m window_translation
# or, after `pip install -e .`
window-translation
```

The app lives in the system tray. Left-click the tray icon, or press the
configured hotkey (default **Ctrl+Shift+T**), to enter region-selection mode.
Drag a rectangle; the translation popup appears next to it.

### Configuration

Open **Settings…** from the tray menu to edit:

| Setting              | Description                                         |
| -------------------- | --------------------------------------------------- |
| Provider             | `openai` or `stub`                                  |
| Model                | e.g. `gpt-4o-mini`                                  |
| API key              | Stored separately with tight file permissions       |
| OCR languages        | Tesseract codes, joined with `+` (e.g. `eng+jpn`)   |
| Tesseract path       | Optional — if the binary isn't on `PATH`            |
| Target language      | Plain English name (e.g. `Korean`, `English`)       |
| Hotkey               | `pynput` format, e.g. `<ctrl>+<shift>+t`            |
| Overlay font size    | Points                                              |
| Pin-mode interval    | Milliseconds between checks while pinned            |

Settings and the API key are stored under:

- Windows: `%APPDATA%\window_translation\`
- macOS/Linux: `$XDG_CONFIG_HOME/window_translation/` (default `~/.config/…`)

---

## Project layout

```
window_translation/
├─ src/window_translation/
│  ├─ __main__.py          # python -m window_translation
│  ├─ app.py               # tray, hotkey, orchestrator
│  ├─ capture/             # screen capture + region selection overlay
│  ├─ ocr/                 # Tesseract wrapper + preprocessing
│  ├─ translate/           # base + OpenAI + stub + factory
│  ├─ overlay/             # result popup + settings dialog
│  └─ config/              # settings.json + API key storage
├─ tests/                  # pytest suite (no display required)
├─ requirements.txt
├─ pyproject.toml
└─ README.md
```

---

## Development

```bash
pip install -r requirements.txt
pip install pytest
pytest
```

The test suite covers settings round-tripping, OCR text cleanup + language
heuristics, the perceptual hash, the API-key store's permissions, and the
translation backends (with a mocked HTTP session — no real network calls).
GUI widgets are intentionally not unit-tested because they require a
display; exercise them manually.

---

## Roadmap

Implemented (Phase 1–5 + parts of Phase 6/7):

- [x] Project scaffolding (pyproject, src layout)
- [x] Region-selection overlay (drag / Esc / right-click cancel)
- [x] Multi-monitor-aware screen capture via `mss`
- [x] Tesseract OCR with preprocessing + heuristic language detection
- [x] OpenAI-compatible translator + offline stub
- [x] Result overlay with smart placement near the captured region
- [x] System-tray app + global hotkey
- [x] Settings dialog, JSON-persisted config, separate API-key file
- [x] Pin mode with perceptual-hash change detection

Planned:

- [ ] Windows DPAPI for API-key encryption
- [ ] Translation history / re-lookup
- [ ] Multiple pinned regions at once
- [ ] Optional PaddleOCR / EasyOCR backends
- [ ] User glossary (proper nouns / game terms)
- [ ] PyInstaller single-exe build
- [ ] Windows Graphics Capture API for exclusive-fullscreen games

---

## Caveats

- DirectX exclusive-fullscreen games may not be capturable; run them in
  borderless-windowed mode.
- OCR quality is the ceiling for translation quality. Increase the
  captured region size or zoom if the result looks garbled.
- The region-pin mode and hotkey require foreground-input privileges;
  some anti-cheat systems reject both.
- Always respect the terms of service of the app you're translating.

## License

MIT.
