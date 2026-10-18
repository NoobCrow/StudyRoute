"""Build submission/StudyRoute_Technical_Documentation.pdf in the house format of the evidence-pack reports.

    pip install markdown pypdf          # dev tools only
    python submission/tools/build_report_pdf.py [source.md [target.pdf]]  # needs Google Chrome (set CHROME_PATH if it is not in the usual place)

The format follows the teammate's Security Self-Assessment and Execution Evidence Report: a full-page navy
cover with a document id, a contents list and a not-production box; then pages with a running header and
footer, a numbered kicker above each section title, navy table headers and teal call-out boxes.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md"
TARGET = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "submission" / "StudyRoute_Technical_Documentation.pdf"
DOC_ID = "SR-TEC-2026-01"
EDITION = "Final edition"
DATE = "18 October 2026"
USUAL_CHROME = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

COVER_CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; width: 210mm; height: 297mm; background: #0f2a47; color: #fff; font-family: Arial, Helvetica, sans-serif; position: relative; }
.rule { position: absolute; left: 24mm; top: 40mm; width: 17mm; height: 1.4mm; background: #0b8a86; }
.kicker { position: absolute; left: 24mm; top: 50mm; font-size: 9.5pt; font-weight: 700; letter-spacing: .09em; color: #8fd8d3; }
h1 { position: absolute; left: 24mm; top: 70mm; margin: 0; font-size: 38pt; line-height: 1.12; font-weight: 700; width: 160mm; }
.sub { position: absolute; left: 24mm; top: 112mm; font-size: 12.5pt; color: #c9d6e3; width: 150mm; }
.box { position: absolute; left: 24mm; top: 140mm; width: 162mm; background: #173b5c; border-radius: 3mm; padding: 6mm 7mm; }
.box .t { font-size: 9pt; font-weight: 700; letter-spacing: .06em; color: #8fd8d3; }
.box .m { font-size: 12pt; margin-top: 3mm; } .box .s { font-size: 9.5pt; color: #c9d6e3; margin-top: 2mm; }
.toc { position: absolute; left: 24mm; top: 176mm; width: 162mm; }
.toc .h { font-size: 9pt; font-weight: 700; letter-spacing: .09em; color: #8fd8d3; margin-bottom: 4mm; }
.cols { display: flex; gap: 8mm; } .col { flex: 1; }
.item { font-size: 9.6pt; color: #dbe6f2; margin-bottom: 3.1mm; display: flex; gap: 4mm; }
.item b { color: #5cc9c3; width: 6mm; flex: none; }
.foot { position: absolute; left: 24mm; right: 24mm; bottom: 24mm; border-top: 1px solid #3c5878; padding-top: 4mm; }
.foot .a { display: flex; justify-content: space-between; font-size: 9.5pt; color: #dbe6f2; }
.foot .b { font-size: 8.8pt; color: #9db2c7; margin-top: 2.5mm; }
"""

BODY_CSS = """
@page { size: A4; margin: 22mm 16mm 18mm 16mm;
  @top-left { content: "STUDYROUTE"; font: 700 8pt Arial, Helvetica, sans-serif; color: #0b8a86; vertical-align: bottom; padding-bottom: 2.5mm; width: 50%%; border-bottom: 1px solid #cfd8e0; }
  @top-right { content: "TECHNICAL DOCUMENTATION"; font: 8pt Arial, Helvetica, sans-serif; color: #6b7a88; text-align: right; vertical-align: bottom; padding-bottom: 2.5mm; width: 50%%; border-bottom: 1px solid #cfd8e0; }
  @bottom-left { content: "%(doc_id)s  |  %(edition)s  |  Synthetic data, not production assurance"; font: 7.6pt Arial, Helvetica, sans-serif; color: #6b7a88; vertical-align: top; padding-top: 3mm; }
  @bottom-right { content: counter(page); font: 8pt Arial, Helvetica, sans-serif; color: #6b7a88; vertical-align: top; padding-top: 3mm; } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9.4pt; line-height: 1.38; color: #1b2733; }
.kick { color: #0b8a86; font-weight: 700; font-size: 8.4pt; letter-spacing: .04em; margin-top: 7mm; padding-top: 1.5mm; page-break-after: avoid; }
h2 { font-size: 19pt; color: #0e2a47; margin: 1mm 0 3mm; page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #0e2a47; margin: 6mm 0 2mm; page-break-after: avoid; }
h4 { font-size: 10.5pt; color: #0e2a47; margin: 4mm 0 1mm; page-break-after: avoid; }
p { margin: 0 0 2.6mm; }
table { border-collapse: collapse; width: 100%%; margin: 3mm 0 4.5mm; font-size: 8.4pt; }
th { background: #0e2a47; color: #fff; text-align: left; padding: 1.8mm 2.6mm; }
td { padding: 1.7mm 2.6mm; vertical-align: top; border-bottom: 1px solid #dde4ea; overflow-wrap: break-word; }
tr:nth-child(even) td { background: #f0f5f8; } tr { page-break-inside: avoid; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.4pt; background: #eef2f5; padding: 0 .8mm; overflow-wrap: anywhere; }
pre { background: #f0f5f8; border: 1px solid #dde4ea; padding: 2.6mm; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8pt; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%%; height: auto; display: block; margin: 3mm auto; page-break-inside: avoid; }
blockquote { margin: 3mm 0 4mm; padding: 2.4mm 3.6mm; border-left: 3px solid #0b8a86; background: #eaf4f4; font-size: 9.2pt; }
blockquote p { margin: 0; }
a { color: #0b5cad; text-decoration: none; }
"""


