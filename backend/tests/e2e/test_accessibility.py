"""M7 accessibility pass: run axe-core (WCAG 2 A/AA rules, including colour contrast) in a real
browser on the main screens, in both themes."""

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.conftest import make_pdf
from tests.e2e.test_smoke import configure

pytestmark = pytest.mark.e2e

AXE = Path(__file__).resolve().parents[3] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]


def violations(page) -> list[str]:
    page.add_script_tag(content=AXE.read_text(encoding="utf-8"))
    result = page.evaluate(
        "tags => axe.run(document, { runOnly: { type: 'tag', values: tags } })", TAGS
    )
    return [
        f"{v['id']} ({v['impact']}): {v['help']} -> "
        + "; ".join(
            n["target"][-1] if isinstance(n["target"][-1], str) else "?" for n in v["nodes"][:4]
        )
        for v in result["violations"]
    ]


def set_theme(page, theme: str) -> None:
    page.evaluate(f"document.documentElement.dataset.theme = '{theme}'")


@pytest.mark.skipif(not AXE.exists(), reason="run `npm install` in frontend/ for axe-core")
def test_main_screens_have_no_accessibility_violations(live_server, page, tmp_path):
    configure(live_server)
    page.reload()
    found: dict[str, list[str]] = {}

    def check(label: str) -> None:
        for theme in ("light", "dark"):
            set_theme(page, theme)
            problems = violations(page)
            if problems:
                found[f"{label} / {theme}"] = problems

    page.get_by_role("button", name="New notebook").click()
    page.get_by_label("Notebook name").fill("A11y")
    page.get_by_role("button", name="Create").click()
    page.get_by_role("heading", name="A11y").wait_for()
    check("empty notebook")

    pdf = tmp_path / "Zebras.pdf"
    pdf.write_bytes(make_pdf(["Zebras graze on grass in herds across the savanna."]))
    page.get_by_role("button", name="Add source").click()
    check("add-source menu")
    page.get_by_role("menuitem", name="Upload files").click()
    page.get_by_label("Choose files").set_input_files(str(pdf))
    expect(page.get_by_role("button", name="Zebras.pdf", exact=True)).to_be_enabled(timeout=20_000)
    page.get_by_label("Ask a question").fill("What do zebras eat?")
    page.get_by_role("button", name="Send").click()
    chip = page.get_by_role("button", name="Citation 1: Zebras.pdf").first
    chip.wait_for(timeout=20_000)
    check("chat answer")
    chip.click()
    page.get_by_role("dialog", name="Source: Zebras.pdf").wait_for()
    check("source viewer")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Summary", exact=True).click()
    page.get_by_role("region", name="Artifact: Notebook summary").get_by_role(
        "heading", name="Key points"
    ).wait_for(timeout=20_000)
    check("summary")
    page.keyboard.press("Escape")  # closes the artifact (the buttons beneath it become usable)
    for button in ("Timeline", "Mind map", "Flashcards & quiz"):
        page.get_by_role("button", name=button, exact=True).click()
        page.get_by_role("region", name=re.compile("^Artifact: ")).get_by_role(
            "button", name="Export"
        ).first.wait_for(timeout=20_000)
        page.wait_for_timeout(1500)  # let the generated content render
        check(button)
        page.keyboard.press("Escape")
    page.get_by_role("button", name="New note").click()
    page.get_by_role("region", name="Note editor").wait_for()
    check("note editor")

    page.goto(f"{live_server}/#/settings")
    page.get_by_role("heading", name="Settings").wait_for()
    check("settings")
    page.goto(f"{live_server}/#/")
    page.get_by_role("heading", name="Notebooks").wait_for()
    check("home")

    assert not found, json.dumps(found, indent=2)
