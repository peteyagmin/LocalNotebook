# CLAUDE.md

`PROJECT_SPEC.md` is the single source of truth. Read its §0 before changing anything. Do not
edit it except to tick milestone boxes in §12. Stop after each milestone for owner testing.

## Current status

M0-M4 accepted. M5 (remaining source types, OCR, web import, YouTube, Discover) implemented,
awaiting owner acceptance. Includes the owner-approved short quiz for small notebooks. Next: M6
(audio overview: TTS, ffmpeg).

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

## M2 additions

- `app/chat/` (new package): `service.stream_answer` is an async generator of events
  (`user_message`, `sources`, `token`, `done`, `suggestions`, `error`) streamed over SSE by
  `POST /notebooks/{id}/chat`. `citations.CitationFilter` removes labels that were not supplied,
  while streaming, so stored text equals shown text. `strip_citations` cleans history replays.
- Retrieval: `retrieval/hybrid.py` (FTS5 BM25 top 20 + vector top 20, RRF k=60, top
  `retrieval_top_k`=8, enabled+ready sources only). `VectorIndex.search` uses sqlite-vec with
  cosine distance (tables from M1 are upgraded once, in place) and falls back to NumPy brute force.
  The `retrieve()` result also feeds `/notebooks/{id}/search` (keyword-only if embeddings fail).
- Prompting (SR-3): `backend/app/prompts/chat_*.txt`, `style_*.txt`. Passages are wrapped in
  delimiters carrying a per-request random nonce. "6 turns of history" is read as 6 user+assistant
  pairs. The refusal sentence is `service.REFUSAL`; no enabled sources never calls the model.
- Stop: `POST /chat/stop` sets an `asyncio.Event` kept in `app.state.chat_stops[notebook_id]`; the
  generator races it against the next token. A dropped client connection also saves the partial
  answer as `stopped`. Assistant messages store a snapshot of cited chunks, so chips survive source
  deletion (shown as removed).
- Frontend: `hooks/useChat`, `components/{ChatPane,AnswerText,CitationChip,SearchBox}`.
  `AnswerText` uses react-markdown with HTML skipped and images dropped; `[n]` becomes a
  `cite:` link rendered as a chip. Viewer state (`ViewTarget`) lives in `NotebookPage`, so chat
  citations and search results both open the viewer with a highlight.
- `evals/run_eval.py` is the QA-4 harness (`--selftest` runs it with an oracle model; covered by
  `test_eval.py`).
- DB writes that may race (index writes) use `BEGIN IMMEDIATE`; `NotebookStore.open()` only checks
  the registry (no directory scan) because it is called on hot paths.

## M3 additions

- Jobs: `jobs.target_id` (renamed from `source_id`) holds the source, artifact, or note id. Kinds:
  `ingest`, `artifact`, `index_note`. `JobRunner.submit_artifact` / `cancel_artifact` /
  `submit_note_index`; interrupted artifacts return to `ready` if they had content, else `failed`.
- Notes (`notes/service.py`): Markdown plus a citation snapshot list; `[n]` markers refer to that list
  and unreferenced citations are pruned on save. Chunks + FTS5 are written synchronously on save,
  vectors by the `index_note` job (`VectorIndex(conn, "notes")`, tables `note_vectors[_fallback]`).
  `merge_notes` renumbers labels (same chunk = one label); `filter_to_valid` drops unsupplied labels.
  Summarize/Combine create a new note and keep the originals; Convert makes pasted-text sources
  with citation markers removed.
- Artifacts (`studio/`): `generate.run_generation` gathers every chunk of enabled+ready sources,
  labels them 1..N, and writes in one call if they fit `context_window_tokens` minus a reserve,
  else map-reduce (`_condense_until_fits`, notes keep their labels, up to 6 rounds). Content lives in
  `artifacts/<id>/content.md`, citations and `source_ids` in the DB. `stale` is computed on read
  (a used source is deleted or disabled). A failed or cancelled regeneration keeps the old version
  (state `ready` plus `error`). Cancel races the pending LLM call (`_race`).
- Export: `studio/markdown_ir.py` (markdown-it-py) feeds `studio/export.py` (python-docx, reportlab).
  Only live citations are listed under "Sources". PDF uses a system Unicode font if found.
- Search is `retrieval/hybrid.search_all` (sources + notes, merged by score; notes deduped per note).
- Frontend: `StudioPane` (create / generated / notes), `ArtifactView`, `NoteEditor` (autosaves 0.8 s
  after typing, flushes on close). The detail view is one absolutely positioned element that is
  either the width of the Studio pane or full width, so Expand does not remount it.

## M4 additions