def find_chrome() -> str:
    for candidate in (os.environ.get("CHROME_PATH", ""), *USUAL_CHROME):
        if candidate and Path(candidate).exists():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if not found:
        raise SystemExit("Google Chrome not found: set CHROME_PATH to its executable")
    return found


def sections(text: str) -> list[tuple[str, str]]:
    """(number, title) of every level-two heading: 'Summary' is 00, '## 3. Core ...' is 03."""
    found = []
    for title in re.findall(r"^## (.+)$", text, flags=re.M):
        match = re.match(r"(\d+)\.\s+(.*)", title)
        found.append((f"{int(match.group(1)):02d}", match.group(2)) if match else ("00", title))
    return found


def cover_html(items: list[tuple[str, str]]) -> str:
    half = (len(items) + 1) // 2
    column = lambda part: "".join(  # noqa: E731
        f"<div class='item'><b>{number}</b><span>{html.escape(title)}</span></div>" for number, title in part
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{COVER_CSS}</style></head><body>"
        "<div class='rule'></div><div class='kicker'>STUDYROUTE &nbsp;/&nbsp; INTERNATIONAL TRACK &nbsp;/&nbsp; TOPIC C</div>"
        "<h1>Technical Documentation</h1>"
        "<div class='sub'>Architecture, core algorithms, trained components and security design</div>"
        "<div class='box'><div class='t'>SANDBOX &nbsp;/&nbsp; SYNTHETIC DATA &nbsp;/&nbsp; NOT PRODUCTION ASSURANCE</div>"
        "<div class='m'>System description with measured evidence and stated limits</div>"
        "<div class='s'>No real money, live bank, real users or independent certification</div></div>"
        f"<div class='toc'><div class='h'>REPORT CONTENTS</div><div class='cols'><div class='col'>{column(items[:half])}</div>"
        f"<div class='col'>{column(items[half:])}</div></div></div>"
        f"<div class='foot'><div class='a'><span>{DOC_ID} &nbsp;|&nbsp; {EDITION}</span><span>{DATE}</span></div>"
        "<div class='b'>Prepared for StudyRoute submission review &bull; English edition &bull; Team TeamEkxin</div></div>"
        "</body></html>"
    )


def kicker(match: re.Match[str]) -> str:
    title = html.unescape(re.sub(r"<[^>]+>", "", match.group(2)))
    number = re.match(r"(\d+)\.\s+(.*)", title)
    label, text = (f"{int(number.group(1)):02d}", number.group(2)) if number else ("00", title)
    text = text.upper().replace(" AND ", " & ")
    return f"<div class='kick'>{label} / {html.escape(text)}</div>{match.group(0)}"


def body_html(markdown_module: object, text: str) -> str:
    start = text.index("## Summary")  # the cover replaces the title block
    body = markdown_module.markdown(  # type: ignore[attr-defined]
        text[start:], extensions=["tables", "fenced_code", "sane_lists"]
    )
    body = re.sub(r"(<h2[^>]*>(.*?)</h2>)", kicker, body)
    css = BODY_CSS % {"doc_id": DOC_ID, "edition": EDITION}
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>StudyRoute: technical documentation</title>"
        f"<base href='{SOURCE.parent.as_uri()}/'><style>{css}</style></head><body>{body}</body></html>"
    )


def print_pdf(chrome: str, page: Path, target: Path) -> None:
    subprocess.run(  # noqa: S603
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         "--allow-file-access-from-files", f"--print-to-pdf={target}", page.as_uri()],
        check=True, capture_output=True,
    )


def main() -> int:
    try:
        import markdown
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("Install the tools first: pip install markdown pypdf", file=sys.stderr)
        return 1
    text = SOURCE.read_text(encoding="utf-8")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / "cover.html").write_text(cover_html(sections(text)), encoding="utf-8")
        (work / "body.html").write_text(body_html(markdown, text), encoding="utf-8")
        print_pdf(chrome, work / "cover.html", work / "cover.pdf")
        print_pdf(chrome, work / "body.html", work / "body.pdf")
        writer = PdfWriter()
        writer.add_page(PdfReader(str(work / "cover.pdf")).pages[0])
        for page in PdfReader(str(work / "body.pdf")).pages:
            writer.add_page(page)
        writer.add_metadata({"/Title": "StudyRoute | Technical Documentation", "/Subject": f"{DOC_ID} {EDITION}"})
        with TARGET.open("wb") as handle:
            writer.write(handle)
    pages = len(PdfReader(str(TARGET)).pages)
    print(f"wrote {TARGET.name}: {pages} pages, {TARGET.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
