"""Turn Markdown into a small block list that the DOCX and PDF writers both consume."""

from __future__ import annotations

from dataclasses import dataclass, field

from markdown_it import MarkdownIt


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Block:
    kind: str  # heading | para | bullet | number | quote | code | rule
    runs: list[Run] = field(default_factory=list)
    level: int = 1  # heading level, or list nesting depth
    number: int = 0  # for numbered items


def _inline_runs(token) -> list[Run]:
    runs: list[Run] = []
    bold = italic = 0
    for child in token.children or []:
        if child.type == "strong_open":
            bold += 1
        elif child.type == "strong_close":
            bold -= 1
        elif child.type == "em_open":
            italic += 1
        elif child.type == "em_close":
            italic -= 1
        elif child.type in ("text", "html_inline"):
            runs.append(Run(child.content, bold > 0, italic > 0))
        elif child.type == "code_inline":
            runs.append(Run(child.content, bold > 0, italic > 0, code=True))
        elif child.type in ("softbreak", "hardbreak"):
            runs.append(Run(" " if child.type == "softbreak" else "\n"))
        elif child.type == "image":
            runs.append(Run(child.content or ""))
    return runs


def parse_markdown(markdown: str) -> list[Block]:
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    blocks: list[Block] = []
    list_stack: list[dict] = []  # {"ordered": bool, "count": int}
    in_quote = 0
    heading: int | None = None
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            heading = int(tok.tag[1])
        elif tok.type == "heading_close":
            heading = None
        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append({"ordered": tok.type == "ordered_list_open", "count": 0})
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif tok.type == "list_item_open":
            list_stack[-1]["count"] += 1
        elif tok.type == "blockquote_open":
            in_quote += 1
        elif tok.type == "blockquote_close":
            in_quote -= 1
        elif tok.type == "inline":
            runs = _inline_runs(tok)
            if heading is not None:
                blocks.append(Block("heading", runs, level=heading))
            elif list_stack:
                top = list_stack[-1]
                kind = "number" if top["ordered"] else "bullet"
                # Only the first paragraph of an item carries the bullet/number.
                prev = tokens[i - 2] if i >= 2 else None
                if (
                    prev is not None
                    and prev.type in ("list_item_open",)
                    or (i >= 1 and tokens[i - 1].type == "list_item_open")
                ):
                    blocks.append(Block(kind, runs, level=len(list_stack), number=top["count"]))
                else:
                    blocks.append(Block("para", runs))
            elif in_quote:
                blocks.append(Block("quote", runs))
            else:
                blocks.append(Block("para", runs))
        elif tok.type in ("fence", "code_block"):
            blocks.append(Block("code", [Run(tok.content.rstrip("\n"), code=True)]))
        elif tok.type == "hr":
            blocks.append(Block("rule"))
    return blocks
