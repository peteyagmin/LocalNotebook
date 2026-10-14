# CLAUDE.md

`PROJECT_SPEC.md` is the single source of truth. Read its §0 before changing anything. Do not
edit it except to tick milestone boxes in §12. Stop after each milestone for owner testing.

## Current status

M0 (skeleton) implemented, awaiting owner acceptance. Next: M1.

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

## Conventions

- Reference requirement IDs (e.g. FR-8.3) in commits and tests.
- No hardcoded model names. No new dependency without a license check and an entry in
  `THIRD_PARTY_LICENSES.md`.
- Cross-platform: `pathlib`, no shell-specific code in Python.
- Prompts (from M2) go in `backend/app/prompts/*.txt`.
