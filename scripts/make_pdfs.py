"""Make the send-ready PDFs from the Markdown documents, each with a cover page.

    pip install markdown          # a dev tool only, not a dependency of the app
    python scripts/make_pdfs.py

Needs Google Chrome (set CHROME_PATH if it is not in the usual place). Writes, under submission/:

    StudyRoute_Technical_Documentation.pdf     from docs/TECHNICAL_DOCUMENTATION.md
    StudyRoute_Security_Self_Assessment.pdf    from docs/SECURITY_SELF_ASSESSMENT.md  (landscape)
    StudyRoute_Execution_Evidence_Summary.pdf  from submission/EXECUTION_EVIDENCE_SUMMARY.md

The numbers on each cover page are read from the repository (the test count, the risk list, the
security-test and Docker outputs), so a cover cannot say more than the files show.
"""

# ruff: noqa: E501  (the cover-page CSS and HTML strings are long on purpose)

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAM = "TeamEkxin"
MEMBERS = "Farhan Labib, Md Redwan Hossen, Alim Bin Yeasin, Kalvin Chakma"
UNIVERSITY = "Ahsanullah University of Science and Technology, Bangladesh"
SANDBOX = "Sandbox: synthetic data, no real money moves. Guidance is indicative: confirm with your AD bank."
EDUCATION_REMITTANCES = ("USD 881.7m", "sent through Bangladeshi banks for overseas education in 2025-26")
USUAL_CHROME = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

Stat = tuple[str, str]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def ratio(relative: str, pattern: str) -> str:
    match = re.search(pattern, read(relative))
    if match is None:
        raise SystemExit(f"{relative}: nothing matches {pattern!r}")
    return f"{match.group(1)} / {match.group(2)}"


def backend_tests() -> str:
    match = re.search(r"Backend: \*\*(\d+) tests\*\*", read("docs/TEST_CASES.md"))
    if match is None:
        raise SystemExit("docs/TEST_CASES.md has no backend count; run scripts/gen_test_cases.py")
    return f"{int(match.group(1)):,}"


def technical_stats() -> list[Stat]:
    attacks = ratio("submission/evidence/security_2026-10-18/attack_probe.txt", r"(\d+)/(\d+) defended")
    return [
        EDUCATION_REMITTANCES,
        (backend_tests(), "automated backend tests; all 24 blueprint scenarios mapped to tests"),
        (attacks, "attacks defended in the security re-run of 18 October 2026"),
    ]


def security_stats() -> list[Stat]:
    risks = len(re.findall(r"^\| R\d+ \|", read("docs/SECURITY_SELF_ASSESSMENT.md"), re.M))
    attacks = ratio("submission/evidence/security_2026-10-18/attack_probe.txt", r"(\d+)/(\d+) defended")
    browser = ratio("submission/evidence/security_2026-10-18/browser_audit.txt", r"(\d+)/(\d+) checks passed")
    return [
        (str(risks), "known risks listed openly, with what is done and what is still open"),
        (attacks, "attacks defended: forged tokens, cross-household access, injection, bank review desk"),
        (browser, "real-browser checks under the production content-security policy"),
    ]


def evidence_stats() -> list[Stat]:
    log = read("submission/evidence/sandbox_operation_log.txt")
    verify = json.loads(read("submission/evidence/audit_verify.json"))
    browser = ratio("submission/evidence/docker_2026-10-18/browser_audit.txt", r"(\d+)/(\d+) checks passed")
    return [
        (str(len(re.findall(r"^\s+OK\s", log, re.M))), "demo checks OK, none failed (14 steps, sandbox)"),
        (str(verify["events_checked"]), f"audit events; the hash chain verifies ({verify['status']})"),
        (browser, "browser checks against the Docker containers"),
    ]


@dataclass(frozen=True)
class Doc:
    source: str
    target: str
    title: str
    subtitle: str
    landscape: bool
    stats: Callable[[], list[Stat]]


DOCS = (
    Doc(
        "docs/TECHNICAL_DOCUMENTATION.md",
        "submission/StudyRoute_Technical_Documentation.pdf",
        "Technical documentation",
        "System architecture, core algorithms and security design",
        False,
        technical_stats,
    ),
    Doc(
        "docs/SECURITY_SELF_ASSESSMENT.md",
        "submission/StudyRoute_Security_Self_Assessment.pdf",
        "Security self-assessment report",
        "Permission tiers and the known-risk list",
        True,
        security_stats,
    ),
    Doc(
        "submission/EXECUTION_EVIDENCE_SUMMARY.md",
        "submission/StudyRoute_Execution_Evidence_Summary.pdf",
        "Execution evidence",
        "What the sandbox logs and test runs show, and what they do not",
        False,
        evidence_stats,
    ),
)

