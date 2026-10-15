"""Regenerate the README screenshots (docs/screenshots/*.png).

Starts the real server with a scripted stand-in for the AI model, loads the three fictional sample
documents from evals/docs, and drives the built UI in Chromium. Needs `frontend/dist` (npm run
build) and Playwright's Chromium. Run: `uv run python scripts/screenshots.py`.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402

from app.core.config import FRONTEND_DIST, RuntimeConfig  # noqa: E402
from app.llm.fake import FakeLLMClient  # noqa: E402
from app.main import create_app  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
TOKEN = "screenshot-token"
DOCS = ["valdoria_port.txt", "meridian_battery.md", "hollow_creek_apiary.txt"]
GUIDES = {
    "Valdoria": (
        "A fictional harbor town founded in 1874: its piers, trade in amber kelp, lighthouse and "
        "yearly festival.",
        ["harbor", "trade", "lighthouse"],
    ),
    "Meridian": (
        "A fictional solid-state battery: performance, safety tests, production and warranty.",
        ["energy density", "safety", "warranty"],
    ),
    "Hollow Creek": (
        "Keeper's notes from a fictional apiary: inspections, harvest and winter care.",
        ["hives", "harvest", "winter"],
    ),
}
SUMMARY = (
    "# Notebook summary\n\n"
    "The notebook holds three fictional documents.\n\n"
    "## Key points\n\n"
    "- The Port of Valdoria was founded in 1874 by Henrik Aldane and exports dried amber "
    "kelp [1].\n"
    "- Calder Labs' Meridian-7 battery reaches 410 Wh/kg and is rated for 2,500 cycles [2].\n"
    "- Hollow Creek Apiary keeps 14 hives and averaged 31 kg of honey per hive [3].\n"
)
MIND_MAP = {
    "root": {
        "label": "Sample notebook",
        "sources": [],
        "children": [
            {
                "label": "Port of Valdoria",
                "sources": [1],
                "children": [
                    {"label": "Founded 1874", "sources": [1], "children": []},
                    {"label": "Amber kelp trade", "sources": [1], "children": []},
                ],
            },
            {
                "label": "Meridian-7 battery",
                "sources": [2],
                "children": [
                    {"label": "410 Wh/kg", "sources": [2], "children": []},
                    {"label": "8-year warranty", "sources": [2], "children": []},
                ],
            },
            {
                "label": "Hollow Creek Apiary",
                "sources": [3],
                "children": [
                    {"label": "14 hives", "sources": [3], "children": []},
                    {"label": "Late-August harvest", "sources": [3], "children": []},
                ],
            },
        ],
    }
}


def model(_name, messages) -> str:
    """A stand-in for the AI model that answers from the sample documents."""
    prompt = messages[-1]["content"]
    if "Build a mind map" in prompt:
        return json.dumps(MIND_MAP)
    if "<<<MATERIAL" in prompt:
        return SUMMARY
    if "follow-up questions" in prompt:
        return json.dumps(
            {"questions": ["Where does the ferry go?", "How tall is the lighthouse?"]}
        )
    if "PASSAGES" in prompt:
        return (
            "The Port of Valdoria was founded in 1874 by the merchant Henrik Aldane, who built "
            "the first wooden pier to ship salted fish [1]. Today it is a harbor town of about "
            "18,400 people [1]."
        )
    for key, (summary, topics) in GUIDES.items():
        if key in prompt:
            return json.dumps({"summary": summary, "topics": topics})
    return json.dumps({"summary": "A sample document.", "topics": ["sample"]})


def start_server(data_root: Path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    config = RuntimeConfig(
        data_root=data_root,
        host="127.0.0.1",
        port=port,
        llm_base_url_override=None,
        allowed_origins=frozenset({origin}),
    )
    fake = FakeLLMClient(default_reply=model)
    app = create_app(config, token=TOKEN, llm_factory=lambda _s: fake)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server, thread, origin


def main() -> None:
    if not (Path(FRONTEND_DIST) / "index.html").exists():
        sys.exit("Build the frontend first: cd frontend && npm run build")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        server, thread, origin = start_server(Path(tmp))
        headers = {"Authorization": f"Bearer {TOKEN}", "Origin": origin}
        api = f"{origin}/api/v1"
        requests.put(
            f"{api}/settings",
            json={"chat_model": "chat", "embedding_model": "embed", "setup_completed": True},
            headers=headers,
            timeout=10,
        ).raise_for_status()
        notebook = requests.post(
            f"{api}/notebooks", json={"name": "Sample notebook"}, headers=headers, timeout=10
        ).json()
        for name in DOCS:  # one at a time so the passage numbers follow this order
            requests.post(
                f"{api}/notebooks/{notebook['id']}/sources/files",
                files=[("files", (name, (ROOT / "evals" / "docs" / name).read_bytes()))],
                headers=headers,
                timeout=30,
            ).raise_for_status()
            while any(
                s["state"] in ("queued", "processing")
                for s in requests.get(
                    f"{api}/notebooks/{notebook['id']}/sources", headers=headers, timeout=10
                ).json()
            ):
                time.sleep(0.1)

        browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        exe = Path(browsers, "chromium") if browsers else None
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(exe) if exe and exe.exists() else None)
            page = browser.new_context(viewport={"width": 1440, "height": 880}).new_page()
            page.goto(f"{origin}/#token={TOKEN}")
            page.get_by_role("heading", name="Notebooks").wait_for()
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / "home.png")

            page.goto(f"{origin}/#/notebooks/{notebook['id']}")
            page.get_by_role("heading", name="Sample notebook").wait_for()
            expect(page.get_by_role("button", name="valdoria_port.txt", exact=True)).to_be_enabled()
            page.get_by_label("Ask a question").fill("Who founded the Port of Valdoria, and when?")
            page.get_by_role("button", name="Send").click()
            chip = page.get_by_role("button", name="Citation 1: valdoria_port.txt").first
            chip.wait_for(timeout=20_000)
            page.get_by_text("Where does the ferry go?").wait_for(timeout=20_000)
            page.get_by_role("button", name="Summary", exact=True).click()
            region = page.get_by_role("region", name="Artifact: Notebook summary")
            region.get_by_role("heading", name="Key points").wait_for(timeout=20_000)
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / "notebook.png")
            page.keyboard.press("Escape")
            page.get_by_role("button", name="Mind map", exact=True).click()
            page.get_by_role("region", name=re.compile("^Artifact:")).wait_for()
            page.get_by_role("button", name="Expand").click()
            page.wait_for_timeout(1500)
            page.screenshot(path=OUT / "mind-map.png")
            page.keyboard.press("Escape")

            chip.click()
            page.get_by_role("dialog", name="Source: valdoria_port.txt").wait_for()
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / "citation.png")
            page.keyboard.press("Escape")

            page.goto(f"{origin}/#/settings")
            page.get_by_role("heading", name="Settings").wait_for()
            page.get_by_label("Theme").select_option("dark")
            page.get_by_role("button", name="Save").click()
            page.wait_for_timeout(500)
            page.screenshot(path=OUT / "settings-dark.png")
            browser.close()
        server.should_exit = True
        thread.join(timeout=10)
    print("Wrote", ", ".join(sorted(f.name for f in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
