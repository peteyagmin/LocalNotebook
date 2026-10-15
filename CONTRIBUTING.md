# Contributing

Thanks for helping. This is a small project, so please open an issue to discuss anything large
before writing code.

## Set up

You need [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org) 20+.

```
git clone https://github.com/peteyagmin/localnotebook.git
cd localnotebook
uv sync
cd frontend && npm ci && npm run build
```

`scripts/dev.sh` (or `scripts\dev.ps1`) runs the backend with reload plus the Vite dev server.

## Check your change

```
uv run ruff check
uv run ruff format --check
uv run pytest
cd frontend && npm run lint && npm test
uv run pytest -m e2e        # browser smoke and accessibility tests; needs the built frontend
```

CI runs the same commands on Linux, macOS and Windows. Tests never need a real model: they use a
scripted fake model (`backend/app/llm/fake.py`) and fake speech engines. Tests that need a real model
are marked `llm` and skipped by default. Test documents are built in code rather than committed (the
`tests/fixtures` folder is intentionally empty).

## Rules of the project

The full rules are in [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) section 0 and
[`CLAUDE.md`](CLAUDE.md) (architecture notes). The ones that matter most:

- **Licenses:** only add dependencies under permissive licenses (MIT, BSD, Apache-2.0, ISC, MPL-2.0,
  Unlicense, PSF). **No GPL, LGPL or AGPL libraries.** Separate programs run as subprocesses are
  fine. Record every new dependency in `THIRD_PARTY_LICENSES.md`.
- **No hardcoded model names in code.** Models are chosen by the user in Settings; the only names
  in the repo are the suggested chat and embedding defaults in `backend/app/config/defaults.toml`.
- **Privacy:** no telemetry and no new network use except actions the user starts and can switch off.
- **Cross-platform:** use `pathlib`; no shell-specific code in Python.
- **Prompts** live in `backend/app/prompts/*.txt`.
- **Plain wording** in the UI: no jargon such as "chunk", "embedding" or "RRF" in the main screens.
- **Destructive actions** need confirmation. Everything must work with the keyboard.
- Reference requirement IDs (for example `FR-8.3`) in commits and tests where they apply.
- Update `README.md`, `docs/USER_GUIDE.md` and `CHANGELOG.md` when behaviour changes.

## Pull requests

Keep them focused, include tests, and fill in the checklist in the pull request template.

## Releases

Maintainers: update `version` in `pyproject.toml` and `frontend/package.json` (and the lock files),
update `CHANGELOG.md`, then push a tag like `v1.0.1`. The release workflow builds the web page and
attaches a ready-to-run zip.
