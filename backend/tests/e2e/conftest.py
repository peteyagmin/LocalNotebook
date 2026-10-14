"""Fixtures for the end-to-end smoke test (QA-5): real server and built UI, fake model."""

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.core.config import FRONTEND_DIST, RuntimeConfig
from app.llm.fake import FakeLLMClient
from app.main import create_app
from tests.helpers import brain

TOKEN = "e2e-token"


@pytest.fixture
def live_server(tmp_path):
    """Serve the built frontend and API on a free local port. Yields the base URL."""
    if not (Path(FRONTEND_DIST) / "index.html").exists():
        pytest.skip("Build the frontend first: cd frontend && npm run build")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    config = RuntimeConfig(
        data_root=tmp_path,
        host="127.0.0.1",
        port=port,
        llm_base_url_override=None,
        allowed_origins=frozenset({origin}),
    )
    fake = FakeLLMClient(default_reply=brain)
    app = create_app(config, token=TOKEN, llm_factory=lambda _s: fake)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the server did not start"
    yield origin
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(live_server):
    from playwright.sync_api import sync_playwright

    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    executable = Path(browsers, "chromium") if browsers else None
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=str(executable) if executable and executable.exists() else None
        )
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()
        page.goto(f"{live_server}/#token={TOKEN}")
        yield page
        browser.close()
