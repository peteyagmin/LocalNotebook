"""QA-5: create notebook -> upload PDF -> ask a question -> click a citation -> generate a summary
-> export it. Real server, built UI, real browser, fake model."""

import pytest
import requests
from playwright.sync_api import expect

from tests.conftest import make_pdf
from tests.e2e.conftest import TOKEN

pytestmark = pytest.mark.e2e


def configure(origin: str) -> None:
    r = requests.put(
        f"{origin}/api/v1/settings",
        json={"chat_model": "c", "embedding_model": "e", "setup_completed": True},
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": origin},
        timeout=10,
    )
    r.raise_for_status()


def test_smoke(live_server, page, tmp_path):
    configure(live_server)
    page.reload()

    # create a notebook
    page.get_by_role("button", name="New notebook").click()
    page.get_by_label("Notebook name").fill("Smoke test")
    page.get_by_role("button", name="Create").click()
    page.get_by_role("heading", name="Smoke test").wait_for()

    # upload a PDF and wait until it is ready
    pdf = tmp_path / "Zebras.pdf"
    pdf.write_bytes(make_pdf(["Zebras graze on grass in herds across the savanna."]))
    page.get_by_role("button", name="Add source").click()
    page.get_by_role("menuitem", name="Upload files").click()
    page.get_by_label("Choose files").set_input_files(str(pdf))
    expect(page.get_by_role("button", name="Zebras.pdf", exact=True)).to_be_enabled(timeout=20_000)

    # ask a question and open the citation
    page.get_by_label("Ask a question").fill("What do zebras eat?")
    page.get_by_role("button", name="Send").click()
    chip = page.get_by_role("button", name="Citation 1: Zebras.pdf").first
    chip.wait_for(timeout=20_000)
    chip.click()
    viewer = page.get_by_role("dialog", name="Source: Zebras.pdf")
    viewer.wait_for()
    assert viewer.locator("mark").inner_text().strip() != ""
    page.keyboard.press("Escape")
    viewer.wait_for(state="detached")

    # generate a summary, open it and export it
    page.get_by_role("button", name="Summary", exact=True).click()
    artifact = page.get_by_role("region", name="Artifact: Notebook summary")
    artifact.wait_for(timeout=20_000)
    artifact.get_by_role("heading", name="Key points").wait_for(timeout=20_000)
    artifact.get_by_role("button", name="Export").click()
    with page.expect_download() as download:
        artifact.get_by_role("menuitem", name="Markdown (.md)").click()
    saved = tmp_path / "out.md"
    download.value.save_as(saved)
    assert download.value.suggested_filename.endswith(".md")
    assert "Zebras graze on grass" in saved.read_text(encoding="utf-8")
