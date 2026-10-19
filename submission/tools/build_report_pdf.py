"""Build submission/StudyRoute_Technical_Documentation.pdf.

    pip install markdown pypdf          # dev tools only
    python submission/tools/build_report_pdf.py [source.md [target.pdf]]  # needs Google Chrome (set CHROME_PATH if it is not in the usual place)

Front pages in the layout of a security assessment report template (front_matter.py): a bordered title page,
a table of contents, a list of tables and a list of figures, numbered i, ii, ... Then the body: a running header
and footer, a numbered kicker above each section title, navy table headers and teal call-out boxes, numbered
from page 1. The page numbers in the lists are read from the rendered body.
"""

from __future__ import annotations

import html
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from front_matter import Cover, assemble, caption_classes, entries, find_chrome, front_html, locate, print_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md"
TARGET = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "submission" / "StudyRoute_Technical_Documentation.pdf"
DOC_ID = "SR-TEC-2026-01"
DATE = "19 October 2026"
COVER = Cover(
    top=("StudyRoute / International Track", "FinTechathon 2026, Topic C", "Prepared by TeamEkxin"),
    title="Technical Documentation",
    subtitle="StudyRoute Technical Documentation",
    tagline="Architecture, core algorithms, trained components and security design",
    note="Synthetic data • Not production assurance",
    bottom=(f"Document {DOC_ID}", DATE, "github.com/NoobCrow/StudyRoute"),
    footer=f"StudyRoute – Technical Documentation ({DOC_ID})",
)
BODY_CSS = """
@page { size: A4; margin: 22mm 16mm 18mm 16mm;
  @top-left { content: "STUDYROUTE"; font: 700 8pt Arial, Helvetica, sans-serif; color: #0b8a86; vertical-align: bottom; padding-bottom: 2.5mm; width: 50%%; border-bottom: 1px solid #cfd8e0; }
  @top-right { content: "TECHNICAL DOCUMENTATION"; font: 8pt Arial, Helvetica, sans-serif; color: #6b7a88; text-align: right; vertical-align: bottom; padding-bottom: 2.5mm; width: 50%%; border-bottom: 1px solid #cfd8e0; }
  @bottom-left { content: "%(doc_id)s  |  Synthetic data, not production assurance"; font: 7.6pt Arial, Helvetica, sans-serif; color: #6b7a88; vertical-align: top; padding-top: 3mm; }
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
code { font-family: Consolas, "Courier New", monospace; font-size: 8.4pt; background: #eef2f5; padding: 0; overflow-wrap: anywhere; }
pre { background: #f0f5f8; border: 1px solid #dde4ea; padding: 2.6mm; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8pt; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%%; height: auto; display: block; margin: 3mm auto; page-break-inside: avoid; }
p:has(+ p img) { break-after: avoid; page-break-after: avoid; }
blockquote { margin: 3mm 0 4mm; padding: 2.4mm 3.6mm; border-left: 3px solid #0b8a86; background: #eaf4f4; font-size: 9.2pt; }
blockquote p { margin: 0; }
a { color: #0b5cad; text-decoration: none; }
p.cap { font-weight: 700; font-size: 8.6pt; color: #0e2a47; margin: 4mm 0 1.4mm; break-after: avoid; page-break-after: avoid; }
p.fcap { text-align: center; margin: 0 0 4.5mm; break-before: avoid; page-break-before: avoid; }
p:has(> img) { margin-bottom: 1mm; break-after: avoid; page-break-after: avoid; }
"""








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
    body = caption_classes(re.sub(r"(<h2[^>]*>(.*?)</h2>)", kicker, body))
    css = BODY_CSS % {"doc_id": DOC_ID}
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>StudyRoute: technical documentation</title>"
        f"<base href='{SOURCE.parent.as_uri()}/'><style>{css}</style></head><body>{body}</body></html>"
    )




def main() -> int:
    try:
        import markdown
        import pypdf  # noqa: F401
    except ImportError:
        print("Install the tools first: pip install markdown pypdf", file=sys.stderr)
        return 1
    text = SOURCE.read_text(encoding="utf-8")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    items = entries(text[text.index("## Summary"):], {"##": 1, "###": 2})
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        (work / "body.html").write_text(body_html(markdown, text), encoding="utf-8")
        print_pdf(chrome, work / "body.html", work / "body.pdf")
        pages = locate(work / "body.pdf", items)
        front, marks = front_html(COVER, items, pages)
        (work / "front.html").write_text(front, encoding="utf-8")
        print_pdf(chrome, work / "front.html", work / "front.pdf")
        total = assemble(work / "front.pdf", work / "body.pdf", TARGET, items, pages, marks,
                         {"/Title": "StudyRoute | Technical Documentation", "/Author": "TeamEkxin", "/Subject": DOC_ID})
    print(f"wrote {TARGET.name}: {total} pages, {TARGET.stat().st_size // 1024} KB")
    return 0

if __name__ == "__main__":
    sys.exit(main())
