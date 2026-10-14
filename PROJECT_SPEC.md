# PROJECT\_SPEC: LocalNotebook

*Local, source-grounded research notebook. A clean-room reimplementation inspired by the publicly observable behavior of Google NotebookLM.*

**Version:** 0.3 (implementation-ready for Claude Code)
**Date:** October 2026
**Owner:** Peter Yagmin

\---

## 0\. Instructions for Claude Code (read first)

This document is the single source of truth for what to build. Follow these rules for the whole project:

1. **Do not add features, settings, or UI elements that are not in this spec.** If something seems missing or a better approach exists, say so in your summary as a suggestion. Do not implement it.
2. **If a requirement is ambiguous, ask** before implementing. Do not guess on anything that affects data formats, the API, or user-visible behavior.
3. **Requirement keywords:** **MUST** = required. **SHOULD** = expected unless there is a stated reason not to. **MAY** = optional, only if trivial.
4. **Reference requirement IDs** (e.g. `FR-3.2`) in commit messages, code comments where helpful, and tests.
5. **Keep docs current.** At the end of each milestone, update `README.md` (setup and usage) and `CLAUDE.md` (architecture notes, conventions, current status). Do not edit this spec except to tick milestone checkboxes in §12. Propose any spec changes to the owner instead.
6. **Clean-room rules (§1.3) are absolute.**
7. **Licensing:** only add dependencies with permissive licenses (MIT, BSD, Apache-2.0, ISC, MPL-2.0, Unlicense, PSF). **Do not add GPL, LGPL, or AGPL Python/JS libraries.** Separate programs called over HTTP or as a subprocess (Ollama, ffmpeg, Tesseract, SearXNG) are allowed. Before adding any dependency, check its current license and record it in `THIRD\\\_PARTY\\\_LICENSES.md`. If the license is unclear, ask.
8. **No hardcoded model names** in application code. All model identifiers come from configuration (§8).
9. **Cross-platform:** code MUST run on Windows 10/11, macOS (Apple Silicon), and Linux. Use `pathlib`, avoid shell-specific commands, and never assume POSIX paths.

\---

## 1\. Purpose \& Scope

LocalNotebook is an application that runs on the user's own computer. The user collects documents into **notebooks**, then chats with, summarizes, and transforms those documents using AI models that run **locally**. Every AI answer MUST be **grounded in the user's sources** and carry **inline citations** that link to the exact passages used.

### 1.1 Goals

* Source-grounded Q\&A with verifiable, clickable citations.
* Fully offline operation after setup, except for actions the user triggers that need the internet (§7).
* Generated outputs: summaries, briefings, study guides, FAQs, timelines, mind maps, flashcards/quizzes, and two-host audio overviews.
* Usable on consumer hardware (§9).

### 1.2 Non-Goals (v1). Do not build these:

* Multi-user accounts, collaboration, or cloud sync.
* Mobile clients.
* Training or fine-tuning models.
* Video overview generation.
* Installer packaging (a single launch command is sufficient for v1).

### 1.3 Clean-Room Constraints

* Work only from this spec and general public knowledge. Do not use, imitate, or reproduce Google source code, internal prompts, model weights, UI artwork, icons, or copy.
* Do not use Google trademarks ("NotebookLM", "Gemini", Google logos) anywhere in the product, code identifiers, or UI text.
* All prompts used by the app MUST be original and live in `backend/app/prompts/` as plain-text template files.

\---

## 2\. Core Concepts

|Term|Definition|
|-|-|
|**Notebook**|A named project container holding sources, chats, notes, and artifacts. Stored as one folder on disk.|
|**Source**|An imported document (file, webpage snapshot, video transcript, or pasted text). Its content does not change after ingestion. Re-fetching a web source creates a new version (FR-2.9).|
|**Chunk**|A segment of a source's text with location metadata (page, heading, character offsets, or timestamp). The unit of retrieval and citation.|
|**Citation**|A numbered marker in an AI response that links to one chunk.|
|**Note**|User-written or user-saved Markdown content in a notebook.|
|**Artifact**|AI-generated output (summary, study guide, audio overview, etc.) saved to the notebook.|
|**Job**|A background task (ingestion, artifact generation, audio synthesis) with status and progress.|

\---