- Structured artifact kinds `timeline`, `mind_map`, `flashcards` (title "Flashcards & quiz") are
  generated by `studio/structured.py`: each kind is a list of `Part`s (prompt + Pydantic schema);
  flashcards is two parts (cards, quiz) merged into one document. Each part goes through
  `llm.structured.generate_json` (2 retries quoting the validation error, FR-5.10), inside `_race`
  so Cancel works. `clean()` then drops citations to unsupplied passages and items left without
  support, sorts the timeline by `iso_date` (BCE supported), caps the mind map at 4 levels and 120
  nodes. A timeline with no events is a valid result; an empty mind map/flashcards result fails.
- Items cite passages with a `sources: [labels]` list (not inline markers). The artifact keeps the
  citation snapshots for labels used. Content is `artifacts/<id>/content.json`; the API returns
  `format: "json"` and `data` (Markdown kinds return `content`).
- Prompts: `artifact_system_json.txt` (JSON-only rules), `artifact_{timeline,mind_map,flashcards,
  quiz}.txt` (each states the exact JSON shape). Output reserve is larger for these kinds.
- Export (`studio/export.py`, `ALLOWED_FORMATS` per kind, checked by the API): `json`,
  `csv-flashcards`, `csv-quiz` (UTF-8 with BOM), `png` (`studio/mindmap_image.py`, Pillow, whole tree
  expanded), and the timeline reuses md/docx/pdf via `timeline_markdown`.
- Frontend: `TimelineView`, `MindMapView` (@xyflow/react; custom layout; do not set
  `elementsSelectable={false}`, it makes nodes ignore clicks; refits on resize), `FlashcardsView`
  (CSS 3D flip, quiz with score). `onAskChat` sends the node question through `Workspace` ->
  `ChatPane.askRequest`. `src/test/setup.ts` stubs ResizeObserver/DOMMatrixReadOnly for React Flow.

## M5 additions

- Source types: `html`, `epub`, `image` (OCR), `audio` (STT), `web` (fetch + extract), `youtube`
  (captions or local transcription). Migration 0004 adds `sources.url/fetched_at/meta` and
  `source_versions` (archived captures of web sources; files under `sources/<id>/versions/<n>/`).
- URL safety (SR-4), `ingest/safe_fetch.py`: syntax checks, DNS resolution with every address
  checked, connection pinned to the checked IP (Host header + `sni_hostname` so TLS still verifies the
  name), redirects followed by hand and re-checked, 20 MB cap. Used for web import and Discover
  candidates. The user's own SearXNG address is *not* subject to it (it is usually on localhost).
- `ingest/services.py` `Services` bundles fetch, URL check, YouTube backend, search provider and
  models dir; tests substitute fakes (`tests/fakes.py`). `LNB_STT_FACTORY=module:function` swaps the
  speech engine in the parser process (tests, development).
- Parsers run in the sandbox with per-type timeouts (`TIMEOUTS_S`); audio has no memory cap. PDF pages
  under 50 characters are OCR'd (`ingest/ocr.py`); images always. Timed text: `Block.start_s/end_s` ->
  segments -> chunk `location.start_seconds/end_seconds`; `describe_location` prints `12:34`.
- YouTube (`ingest/youtube.py`): caption order = human-made in the UI language (from the browser's
  Accept-Language, saved in `meta.languages`), auto-generated in it, then other languages likewise.
  Metadata failure falls back to a generic title. Downloaded audio is always deleted.
- Speech models (`speech/stt.py`, `speech/models.py`): installed once `models/stt/<name>/model.bin`
  exists (downloads go to `<name>.partial` first); the download endpoint is `async` because it starts an
  asyncio task. Discover (`ingest/discover.py`): search -> fetch+extract (8 parallel, 15 s each) -> LLM
  ranking (`discover_rank.txt`) -> up to 10; nothing is imported.
- Network switches (FR-8.6): `allow_web_import`, `allow_discover`, `allow_model_downloads`
  (enforced in the API and the pipeline) and `GET /capabilities` for the UI's explanations.
- Short quiz: `quiz_count(tokens)` = clamp(tokens/150, 3, 10) and `flashcard_target` = clamp(tokens/60,
  4, 15); the schema and prompt are built per run (`Part.make_schema` / `prompt_vars`).
- Frontend: `AddSourceDialogs`, `useCapabilities`, viewer timestamps and YouTube links
  (`&t=<seconds>s`), `describeLocation` (shared by chips and search), grouped Settings with the
  speech-model download and progress.

## Conventions

- Reference requirement IDs (e.g. FR-8.3) in commits and tests.
- No hardcoded model names. No new dependency without a license check and an entry in
  `THIRD_PARTY_LICENSES.md`.
- Cross-platform: `pathlib`, no shell-specific code in Python.
- Prompts (from M2) go in `backend/app/prompts/*.txt`.
