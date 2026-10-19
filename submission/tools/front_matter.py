"""Front pages for the submission reports, laid out like a security assessment report template.

A bordered title page, a table of contents, a list of tables and a list of figures. Each front page carries
the synthetic-data banner and a roman page number; the body keeps its own layout and starts again at page 1.
The page numbers in the lists are read from the rendered body PDF, so they always match it.

Captions are Markdown paragraphs of the form **Table 3. Title** (above a table) or **Figure 2. Title** (below
an image). Used by build_report_pdf.py; needs pypdf and Google Chrome.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

BANNER = "SYNTHETIC DATA – NOT PRODUCTION ASSURANCE"
CAPTION = re.compile(r"^\*\*((?:Table|Figure) \d+\. .+?)\*\*$")
CAPTION_HTML = re.compile(r"<p><strong>((Table|Figure) \d+\. [^<]+)</strong></p>")
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(.*)$")
USUAL_CHROME = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
TOC_FIRST, TOC_NEXT, LIST_PAGE = 42.5, 46.0, 45.0  # line units that fit on a front page

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Times New Roman", Times, serif; color: #000; }
.page { width: 210mm; height: 297mm; position: relative; overflow: hidden; break-after: page; }
.page:last-child { break-after: auto; }
.banner { position: absolute; left: 25mm; right: 25mm; top: 13mm; padding-bottom: 1.6mm; text-align: center;
  color: #e00000; font-weight: 700; font-size: 11.5pt; border-bottom: 1.3pt solid #000; }
.foot { position: absolute; left: 25mm; right: 25mm; bottom: 13mm; padding-top: 1.4mm; border-top: 1pt solid #000;
  display: flex; justify-content: space-between; font: 8.5pt "Arial Narrow", Arial, sans-serif; }
.content { position: absolute; left: 25mm; right: 25mm; top: 30mm; bottom: 24mm; }
h1 { font: 700 15pt "Arial Narrow", Arial, sans-serif; margin: 0 0 4mm; }
h1.next { margin-top: 7mm; }
.box { position: absolute; left: 25mm; right: 22mm; top: 27mm; bottom: 29mm; border: 2.1mm solid #000; }
.box > div { position: absolute; left: 6mm; right: 6mm; text-align: center; font-size: 12pt; line-height: 1.3; }
.box .top { top: 28%%; }
.box .mid { top: 56%%; }
.box .bot { top: 80%%; line-height: 1.5; }
.mid .t1 { font-size: 21pt; font-weight: 700; }
.mid .t2 { font-size: 15pt; font-weight: 700; margin-top: 1.5mm; }
.mid .t3 { font-style: italic; margin-top: 2.2mm; }
.mid .t4 { margin-top: 1.4mm; }
.e { display: flex; align-items: baseline; font-size: 11.5pt; line-height: 5.6mm; }
.e.l1 { margin-top: 2.6mm; }
.e.first, .e.flat { margin-top: 0; }
.e.l2 { padding-left: 5mm; }
.e.l3 { padding-left: 16mm; }
.e .n { flex: none; }
.e.l1 .n { width: 8mm; }
.e.l2 .n { width: 11mm; }
.e .t { flex: none; max-width: 136mm; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.e .d { flex: 1; overflow: hidden; white-space: nowrap; margin: 0 1.2mm; }
.e .d::after { content: "%(dots)s"; letter-spacing: 1.1pt; }
.e .p { flex: none; min-width: 6mm; text-align: right; }
table.dc { border-collapse: collapse; width: 100%%; font-size: 10.5pt; }
table.dc td { border: 1pt solid #000; padding: 1.6mm 2.2mm; vertical-align: top; }
table.dc td.k { width: 46mm; font-weight: 700; background: #f0f0f0; }
"""


@dataclass(frozen=True)
class Cover:
    top: tuple[str, ...]
    title: str
    subtitle: str
    tagline: str
    note: str
    bottom: tuple[str, ...]
    footer: str  # the running footer label of the front pages


