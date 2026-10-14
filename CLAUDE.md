# CLAUDE.md

`PROJECT_SPEC.md` is the single source of truth. Read its §0 before changing anything. Do not
edit it except to tick milestone boxes in §12. Stop after each milestone for owner testing.

## Current status

M0 accepted. M1 (notebooks and core ingestion) implemented, awaiting owner acceptance. Next: M2.

## Architecture (as built)

- `pyproject.toml` is at the repo root (`uv run pytest`, `uv run ruff check` work from there).
  Python code is in `backend/app`; tests in `backend/tests` (`pythonpath = backend`).
- `app.main.create_app()` is the FastAPI app factory (`uvicorn app.main:create_app --factory`).
  It runs app.db migrations, installs `SecurityMiddleware` (SR-2: bearer token on `/api/*`, Origin
  allow-list), serves `frontend/dist` if built, and returns errors as `{"error": {code, message}}`.
- Token comes from env `LNB_TOKEN` (set by `scripts/launcher.py`); the browser gets it in the URL
  fragment (`#token=`), `frontend/src/api.ts` moves it to sessionStorage.
- Config: `core/config.py` (defaults.toml + `LNB_*` env). Settings live in app.db
  (`core/settings_store.py`, JSON values, defaults from defaults.toml). `LNB_LLM_BASE_URL` overrides
  the stored URL.
- Migrations: numbered SQL files in `backend/migrations/<db>/`, applied by `core/db.migrate`, each in
  a transaction, with a file backup before upgrading an existing db (DR-4).
- LLM: `llm/base.py` (`LLMClient` protocol, `LLMError`), `openai_compat.py` (real), `fake.py`
  (scripted, for all tests, QA-2). API handlers get a client via `app.state.llm_factory`; tests pass
  a fake factory to `create_app`.
- Setup wizard checks: `core/setup_checks.py`, exposed at `GET /api/v1/setup/checks`.
- Frontend: Vite + React + TS + Tailwind v4, `src/pages` (Workspace, Setup, SettingsPage),
  hand-typed API client in `src/api.ts`.

## M1 additions

- Notebooks: `core/notebooks.NotebookStore` (registry in app.db, folder + `notebook.db` per notebook,
  `data_root/notebooks/<id>/sources/<source_id>/{original.<ext>,extracted.json}`). `open()` raises
  `NotFound` (mapped to 404) for unregistered ids. Never call `db.connect` on a notebook path
  directly: it would recreate a deleted folder.
- Notebook migrations: `backend/migrations/notebook/`. Vector table is created lazily on the first
  embedding (dimension from the model, recorded in `notebook_meta`): sqlite-vec `chunk_vectors`, or
  `chunk_vectors_fallback` BLOB table if the extension cannot load (`retrieval/vectors.py`).
- Ingestion: `ingest/pipeline.run_ingest` = parse (spawned process with timeout and Linux memory
  limit, `ingest/sandbox.py`) -> `extracted.json` (full normalized text plus location `segments`) ->
  `chunker.chunk_text` (~500 tokens, ~80 overlap, tokens estimated as chars/4) -> embeddings ->
  `write_index` (chunks + FTS5 + vectors, one transaction) -> source guide. `reindex_source`
  rebuilds the index from `extracted.json` alone (DR-3).
- Jobs: `jobs/runner.JobRunner` (asyncio queue, 2 workers, `jobs` table). On startup,
  `recover()` marks queued/running jobs `interrupted` and their sources `failed` (retryable).
- Structured LLM output with validation + 2 retries: `llm/structured.generate_json` (reuse for
  FR-5.10). Prompts: `backend/app/prompts/*.txt`, rendered by `llm/prompts.render_prompt`.
- API: `/api/v1/notebooks[/{id}[/sources...]]`. Sources list also streams over SSE
  (`/sources/stream`: sends snapshots, closes when nothing is queued or processing). The frontend
  reads it with fetch (`api.ts`), since EventSource cannot send the token header.
- Frontend: hash routing (`#/`, `#/notebooks/<id>`, `#/settings`); `SourcesPane`, `SourceViewer`
  (accepts a `highlight` range for citations, used from M2), `hooks/useSources`.
- Tests build PDFs/DOCX in code (`tests/conftest.make_pdf`, `make_docx`) rather than committing
  binary fixtures.

## Conventions

- Reference requirement IDs (e.g. FR-8.3) in commits and tests.
- No hardcoded model names. No new dependency without a license check and an entry in
  `THIRD_PARTY_LICENSES.md`.
- Cross-platform: `pathlib`, no shell-specific code in Python.
- Prompts (from M2) go in `backend/app/prompts/*.txt`.