## 3\. Technology Stack (decided)

These choices are fixed for v1. Do not substitute without asking.

|Layer|Choice|Notes|
|-|-|-|
|Backend language|Python 3.11+|Managed with `uv` (`pyproject.toml` + lockfile).|
|Web framework|FastAPI + Uvicorn|Binds to `127.0.0.1` only.|
|Frontend|React + TypeScript, built with Vite|Styling with Tailwind CSS. Production build is served by the backend as static files.|
|App shape|Local web server + browser UI|One command starts the server and opens the default browser (§11.3).|
|Metadata storage|SQLite, one database file per notebook, plus one global app database|Use the standard `sqlite3` module or SQLAlchemy Core. Schema migrations via numbered SQL files.|
|Keyword search|SQLite FTS5||
|Vector search|`sqlite-vec` extension in the same per-notebook database|If it can't load on a platform, fall back to brute-force cosine similarity with NumPy and log a warning.|
|LLM + embeddings runtime|Ollama, accessed through its OpenAI-compatible HTTP API|Also works with any other OpenAI-compatible local server (FR-8.4).|
|PDF text|`pypdfium2`|Do not use PyMuPDF (AGPL).|
|OCR|Tesseract (external program) via `pytesseract`|Used for scanned PDF pages and images.|
|DOCX / HTML / EPUB|`python-docx`; `trafilatura` for webpages and HTML; EPUB parsed as a ZIP of XHTML with the same HTML extractor|Verify licenses per rule 8.|
|Speech-to-text|`faster-whisper`|Used for audio files and caption-less videos.|
|Text-to-speech|Kokoro (local)|Used behind a `TTSEngine` interface so it can be swapped later.|
|Audio processing|ffmpeg (external program)|Concatenation, normalization, MP3 export.|
|YouTube captions|`youtube-transcript-api`|Metadata via `yt-dlp` (used as a library, metadata only, unless FR-2.10 fallback is enabled).|
|Web search (Discover)|Provider interface. v1 ships a SearXNG provider (user's self-hosted instance URL)|No provider is configured by default.|
|Background jobs|In-process async worker pool, job state stored in SQLite|Jobs left unfinished by a crash are marked `interrupted` on restart and can be retried.|
|Mind map rendering|`react-flow` (or equivalent MIT-licensed library)||
|Testing|`pytest` (backend), `vitest` + React Testing Library (frontend), Playwright for end-to-end smoke tests||
|Linting / formatting|`ruff` (Python), ESLint + Prettier (TS)||

\---

## 4\. Functional Requirements

### 4.1 Notebook Management

* **FR-1.1** Create, rename, duplicate, delete (with confirmation), and list notebooks. The home screen shows notebooks as cards sorted by last-modified.
* **FR-1.2** Each notebook is a self-contained folder on disk (§6).
* **FR-1.3** Export a notebook as a single `.lnb` file (a ZIP of the notebook folder plus a manifest). Import the same format. Importing never overwrites an existing notebook; on an ID conflict it imports as a copy.
* **FR-1.4** Show notebook metadata: source count, created and modified dates, storage size on disk.

### 4.2 Source Ingestion

* **FR-2.1** Supported inputs: PDF, DOCX, TXT, Markdown, HTML, EPUB, pasted text, webpage URL, YouTube URL, audio files (MP3, WAV, M4A), and images (PNG, JPG).
* **FR-2.2** For PDFs, any page with less than 50 characters of extractable text is OCR'd. Images are always OCR'd.
* **FR-2.3** Ingestion pipeline (one job per source): extract text → normalize whitespace and encoding → chunk → embed → write to FTS5 and vector index → generate source guide (FR-2.6) → mark `ready`.

  * **Chunking:** target \~500 tokens per chunk, \~80-token overlap. Split on heading or paragraph boundaries where possible; never split mid-sentence unless a single sentence exceeds the target.
  * **Every chunk MUST store:** source ID, ordinal, text, and location (page number for PDFs; heading path for DOCX/MD/HTML/EPUB; start/end seconds for audio/video; character offsets for all types).
* **FR-2.4** Source states: `queued`, `processing`, `ready`, `failed`. The sources pane shows the state and a progress indicator. Failed sources stay in the list with the error message and a **Retry** action.
* **FR-2.5** Limits (configurable, global settings): 50 sources per notebook; 200 MB per uploaded file. Exceeding a limit shows a clear error before any work starts.
* **FR-2.6** After ingestion, generate a **source guide** for each source: a 3–5 sentence summary and 3–8 key topics. It is shown when the user opens the source.
* **FR-2.7** Each source has an enable/disable checkbox. Only enabled sources are used for chat and artifact generation. A "select all / none" control is provided. New sources are enabled by default.
* **FR-2.8** Source viewer: shows the extracted text with location markers (page numbers or timestamps). Clicking a citation opens the viewer, scrolls to the cited chunk, and highlights it.
* **FR-2.9 Webpage import:** The user pastes one or more URLs (one per line). Each page is fetched once, its main content extracted with `trafilatura`, and stored with its URL, page title, and fetch timestamp. If extraction yields under 200 characters, the import fails with a "could not extract readable content" message. **Refresh from web** re-fetches and creates a new source version; the previous version is kept and the new one becomes active.
* **FR-2.10 YouTube import:** The user pastes a video URL.

  1. Fetch captions with `youtube-transcript-api`, preferring human-made captions over auto-generated, and the UI language over other languages.
  2. If no captions exist **and** the setting *"Transcribe videos without captions"* is on (default **off**), download the audio only with `yt-dlp`, transcribe it with `faster-whisper`, then delete the downloaded audio. The setting's description MUST tell the user they are responsible for complying with the platform's terms of service.
  3. If no captions exist and the setting is off, fail with: *"This video has no captions. Enable 'Transcribe videos without captions' in Settings to transcribe it locally."*
  4. Store the transcript with timestamps plus metadata: title, channel, description, URL, duration.
  5. Chunk on timestamp boundaries. Citations display a timestamp (e.g. `12:34`). In the viewer, each cited chunk has an "Open in browser at this time" link (`\\\&t=<seconds>s`).
* **FR-2.11 Discover sources:** The user enters a topic. The app queries the configured search provider for up to 30 results, fetches and extracts each candidate (in parallel, 15-second timeout each), and asks the local LLM to rank them by relevance to the topic. It shows up to 10 suggestions, each with title, URL, and a one-sentence relevance note. The user ticks which to import; selected items go through FR-2.9 or FR-2.10. **Nothing is imported automatically.** If no search provider is configured, the Discover button opens Settings with an explanation.
* **FR-2.12** Web-derived sources show a type icon (web or video), the original URL, and the capture date.

### 4.3 Grounded Chat

* **FR-3.1 Retrieval:** For each user question, run hybrid retrieval over **enabled sources only**: top 20 by vector similarity + top 20 by FTS5 BM25, merged with reciprocal rank fusion. Pass the top 8 chunks to the model (configurable). Include the last 6 chat turns for conversational context.
* **FR-3.2 Citations:**

  * Retrieved chunks are given to the model labeled `\\\[1]`…`\\\[n]`. The model is instructed to cite with these labels after each claim.
  * After generation, the backend maps each label to its chunk ID and **drops any citation label that wasn't in the provided set**.
  * The UI renders citations as small numbered chips. Hovering shows the source name and a short excerpt. Clicking opens the source viewer at that chunk (FR-2.8).
  * Citations are stored with the message so they still work after a restart.
* **FR-3.3 Out-of-source questions:** If the retrieved chunks don't support an answer, the assistant MUST say the sources don't cover it. There is no general-knowledge mode in v1.
* **FR-3.4** Chat history persists per notebook. A "Clear chat" action (with confirmation) deletes it.
* **FR-3.5** After each answer, show up to 3 suggested follow-up questions as clickable chips. When chat is empty, show 3 starter questions generated from the source guides.
* **FR-3.6** Each assistant message has a **Save to note** action that preserves citations.
* **FR-3.7** Per-notebook chat settings: response style (Default / Concise / Detailed / Learning guide) and a free-text custom instruction (max 1,000 characters).
* **FR-3.8** Responses stream token by token over Server-Sent Events. A **Stop** button cancels generation; the partial answer is kept and marked as stopped.
* **FR-3.9** If the LLM runtime is unreachable, the chat shows a clear error with a link to Settings rather than failing silently.

### 4.4 Notes

* **FR-4.1** Create, edit, and delete notes. Editor is Markdown with a live preview. Saved notes display citations as chips that still link to their sources.
* **FR-4.2** Select multiple notes and run: **Summarize**, **Combine into one note**, or **Convert to source**.
* **FR-4.3** "Convert to source" creates a new pasted-text source from the note, which is then ingested normally.

### 4.5 Generated Artifacts ("Studio")

Each artifact is generated from the **enabled** sources, saved to the notebook with the list of source IDs it used, and can be regenerated. Every generator accepts an optional focus prompt (topic, audience, length; max 500 characters).

|ID|Artifact|Output format|Requirements|
|-|-|-|-|
|FR-5.1|Notebook summary|Markdown|1–3 paragraphs plus key points, with citations.|
|FR-5.2|Briefing document|Markdown|Executive summary, key themes, important details, notable quotes, with citations.|
|FR-5.3|Study guide|Markdown|Key concepts, 10 short-answer questions with answer key, glossary.|
|FR-5.4|FAQ|Markdown|8–15 Q\&A pairs with citations.|
|FR-5.5|Timeline|JSON → rendered list|Dated events in chronological order, each with a citation; plus a cast of key people/entities. Show "No dated events found" if none.|
|FR-5.6|Mind map|JSON tree → interactive graph|Max depth 4. Nodes collapse/expand. Clicking a node sends *"Tell me about {node} in the context of {parent path}"* to chat.|
|FR-5.7|Flashcards \& quiz|JSON|Flashcards (front/back, flip animation, next/previous). Quiz: 10 multiple-choice questions, 4 options each, with explanation and citation; shows score at the end.|
|FR-5.8|Audio overview|MP3 + transcript JSON|See §4.6.|

* **FR-5.9 Large notebooks:** If the enabled sources don't fit in the model's context window, use a map-reduce approach: summarize each source (or group of chunks) first, then generate the artifact from those summaries while keeping chunk IDs so citations stay valid.
* **FR-5.10 Structured outputs:** JSON artifacts MUST be validated against a Pydantic schema. On invalid JSON, retry up to 2 times with the validation error included in the prompt, then fail the job with a clear message.
* **FR-5.11 Export:** Markdown artifacts → `.md`, `.docx`, `.pdf`; audio → `.mp3`; mind map → `.png` and `.json`; flashcards/quiz → `.csv` and `.json`.
* **FR-5.12** Generation runs as a background job with progress and **Cancel**. The user can keep chatting while a job runs.
* **FR-5.13** If a source used by an artifact is deleted or disabled after generation, the artifact shows a "Sources changed — regenerate?" badge.

### 4.6 Audio Overview

* **FR-6.1 Pipeline** (each stage reports progress):

  1. **Outline:** build a topic outline from the enabled sources (using FR-5.9 if needed).
  2. **Script:** write a dialogue between two hosts ("Host A" and "Host B") as JSON: a list of `{speaker, text, chunk\\\_ids\\\[]}` turns. The hosts explain, question, and react naturally, and stick to what the sources say.
  3. **Synthesis:** synthesize each turn with the TTS voice assigned to its speaker (two distinct voices, configurable in Settings).
  4. **Assembly:** concatenate with short natural pauses (250–500 ms), normalize loudness with ffmpeg, export MP3. Record each turn's start/end time in the transcript JSON.
* **FR-6.2 Options:** Length: Short (\~5 min), Default (\~10 min), Long (\~20 min). Format: Deep dive, Brief, Debate, Critique. Plus the optional focus prompt.
* **FR-6.3 Player:** play/pause, seek bar, ±15 s skip, speed (0.75×–2×), and a transcript that highlights the current turn and allows click-to-seek.
* **FR-6.4 Script editing:** The script is viewable and editable as a list of turns (edit text, change speaker, delete, reorder). **Re-synthesize** rebuilds the audio from the edited script without regenerating it.
* **FR-6.5** *(v1.x, not in v1)* Interactive mode where the user can interrupt with questions.

### 4.7 Search

* **FR-7.1** A search box in each notebook searches source text and notes (hybrid retrieval). Results show source name, location, and a highlighted excerpt; clicking opens the source viewer.

### 4.8 Settings \& Model Management

* **FR-8.1** Configurable model roles: `chat\\\_model`, `embedding\\\_model`, `stt\\\_model`, `tts\\\_voice\\\_a`, `tts\\\_voice\\\_b`. Shown in a Settings page with a "Test connection" button for the LLM runtime.
* **FR-8.2** Settings shows which models are installed in Ollama and the Ollama command to pull a missing one. The app does not download LLMs itself in v1. STT and TTS models download on first use with a progress indicator and the user's confirmation.
* **FR-8.3** On first launch, a setup wizard checks for: Ollama reachable, required models present, Tesseract installed, ffmpeg installed. Each check shows pass/fail and how to fix it. Features whose dependency is missing are disabled with an explanation, not hidden.
* **FR-8.4** LLM endpoint is configurable (base URL + optional API key) for any OpenAI-compatible server. A non-loopback URL MUST show a persistent warning banner: *"AI requests are being sent to {host}."*
* **FR-8.5** Changing `embedding\\\_model` marks all notebooks' indexes as stale and offers **Rebuild index** per notebook (DR-3).
* **FR-8.6** Network settings (all individually toggleable): webpage/video import, Discover sources, STT/TTS model downloads.

\---

## 5\. User Interface

### 5.1 Layout

* **Home:** notebook cards, **New notebook**, **Import notebook**, Settings link.
* **Notebook view:** three resizable, collapsible panes.

  1. **Sources (left):** add-source menu (Upload files, Paste text, Website, YouTube, Discover), source list with checkboxes, status, and type icons.
  2. **Chat (center):** messages with citation chips, suggested questions, input box with Send/Stop, chat settings (FR-3.7).
  3. **Studio (right):** one button per artifact type (FR-5.x), list of generated artifacts with status, notes list, and the audio player when an audio overview is open.
* **Source viewer:** slides over the chat pane; closes with Esc.
* Artifacts open in the Studio pane, with an "expand" option to view them full-width.

### 5.2 General

* Light and dark themes, following the OS by default.
* Keyboard: `Enter` sends, `Shift+Enter` newline, `Esc` closes overlays, `Ctrl/Cmd+K` focuses search.
* Accessibility: all controls keyboard-reachable, ARIA labels on icon buttons, visible focus states, base font size adjustable in Settings.
* All destructive actions require confirmation.
* Use plain, user-facing wording. No internal jargon such as "chunk", "embedding", or "RRF" in the main UI (it is fine in Settings and error details).

\---

## 6\. Data \& Storage

### 6.1 Directory layout

Data root defaults to the OS-standard user-data folder (via `platformdirs`) and is configurable.

```
<data\\\_root>/
  app.db                      # global settings, notebook registry
  models/                     # downloaded STT/TTS models
  notebooks/<notebook\\\_id>/
    notebook.db               # sources, chunks, FTS5, vectors, chats, notes, artifacts, jobs
    sources/<source\\\_id>/
      original.<ext>          # unmodified uploaded file (if any)
      extracted.json          # normalized text + location metadata
    artifacts/<artifact\\\_id>/
      content.(md|json)
      audio.mp3               # audio overviews only
      transcript.json         # audio overviews only
```

### 6.2 Main tables (notebook.db)

`sources`, `source\\\_versions`, `chunks`, `chunks\\\_fts` (FTS5), `chunk\\\_vectors` (sqlite-vec), `chat\\\_messages` (with `citations` JSON), `notes`, `artifacts`, `jobs`, `schema\\\_version`.
IDs are UUIDv7 strings. Timestamps are ISO 8601 UTC.

### 6.3 Data rules

* **DR-1** All user data lives under `<data\\\_root>`.
* **DR-2** Original files are kept unmodified.
* **DR-3** The search index can be fully rebuilt from `extracted.json` files.
* **DR-4** Schema version is stored; migrations run automatically at startup, with a backup of `notebook.db` taken first.
* **DR-5** Deleting a source removes its chunks, vectors, and files, and triggers FR-5.13 for dependent artifacts. Citations pointing to deleted chunks render as "source removed".
* **DR-6** All database writes use transactions. A crash MUST NOT leave a notebook unreadable.

\---

## 7\. Privacy \& Security

* **SR-1** No outbound network requests except: the configured LLM endpoint; user-triggered URL/video import; Discover searches; STT/TTS model downloads (with confirmation). **No telemetry, analytics, or update checks.**
* **SR-2** The server binds to `127.0.0.1` only. The API requires a random per-launch token, which the launcher passes to the browser on startup. Reject requests with a mismatched `Origin` header.
* **SR-3** Treat all source content as untrusted:

  * Parse files in a worker with a timeout and memory limit; a parser crash fails only that source.
  * In prompts, wrap source text in clearly marked delimiters and instruct the model to treat it as reference material, never as instructions.
  * Render all model output and source text as sanitized Markdown (no raw HTML, no scripts).
* **SR-4** URL fetching: only `http`/`https`; refuse `localhost`, private IP ranges, and `file://` to prevent the app being used to reach local services. Max response size 20 MB.
* **SR-5** Imported web sources work offline after import.
* *(v1.x)* Optional encryption of the data folder.

\---

## 8\. Configuration

* Global settings live in `app.db` and are edited through the Settings page.
* Defaults live in `backend/app/config/defaults.toml`. Model identifiers are placeholders the owner fills in during setup; the setup wizard (FR-8.3) prompts for any that are missing.
* Environment variable overrides (prefix `LNB\\\_`) are supported for `data\\\_root`, `host\\\_port`, and `llm\\\_base\\\_url` for development.

\---

## 9\. Hardware Tiers \& Performance Targets

|Tier|Example hardware|Expectation|
|-|-|-|
|Minimum|16 GB RAM, recent 8-core CPU, no GPU|All features work; chat and audio are slow.|
|Recommended|32 GB RAM + GPU with 12 GB+ VRAM, or Apple Silicon with 32 GB|Meets the targets below.|

Targets on **recommended** hardware (to be validated by the owner; adjust after real testing):

|Metric|Target|
|-|-|
|First chat token|≤ 3 s with 50 enabled sources|
|Ingest a 100-page text PDF|≤ 60 s|
|\~10-minute audio overview|≤ 10 min end-to-end|
|UI responsiveness|No UI freeze during any background job|

\---

## 10\. Quality \& Testing

* **QA-1 Unit tests** for: every parser, chunker (boundary and overlap rules), retrieval merge, citation mapping/stripping (FR-3.2), JSON schema validation and retry (FR-5.10), URL safety checks (SR-4), and migrations.
* **QA-2 LLM-independent tests:** All tests MUST run without a real model, using a fake LLM client that returns scripted responses. Real-model tests are marked `@pytest.mark.llm` and skipped by default.
* **QA-3 Fixtures:** `tests/fixtures/` holds small, self-created or public-domain documents (text PDF, scanned PDF, DOCX, EPUB, HTML, MP3, PNG). Do not commit copyrighted material.
* **QA-4 Grounding evaluation** (`evals/`, run manually with a real model): a fixed document set with \~30 questions, half answerable and half not. Report: citation support rate (target ≥ 95%), correct-refusal rate on unanswerable questions (target ≥ 90%). Include a script that prints a results table.
* **QA-5 End-to-end smoke test** (Playwright, fake LLM): create notebook → upload PDF → ask a question → click a citation → generate a summary → export it.
* **QA-6** CI-ready commands: `uv run pytest`, `npm test`, `npm run lint`, `uv run ruff check`.

\---

## 11\. Repository Structure \& Developer Workflow

### 11.1 Layout

```
/backend
  app/
    api/            # FastAPI routers (notebooks, sources, chat, notes, artifacts, jobs, settings)
    core/           # config, db, migrations, security
    ingest/         # parsers, ocr, chunker, web, youtube, discover
    retrieval/      # embeddings, fts, vectors, hybrid
    llm/            # OpenAI-compatible client, fake client, prompt loader
    studio/         # artifact generators, audio pipeline
    speech/         # stt, tts interfaces + implementations
    jobs/           # worker pool, job state
    prompts/        # \\\*.txt prompt templates (original)
  migrations/
  tests/
/frontend
  src/ (components, pages, api client, hooks)
/evals
/scripts            # launcher, dev helpers
README.md
CLAUDE.md
PROJECT\\\_SPEC.md
THIRD\\\_PARTY\\\_LICENSES.md
```

### 11.2 API conventions

* REST + JSON under `/api/v1/…`; streaming via SSE (`text/event-stream`) for chat and job progress.
* Errors: `{ "error": { "code": "...", "message": "user-readable text" } }` with appropriate HTTP status.
* The OpenAPI schema generated by FastAPI is the API reference; the frontend API client is typed against it.

### 11.3 Running

* `scripts/run` (with `.ps1` and `.sh` variants) builds the frontend if needed, starts the backend on a free local port, and opens the browser with the session token.
* `scripts/dev` runs backend with reload and the Vite dev server.

\---

## 12\. Milestones

Complete in order. **Stop after each milestone for owner testing.** Tick boxes only when all acceptance criteria pass.

* \[x] **M0 — Skeleton**
Repo layout, tooling, `scripts/run` and `scripts/dev`, health endpoint, empty three-pane UI, settings storage, setup wizard checks (FR-8.3), fake LLM client, CI commands, `README.md`, `CLAUDE.md`, `THIRD\\\_PARTY\\\_LICENSES.md`.
*Accept:* app launches with one command on the owner's machine; wizard correctly reports Ollama/Tesseract/ffmpeg presence; all tests pass.
* \[x] **M1 — Notebooks \& core ingestion**
FR-1.1, FR-1.2, FR-1.4; FR-2.1 (PDF, DOCX, TXT, MD, pasted text only), FR-2.3–FR-2.8; DR-1–DR-6.
*Accept:* upload each supported type and view its extracted text; enable/disable works; failures show retry; restart preserves everything.
* \[x] **M2 — Grounded chat**
FR-3.1–FR-3.9, FR-7.1, SR-3 prompt hardening.
*Accept:* answers stream with working citation chips that open the right passage; unanswerable questions are declined; stop works; QA-4 eval script runs and prints results.
* \[ ] **M3 — Notes \& text artifacts**
FR-4.1–FR-4.3; FR-5.1–FR-5.4, FR-5.9–FR-5.13 (Markdown artifacts).
*Accept:* each artifact generates, cites, exports to md/docx/pdf, and shows the stale badge after a source is removed.
* \[ ] **M4 — Structured artifacts**
FR-5.5–FR-5.7 with schema validation and retry.
*Accept:* timeline, mind map (click-to-chat works), flashcards and quiz render and export.
* \[ ] **M5 — Remaining source types \& web**
FR-2.1 (HTML, EPUB, images, audio), FR-2.2 OCR, FR-2.9–FR-2.12, SR-4, FR-8.6.
*Accept:* webpage and YouTube imports work with timestamped citations; caption-less video fails with the correct message when the setting is off and transcribes when on; Discover returns ranked suggestions from a configured SearXNG instance and imports only selected items; private-IP URLs are refused.
* \[ ] **M6 — Audio overview**
FR-6.1–FR-6.4.
*Accept:* all lengths/formats generate playable MP3s with synced transcript; editing the script and re-synthesizing works without regenerating the script.
* \[ ] **M7 — Export/import \& polish**
FR-1.3, FR-8.5, theming, keyboard shortcuts, accessibility pass, QA-5 smoke test, performance check against §9.
*Accept:* a notebook exported on one machine imports cleanly on another; smoke test passes; owner signs off on v1.0.

\---

## 13\. Decisions Log (resolved from v0.2 open questions)

|Question|Decision|
|-|-|
|Desktop app vs. local server + browser?|Local server + browser UI for v1 (§3). Native packaging deferred.|
|Whole-notebook artifacts exceeding context?|Map-reduce with preserved chunk IDs (FR-5.9).|
|General-knowledge mode?|Not in v1 (FR-3.3).|
|Which TTS/STT?|Kokoro and faster-whisper behind swappable interfaces.|
|Bundled models?|None bundled. LLMs pulled via Ollama by the user; STT/TTS downloaded on first use with confirmation.|
|Sharing notebooks?|Via `.lnb` export/import only (FR-1.3).|

### Still open (owner to decide; Claude Code should not decide these)

1. Default `chat\\\_model` and `embedding\\\_model` values for `defaults.toml`.
2. Final product name (replace "LocalNotebook" throughout if changed).
3. Whether v1.x adds interactive audio (FR-6.5) or cross-notebook search first.