@dataclass(frozen=True)
class Entry:
    kind: str  # "toc", "Table" or "Figure"
    level: int
    text: str


def find_chrome() -> str:
    for candidate in (os.environ.get("CHROME_PATH", ""), *USUAL_CHROME):
        if candidate and Path(candidate).exists():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if not found:
        raise SystemExit("Google Chrome not found: set CHROME_PATH to its executable")
    return found


def print_pdf(chrome: str, page: Path, target: Path) -> None:
    subprocess.run(  # noqa: S603
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         "--allow-file-access-from-files", f"--print-to-pdf={target}", page.as_uri()],
        check=True, capture_output=True,
    )


def plain(text: str) -> str:
    """Heading or caption text as it appears on the page (Markdown marks removed)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return html.unescape(re.sub(r"\*\*|`|(?<!\w)\*|\*(?!\w)", "", text)).strip()


def entries(markdown_text: str, levels: dict[str, int], skip: tuple[str, ...] = ()) -> list[Entry]:
    """Headings (by marker, e.g. {"##": 1, "###": 2}) and captions, in document order."""
    found: list[Entry] = []
    fenced = False
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        caption = CAPTION.match(stripped)
        if caption:
            found.append(Entry(caption.group(1).split(" ", 1)[0], 1, caption.group(1)))
            continue
        marker, _, title = stripped.partition(" ")
        if marker in levels and title and not any(word in title for word in skip):
            found.append(Entry("toc", levels[marker], plain(title)))
    return found


def caption_classes(body_html: str) -> str:
    """Give caption paragraphs their own class: tables above, figures below and centred."""
    return CAPTION_HTML.sub(
        lambda m: f"<p class='cap {'tcap' if m.group(2) == 'Table' else 'fcap'}'>{m.group(1)}</p>", body_html
    )


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", text).lower())


def locate(body_pdf: Path, items: list[Entry]) -> list[int]:
    """The body page (from 1) on which each item first appears, searching forward in document order."""
    from pypdf import PdfReader

    pages = [_key(page.extract_text() or "") for page in PdfReader(str(body_pdf)).pages]
    found, start = [], 0
    for item in items:
        key = _key(item.text)
        for index in range(start, len(pages)):
            if key in pages[index]:
                found.append(index + 1)
                start = index
                break
        else:
            raise ValueError(f"not found in the rendered body: {item.text!r}")
    return found


def roman(number: int) -> str:
    out = ""
    for value, letters in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while number >= value:
            out, number = out + letters, number - value
    return out


def _row(entry: Entry, page: int, first: bool) -> tuple[str, float]:
    text = html.escape(entry.text)
    if entry.kind != "toc":
        return f"<div class='e flat'><span class='t'>{text}</span><span class='d'></span><span class='p'>{page}</span></div>", 1.0
    numbered = NUMBERED.match(entry.text)
    blank = "<span class='n'></span>" if entry.level == 2 else ""  # line up with the numbered titles
    number = f"<span class='n'>{html.escape(numbered.group(1))}</span>" if numbered else blank
    title = html.escape(numbered.group(2)) if numbered else text
    extra = " first" if first else ""
    height = 1.0 + (0.46 if entry.level == 1 and not first else 0.0)
    return (
        f"<div class='e l{entry.level}{extra}'>{number}<span class='t'>{title}</span>"
        f"<span class='d'></span><span class='p'>{page}</span></div>",
        height,
    )


def _page(cover: Cover, number: int, content: str) -> str:
    return (
        f"<section class='page'><div class='banner'>{html.escape(BANNER)}</div><div class='content'>{content}</div>"
        f"<div class='foot'><span>{html.escape(cover.footer)}</span><span>Page {roman(number)}</span></div></section>"
    )


def _cover_page(cover: Cover) -> str:
    lines = lambda items: "<br>".join(html.escape(item) for item in items)  # noqa: E731
    return (
        f"<section class='page'><div class='banner'>{html.escape(BANNER)}</div><div class='box'>"
        f"<div class='top'>{lines(cover.top)}</div>"
        f"<div class='mid'><div class='t1'>{html.escape(cover.title)}</div><div class='t2'>{html.escape(cover.subtitle)}</div>"
        f"<div class='t3'>{html.escape(cover.tagline)}</div><div class='t4'>{html.escape(cover.note)}</div></div>"
        f"<div class='bot'>{lines(cover.bottom)}</div></div></section>"
    )


def _flow(blocks: list[tuple[str, float]], first_capacity: float, capacity: float) -> list[str]:
    pages: list[str] = []
    current, used, limit = "", 0.0, first_capacity
    for markup, height in blocks:
        if used + height > limit and current:
            pages.append(current)
            current, used, limit = "", 0.0, capacity
        current += markup
        used += height
    if current:
        pages.append(current)
    return pages


def front_html(
    cover: Cover, items: list[Entry], pages: list[int], extra: tuple[tuple[str, str], ...] = ()
) -> tuple[str, dict[str, int]]:
    """The front pages as one HTML document, and the front page index (from 0) of each list."""
    toc = [(e, p) for e, p in zip(items, pages, strict=True) if e.kind == "toc"]
    tables = [(e, p) for e, p in zip(items, pages, strict=True) if e.kind == "Table"]
    figures = [(e, p) for e, p in zip(items, pages, strict=True) if e.kind == "Figure"]
    out = [_cover_page(cover)]
    marks = {"Title page": 0}

    toc_blocks = [("<h1>Table of Contents</h1>", 2.6)] + [_row(e, p, i == 0) for i, (e, p) in enumerate(toc)]
    marks["Table of Contents"] = len(out)
    for body in _flow(toc_blocks, TOC_FIRST + 2.6, TOC_NEXT):
        out.append(_page(cover, len(out) + 1, body))

    list_blocks: list[tuple[str, float]] = []
    if tables:
        list_blocks += [("<h1>List of Tables</h1>", 2.6)] + [_row(e, p, False) for e, p in tables]
    if figures:
        list_blocks += [("<h1 class='next'>List of Figures</h1>" if tables else "<h1>List of Figures</h1>", 3.8)]
        list_blocks += [_row(e, p, False) for e, p in figures]
    if list_blocks:
        marks["List of Tables" if tables else "List of Figures"] = len(out)
        for body in _flow(list_blocks, LIST_PAGE, LIST_PAGE):
            out.append(_page(cover, len(out) + 1, body))

    for title, body in extra:
        marks[title] = len(out)
        out.append(_page(cover, len(out) + 1, f"<h1>{html.escape(title)}</h1>{body}"))

    css = CSS % {"dots": ". " * 160}
    document = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(out)}</body></html>"
    return document, marks


def assemble(
    front_pdf: Path, body_pdf: Path, target: Path, items: list[Entry], pages: list[int],
    marks: dict[str, int], metadata: dict[str, str],
) -> int:
    """Front pages, then the body; bookmarks for the lists and every heading; roman then arabic page labels."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    front = PdfReader(str(front_pdf)).pages
    for page in front:
        writer.add_page(page)
    for page in PdfReader(str(body_pdf)).pages:
        writer.add_page(page)
    offset = len(front)
    for title, index in marks.items():
        writer.add_outline_item(title, index)
    parents: dict[int, object] = {}
    for entry, page in zip(items, pages, strict=True):
        if entry.kind != "toc":
            continue
        parent = parents.get(entry.level - 1) if entry.level > 1 else None
        parents[entry.level] = writer.add_outline_item(entry.text, offset + page - 1, parent=parent)
    if hasattr(writer, "set_page_label"):
        writer.set_page_label(0, offset - 1, style="/r")
        writer.set_page_label(offset, len(writer.pages) - 1, style="/D", start=1)
    writer.add_metadata(metadata)
    with target.open("wb") as handle:
        writer.write(handle)
    return len(writer.pages)
