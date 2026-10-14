# LocalNotebook

Local, source-grounded research notebook. See `PROJECT_SPEC.md` for the full specification.

**Status:** M7 implemented (export/import and polish): v1.0 candidate. Everything from M0 to M6
(notebooks, sources of every type, cited chat, notes, generated documents, structured study aids,
audio overviews) plus:

- **Export and import** (`Export` on a notebook card, `Import notebook` on the home screen). A
  notebook is one `.lnb` file (a ZIP of its folder and a manifest). Importing never overwrites: if the
  notebook is already there, it is added as a copy.
- **Rebuild index.** After you change the embedding model, notebooks show an offer to rebuild their
  search index, which re-reads every source and note with the new model.
- **Appearance** (Settings): light, dark, or the same as the computer; text size.
- **Keyboard:** `Enter` sends, `Shift+Enter` adds a line, `Esc` closes the newest open menu, dialog,
  or panel, `Ctrl/Cmd+K` focuses search.
- An accessibility pass (checked automatically with axe-core in light and dark themes).

Ingesting a source calls your model server twice (embeddings, then a short source guide), so a chat
model and an embedding model must be set in Settings first. Without them a source shows as failed
with a **Retry** button.

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages Python 3.11+)
- Node.js 20+ and npm
- [Ollama](https://ollama.com) (or another OpenAI-compatible local server)
- Tesseract, ffmpeg and espeak-ng on `PATH` (checked by the setup wizard; espeak-ng is only needed for audio overviews)

## Run

| OS | Command |
|-|-|
| Linux / macOS | `scripts/run.sh` |
| Windows (PowerShell) | `scripts/run.ps1` |

This builds the frontend on first run, starts the server on a free `127.0.0.1` port, and opens your
browser with a per-launch token. On first launch the setup wizard checks the model server, your
chat and embedding models, Tesseract, and ffmpeg.

## Develop

`scripts/dev.sh` / `scripts/dev.ps1`: backend with reload plus the Vite dev server.

## Test and lint

```
uv run pytest
uv run ruff check
cd frontend && npm test && npm run lint
```

End-to-end smoke test (QA-5; a real browser against the built UI and a fake model) and the
accessibility check:

```
cd frontend && npm install && npm run build   # once, and after UI changes
uv run pytest -m e2e
```

Performance check against spec §9 (measures the app's own cost with a fake model; the real-model
parts are for you to measure on your hardware):

```
uv run python evals/perf_check.py
```

## Web, video, audio, and OCR

- **Tesseract** (a separate program) is needed for images and scanned PDF pages. Without it the rest
  works, and the setup wizard and the Add source menu say so.
- **Audio and videos without captions** need a speech-to-text model: enter its name in Settings, then
  press **Download model** (it asks first and shows progress). Models live in your data folder.
- **Transcribe videos without captions** is off by default. Turning it on downloads only the audio,
  transcribes it on your computer, and deletes the audio. You are responsible for complying with the
  platform's terms of service.
- **Discover** needs your own [SearXNG](https://docs.searxng.org) address with JSON output enabled
  (Settings > Network). It suggests up to 10 pages or videos; nothing is imported until you tick them.
- Web addresses on this computer or your local network are always refused. Each kind of network use
  can be switched off in Settings > Network.

## Generated documents and large notebooks

Artifacts are written from all enabled sources. If they do not fit in your model's context window,
the app first condenses them in parts, then writes the document from those notes. Set **Model
context window (tokens)** in Settings to your model's real size (default 8000). PDF export uses a
system Unicode font when one is installed (DejaVu Sans, Arial); otherwise it uses a built-in
Latin-only font.

## Grounding evaluation (QA-4)

Run manually against a real model; it uses fictional documents so the model cannot answer from
memory:

```
uv run python evals/run_eval.py --chat-model <name> --embedding-model <name>
```

It asks 30 questions (15 answerable, 15 not) and prints a results table with two rates: citation
support (target 95%) and correct refusal (target 90%). `--selftest` checks the script itself with a
scripted model and needs no server.

## Configuration

- Defaults: `backend/app/config/defaults.toml`. Model names are empty until you set them in the
  wizard or Settings.
- Environment overrides: `LNB_DATA_ROOT`, `LNB_HOST_PORT`, `LNB_LLM_BASE_URL`.
- Data folder: the OS user-data directory for "LocalNotebook" (override with `LNB_DATA_ROOT`).
