"""Performance check against spec §9. Run: `uv run python evals/perf_check.py`.

It measures what the app itself costs, with a fake model that answers instantly: parsing, chunking
and indexing a 100-page PDF, retrieval across 50 sources, time to the first streamed token, and how
long a trivial request waits while ingestion runs (UI responsiveness). Time spent in the real chat,
embedding, speech and TTS models is NOT included: the owner measures that on the recommended
hardware (the targets in §9 are end to end).
"""

from __future__ import annotations

import io
import json
import socket
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
import uvicorn
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import RuntimeConfig  # noqa: E402
from app.llm.fake import FakeLLMClient  # noqa: E402
from app.main import create_app  # noqa: E402

TOKEN = "perf-token"
WORDS = (
    "zebras graze savanna grass herds river lighthouse harbour founder trade winter archive "
    "census map charter market storm bridge canal guild ledger orchard meadow quarry"
).split()


def make_pdf(pages: int) -> bytes:
    """A text PDF with `pages` pages of about 450 words each."""
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    for page in range(pages):
        text = pdf.beginText(50, 800)
        text.setFont("Helvetica", 9)
        for line in range(45):
            words = [WORDS[(page * 7 + line * 3 + i) % len(WORDS)] for i in range(10)]
            text.textLine(f"{line} " + " ".join(words) + ".")
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def reply(_model, messages) -> str:
    last = messages[-1]["content"]
    if "PASSAGES" in last:
        return "Zebras graze on the savanna [1]."
    return json.dumps({"summary": "A summary.", "topics": ["a", "b"]})


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
    fake = FakeLLMClient(default_reply=reply)
    app = create_app(config, token=TOKEN, llm_factory=lambda _s: fake)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    return server, thread, origin


class Api:
    def __init__(self, origin: str):
        self.base = f"{origin}/api/v1"
        self.http = requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {TOKEN}", "Origin": origin})

    def call(self, method: str, path: str, **kw):
        r = self.http.request(method, self.base + path, timeout=120, **kw)
        r.raise_for_status()
        return r

    def wait_ready(self, notebook_id: str, expected: int, timeout: float = 600) -> float:
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            sources = self.call("GET", f"/notebooks/{notebook_id}/sources").json()
            if len(sources) == expected and all(s["state"] in ("ready", "failed") for s in sources):
                failed = [s for s in sources if s["state"] == "failed"]
                assert not failed, failed[0]["error"]
                return time.perf_counter() - start
            time.sleep(0.05)
        raise TimeoutError("sources did not finish")


def upload(api: Api, notebook_id: str, name: str, data: bytes, mime: str):
    api.call(
        "POST", f"/notebooks/{notebook_id}/sources/files", files=[("files", (name, data, mime))]
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        server, server_thread, origin = start_server(Path(tmp))
        api = Api(origin)
        api.call("PUT", "/settings", json={"chat_model": "c", "embedding_model": "e"})
        notebook_id = api.call("POST", "/notebooks", json={"name": "perf"}).json()["id"]
        rows: list[tuple[str, str, str, str]] = []

        # 1. a 100-page PDF, while a probe measures how long a trivial request waits
        pdf = make_pdf(100)
        latencies: list[float] = []
        stop = threading.Event()

        def probe() -> None:
            while not stop.is_set():
                t = time.perf_counter()
                api.call("GET", "/health")
                latencies.append(time.perf_counter() - t)
                time.sleep(0.02)

        thread = threading.Thread(target=probe)
        thread.start()
        upload(api, notebook_id, "hundred.pdf", pdf, "application/pdf")
        ingest_s = api.wait_ready(notebook_id, 1)
        stop.set()
        thread.join()
        rows.append(
            (
                "Ingest a 100-page text PDF (app only, instant model)",
                "<= 60 s",
                f"{ingest_s:.1f} s",
                "",
            )
        )
        worst = max(latencies) * 1000
        rows.append(
            (
                "Slowest trivial request while ingesting",
                "no UI freeze",
                f"{worst:.0f} ms",
                f"{len(latencies)} requests, median {statistics.median(latencies) * 1000:.0f} ms",
            )
        )

        # 2. fifty sources, then time to the first streamed token
        for i in range(49):
            text = " ".join(WORDS[(i + j) % len(WORDS)] for j in range(400))
            upload(api, notebook_id, f"s{i}.txt", text.encode(), "text/plain")
        api.wait_ready(notebook_id, 50)
        samples = []
        for _ in range(10):
            t = time.perf_counter()
            with api.http.post(
                f"{api.base}/notebooks/{notebook_id}/chat",
                json={"question": "What do zebras eat?"},
                stream=True,
                timeout=60,
            ) as r:
                for line in r.iter_lines():
                    if line.startswith(b"data:") and b'"token"' in line:
                        samples.append(time.perf_counter() - t)
                        break
                for _ in r.iter_lines():
                    pass
        rows.append(
            (
                "First chat token, 50 sources (app only, instant model)",
                "<= 3 s (with a real model)",
                f"{statistics.median(samples) * 1000:.0f} ms",
                f"worst of {len(samples)}: {max(samples) * 1000:.0f} ms",
            )
        )
        t = time.perf_counter()
        api.call("GET", f"/notebooks/{notebook_id}/search", params={"q": "zebras savanna"})
        rows.append(
            ("Search across 50 sources", "-", f"{(time.perf_counter() - t) * 1000:.0f} ms", "")
        )
        server.should_exit = True
        server_thread.join(timeout=10)

    widths = [
        max(len(r[i]) for r in rows + [("Check", "Target", "Measured", "Note")]) for i in range(4)
    ]
    for r in [("Check", "Target", "Measured", "Note"), *rows]:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
    print(
        "\nNot measured here (needs the real models on the recommended hardware): first token with "
        "the real chat model, embedding time, and the ~10-minute audio overview."
    )


if __name__ == "__main__":
    main()
