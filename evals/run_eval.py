"""Grounding evaluation (QA-4). Run manually against a real model:

    uv run python evals/run_eval.py --chat-model <name> --embedding-model <name> \
        [--base-url http://127.0.0.1:11434/v1] [--api-key KEY]

It ingests the fictional documents in evals/docs/ into a throwaway data folder, asks the 30
questions in evals/questions.json (half answerable, half not), and prints a results table.

Metrics (per question, no model-as-judge):
- Citation support rate: of the answerable questions, the share whose answer cites at least one
  passage that contains the question's gold evidence phrase. Target >= 95%.
- Correct-refusal rate: of the unanswerable questions, the share answered with the refusal
  sentence and no citations. Target >= 90%.

`--selftest` replaces the model with a scripted oracle that knows the answer key, to check the
plumbing and the dataset without any model server. Exit status is 1 if a target is missed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.chat import service  # noqa: E402
from app.core import db, settings_store  # noqa: E402
from app.core.config import MIGRATIONS_DIR  # noqa: E402
from app.core.ids import new_id  # noqa: E402
from app.core.notebooks import NotebookStore  # noqa: E402
from app.ingest import service as source_service  # noqa: E402
from app.ingest.pipeline import run_ingest  # noqa: E402
from app.llm.fake import FakeLLMClient  # noqa: E402
from app.llm.openai_compat import OpenAICompatClient  # noqa: E402

CITATION_TARGET = 0.95
REFUSAL_TARGET = 0.90


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def is_refusal(content: str, citations: list) -> bool:
    return not citations and _norm(service.REFUSAL) in _norm(content)


def supported(conn, citations: list, evidence: list[str]) -> bool:
    for cite in citations:
        row = conn.execute("SELECT text FROM chunks WHERE id = ?", (cite["chunk_id"],)).fetchone()
        if row and any(_norm(e) in _norm(row["text"]) for e in evidence):
            return True
    return False


def selftest_llm(questions: list[dict]) -> FakeLLMClient:
    """An oracle that knows the answer key: it cites the supplied passage containing the gold
    evidence, and refuses when there is none. It checks the plumbing (retrieval puts the evidence
    in front of the model, citations map back to chunks, the metrics are computed correctly)."""
    key = {q["question"]: q for q in questions}

    def brain(_model, messages):
        last = messages[-1]["content"]
        if "follow-up questions" in last:
            return json.dumps({"questions": ["Tell me more?"]})
        if "PASSAGES" not in last:
            return json.dumps({"summary": "A document.", "topics": ["a", "b", "c"]})
        question = last.split("Question:")[-1].split("\n")[0].strip()
        gold = key[question]
        if gold["answerable"]:
            for label, body in re.findall(
                r"\[(\d+)\] \(Source[^\n]*\n(.*?)(?=\n\n\[\d+\] \(Source|\n<<<END)", last, re.S
            ):
                if any(_norm(e) in _norm(body) for e in gold["evidence"]):
                    return f"The sources say so [{label}]."
        return service.REFUSAL

    return FakeLLMClient(default_reply=brain)


async def evaluate(args) -> int:
    questions = json.loads((Path(__file__).parent / "questions.json").read_text("utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="lnb-eval-"))
    try:
        db.migrate(tmp / "app.db", MIGRATIONS_DIR / "app")
        store = NotebookStore(tmp)
        notebook_id = store.create("eval")["id"]
        llm = (
            selftest_llm(questions)
            if args.selftest
            else OpenAICompatClient(args.base_url, args.api_key, timeout=300)
        )
        settings = {
            **settings_store.load_defaults_for_eval(),
            "chat_model": args.chat_model or "selftest",
            "embedding_model": args.embedding_model or "selftest",
        }
        conn = store.open(notebook_id)
        for doc in sorted((Path(__file__).parent / "docs").iterdir()):
            source_id = new_id()
            folder = store.source_dir(notebook_id, source_id)
            folder.mkdir(parents=True)
            shutil.copy(doc, folder / f"original{doc.suffix}")
            source_service.create_source(
                conn,
                source_id=source_id,
                name=doc.name,
                source_type={".md": "md"}.get(doc.suffix, "txt"),
                original_name=doc.name,
                size_bytes=doc.stat().st_size,
            )
            error = await run_ingest(store, notebook_id, source_id, llm, settings)
            if error:
                print(f"Ingestion of {doc.name} failed: {error}", file=sys.stderr)
                return 2

        rows = []
        for q in questions:
            events = []
            async for event in service.stream_answer(
                store, notebook_id, q["question"], llm, settings, asyncio.Event()
            ):
                events.append(event)
            done = next((e["message"] for e in events if e["type"] == "done"), None)
            if done is None:
                err = next((e["message"] for e in events if e["type"] == "error"), "no answer")
                rows.append((q, False, 0, f"ERROR: {err}"))
                continue
            cites = done["citations"]
            if q["answerable"]:
                ok = supported(conn, cites, q["evidence"])
            else:
                ok = is_refusal(done["content"], cites)
            rows.append((q, ok, len(cites), done["content"]))
        conn.close()
        close = getattr(llm, "aclose", None)
        if close:
            await close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"{'ID':<5}{'Kind':<14}{'Result':<7}{'Cites':<6}Answer")
    for q, ok, n, text in rows:
        snippet = " ".join(text.split())[:70]
        kind = "answerable" if q["answerable"] else "unanswerable"
        print(f"{q['id']:<5}{kind:<14}{'PASS' if ok else 'FAIL':<7}{n:<6}{snippet}")
    ans = [ok for q, ok, _, _ in rows if q["answerable"]]
    unans = [ok for q, ok, _, _ in rows if not q["answerable"]]
    cite_rate, refuse_rate = sum(ans) / len(ans), sum(unans) / len(unans)
    print()
    print(f"{'Metric':<28}{'Result':<14}{'Target':<8}Status")
    for name, rate, count, total, target in (
        ("Citation support rate", cite_rate, sum(ans), len(ans), CITATION_TARGET),
        ("Correct-refusal rate", refuse_rate, sum(unans), len(unans), REFUSAL_TARGET),
    ):
        status = "PASS" if rate >= target else "FAIL"
        print(f"{name:<28}{f'{rate:.0%} ({count}/{total})':<14}{f'>={target:.0%}':<8}{status}")
    return 0 if cite_rate >= CITATION_TARGET and refuse_rate >= REFUSAL_TARGET else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    p.add_argument("--api-key", default="")
    p.add_argument("--chat-model", default="")
    p.add_argument("--embedding-model", default="")
    p.add_argument("--selftest", action="store_true", help="use a scripted model, no server")
    args = p.parse_args()
    if not args.selftest and not (args.chat_model and args.embedding_model):
        p.error("--chat-model and --embedding-model are required (or use --selftest)")
    sys.exit(asyncio.run(evaluate(args)))


if __name__ == "__main__":
    main()
