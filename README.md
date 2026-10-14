# LocalNotebook

Local, source-grounded research notebook. See `PROJECT_SPEC.md` for the full specification.

**Status:** M3 implemented (notes and text artifacts). On top of M2 (grounded chat with citations)
you can now keep chat answers as notes, edit notes in Markdown with a live preview, summarize or
combine notes, turn notes into sources, and generate four documents from your sources (summary,
briefing, study guide, FAQ) that you can export as Markdown, Word, or PDF. Artifacts show a "Sources
changed" badge when a source they used is disabled or removed. Structured artifacts (timeline, mind
map, flashcards), the remaining source types, and audio overviews come in later milestones.

Ingesting a source calls your model server twice (embeddings, then a short source guide), so a chat
model and an embedding model must be set in Settings first. Without them a source shows as failed
with a **Retry** button.

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
