# LocalNotebook

Local, source-grounded research notebook. See `PROJECT_SPEC.md` for the full specification.

**Status:** M0 (skeleton) complete. No notebook or source features yet.

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages Python 3.11+)
- Node.js 20+ and npm
- [Ollama](https://ollama.com) (or another OpenAI-compatible local server)
- Tesseract and ffmpeg on `PATH` (checked by the setup wizard; needed from later milestones)

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

## Configuration

- Defaults: `backend/app/config/defaults.toml`. Model names are empty until you set them in the
  wizard or Settings.
- Environment overrides: `LNB_DATA_ROOT`, `LNB_HOST_PORT`, `LNB_LLM_BASE_URL`.
- Data folder: the OS user-data directory for "LocalNotebook" (override with `LNB_DATA_ROOT`).