CSS = """
@page { size: %(size)s; margin: 14mm 12mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: %(body)s; line-height: 1.42; color: #1b1f23; }
h1 { font-size: 20pt; margin: 0 0 5mm; }
h2 { font-size: 14pt; margin: 7mm 0 3mm; border-bottom: 1px solid #c8d1d9; padding-bottom: 1mm; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 5mm 0 2mm; page-break-after: avoid; }
h4 { font-size: 11pt; margin: 4mm 0 1mm; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%%; margin: 3mm 0; font-size: %(table)s; }
th, td { border: 1px solid #c8d1d9; padding: 1.1mm 1.8mm; vertical-align: top; text-align: left; overflow-wrap: break-word; }
th { background: #eef2f5; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; background: #f1f3f5; padding: 0 1mm; word-break: break-word; }
pre { background: #f1f3f5; padding: 2.5mm; white-space: pre-wrap; word-break: break-word; font-size: 8.3pt; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%%; height: auto; display: block; margin: 3mm auto; page-break-inside: avoid; }
blockquote { margin: 2mm 0; padding: 1mm 4mm; border-left: 3px solid #c8d1d9; color: #444; }
a { color: #0b5cad; text-decoration: none; }
.cover { height: %(cover_h)s; display: flex; flex-direction: column; justify-content: center; padding: 0 6mm; background: #0b2545; color: #fff; page-break-after: always; border-radius: 3mm; }
.cover .kicker { color: #f4b942; font-weight: 700; letter-spacing: 0.08em; font-size: 10pt; }
.cover h1 { font-family: Cambria, Georgia, serif; font-size: 48pt; margin: 4mm 0 2mm; color: #fff; }
.cover .doc { font-size: 22pt; font-weight: 600; margin: 0; }
.cover .sub { font-size: 12.5pt; color: #c9d6e3; margin: 2mm 0 10mm; }
.cover .stats { display: flex; gap: 6mm; margin-bottom: 12mm; }
.cover .stat { flex: 1; background: #12335f; border-radius: 2.5mm; padding: 5mm; }
.cover .num { font-family: Cambria, Georgia, serif; font-size: 22pt; font-weight: 700; color: #f4b942; }
.cover .what { font-size: 9.5pt; color: #dbe6f2; margin-top: 1.5mm; }
.cover .team { font-size: 11pt; margin: 0; }
.cover .small { font-size: 9pt; color: #c9d6e3; margin: 1.5mm 0 0; }
"""


def cover(doc: Doc) -> str:
    stats = "".join(
        f'<div class="stat"><div class="num">{num}</div><div class="what">{what}</div></div>'
        for num, what in doc.stats()
    )
    return (
        '<section class="cover">'
        "<div class=\"kicker\">FINTECHATHON 2026 &middot; INTERNATIONAL TRACK &middot; TOPIC C</div>"
        f"<h1>StudyRoute</h1><p class=\"doc\">{doc.title}</p><p class=\"sub\">{doc.subtitle}</p>"
        f'<div class="stats">{stats}</div>'
        f'<p class="team"><b>{TEAM}</b> &middot; {MEMBERS}</p>'
        f'<p class="small">{UNIVERSITY}</p><p class="small">{SANDBOX}</p>'
        "</section>"
    )


def html_page(doc: Doc, markdown_module: object) -> str:
    source = ROOT / doc.source
    body = markdown_module.markdown(  # type: ignore[attr-defined]
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )
    css = CSS % {
        "size": "A4 landscape" if doc.landscape else "A4",
        "body": "9.5pt" if doc.landscape else "10.5pt",
        "table": "8.3pt" if doc.landscape else "9pt",
        "cover_h": "180mm" if doc.landscape else "262mm",
    }
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>StudyRoute: {doc.title}</title>"
        f'<base href="{source.parent.as_uri()}/"><style>{css}</style></head>'
        f"<body>{cover(doc)}{body}</body></html>"
    )


def find_chrome() -> str:
    candidates = [os.environ.get("CHROME_PATH", ""), *USUAL_CHROME]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return found
    raise SystemExit("Google Chrome not found: set CHROME_PATH to its executable")


def main() -> int:
    try:
        import markdown
    except ImportError:
        print("Install the converter first: pip install markdown", file=sys.stderr)
        return 1
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as folder:
        for doc in DOCS:
            page = Path(folder) / (Path(doc.target).stem + ".html")
            page.write_text(html_page(doc, markdown), encoding="utf-8")
            target = ROOT / doc.target
            subprocess.run(  # noqa: S603
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--no-pdf-header-footer",
                    "--allow-file-access-from-files",
                    f"--print-to-pdf={target}",
                    page.as_uri(),
                ],
                check=True,
                capture_output=True,
            )
            print(f"wrote {doc.target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
