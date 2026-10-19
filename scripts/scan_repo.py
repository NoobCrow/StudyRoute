"""Scan the files git tracks for things that must never be committed or submitted.

    python scripts/scan_repo.py            # exit 1 when anything is found

Looks for private keys, API keys, JWTs, passport-like numbers, e-mail addresses on real
domains and TODO markers. Standard library only, so CI and judges can run it anywhere.
Synthetic data is expected: the .test domain and the documented example IBAN are allowed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_SUFFIXES = {".png", ".docx", ".ico", ".svg", ".lock", ".onnx", ".gz", ".pptx", ".mp4", ".webm"}
SKIP_FILES = {
    "scripts/scan_repo.py",  # defines the patterns
    "backend/tests/test_repo_scan.py",  # plants fake secrets to prove the scanner catches them
    "web/package-lock.json",
}
EMAIL_LABEL = "e-mail on a real domain"
# .test is a reserved TLD that can never receive mail, so synthetic addresses are fine.
ALLOWED_EMAIL_DOMAINS = (".test", "example.org", "example.com")

# Exact (file, rule) pairs that are deliberate: synthetic fixtures and documentation text.
ALLOWED: dict[str, set[str]] = {
    "backend/tests/test_ai_cloud.py": {"secret assigned a literal value"},  # synthetic test key
    "backend/tests/test_saved_ai_connection.py": {"secret assigned a literal value"},  # synthetic test key
    "CLAUDE.md": {"TODO marker"},  # the rule "no TODO left silently"
    "docs/BLUEPRINT.md": {"TODO marker", EMAIL_LABEL},  # organiser contact is public
    "docs/COMPETITION_RULES.md": {EMAIL_LABEL},  # the organiser's public contact, as printed in the rules
    "submission/CHECKLIST.md": {EMAIL_LABEL},  # the organiser's public registration address
    "submission/EMAIL_TEMPLATES.md": {EMAIL_LABEL},  # the organiser's public registration address
    "backend/tests/test_ai_llm_mode.py": {"passport-like number"},  # masking test input
    "backend/tests/test_ai_masking.py": {"passport-like number"},  # masking test input
    "backend/tests/test_api_validation.py": {"TODO marker"},  # "XXX" is an invalid charge code
    "backend/tests/test_engine_money.py": {"TODO marker"},  # "XXX" is the no-currency ISO code
    "backend/tests/test_api_send_plan.py": {"TODO marker"},  # "XXX" is an unsupported currency
    "backend/tests/test_security.py": {"JWT"},  # fake token used to test log redaction
}

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Anthropic or OpenAI style API key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "secret assigned a literal value",
        re.compile(
            r"(?i)\b(?:api[_-]?key|[a-z0-9_-]*secret|jwt[_-]?signing[_-]?key|encryption[_-]?key|passwd|password|token)\b[\"\']?\s*[=:]\s*[\"'][A-Za-z0-9+/_=-]{24,}[\"']"
        ),
    ),
    ("passport-like number", re.compile(r"(?i)\bpassport\b[^\n]{0,20}\b[A-Z]{1,2}\d{7,8}\b")),
    ("TODO marker", re.compile(r"\b(?:TODO|FIXME|XXX)\b")),
]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "data",
    ".pytest_cache", ".ruff_cache", "htmlcov", "coverage",
    ".next", "out", "test-results", "playwright-report", ".shots", ".cache",
}  # fmt: skip


GENERATED_FILES = {"next-env.d.ts", "security_headers.conf"}
VERSIONED_DATA = (("ml", "data"), ("backend", "tests", "data"))


def excluded(path: Path) -> bool:
    """Generated artifacts and dependency trees, never source, even if accidentally tracked."""
    relative = path.relative_to(ROOT)
    # ml/data (benchmarks) and backend/tests/data (explainer test questions) are versioned input,
    # unlike the runtime's data directory.
    parts = relative.parts
    ignored = any(part in IGNORED_DIRS - {"data"} for part in parts)
    versioned = any(parts[: len(kept)] == kept for kept in VERSIONED_DATA)
    runtime_data = "data" in parts and not versioned
    return (ignored or runtime_data or path.is_symlink() or path.name in GENERATED_FILES
            or path.name.endswith(".tsbuildinfo"))


def _walk() -> list[Path]:
    """Pruned fallback for source ZIPs: do not recurse into dependency/build trees.

    Private environment files are deliberately NOT ignored: scanning must fail if one is present.
    """
    found = []
    for base, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if not excluded(Path(base) / d)]
        found.extend(Path(base) / name for name in names if not excluded(Path(base) / name))
    return found


def tracked_files() -> list[Path]:
    """Files git tracks (plus new, unignored ones); the plain file tree when git is unavailable."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
            capture_output=True, check=True,
        ).stdout.decode().strip()
        if Path(top).resolve() != ROOT.resolve():
            return _walk()
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _walk()
    return [ROOT / name for name in out.split("\0") if name and not excluded(ROOT / name)]


def scan_text(relative: str, text: str) -> list[str]:
    """Return one message per finding in `text`, which is the content of file `relative`."""
    allowed = ALLOWED.get(relative, set())
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in RULES:
            if (pattern.search(line) and label not in allowed
                    and not (label == "secret assigned a literal value"
                             and re.search(r'"token"\s*:\s*"0x[0-9a-fA-F]{40}"', line))):
                hits.append(f"{relative}:{number}: {label}")
        for match in EMAIL.finditer(line):
            domain = match.group(1).lower()
            if EMAIL_LABEL not in allowed and not domain.endswith(ALLOWED_EMAIL_DOMAINS):
                hits.append(f"{relative}:{number}: {EMAIL_LABEL} ({domain})")
    return hits


def scan_file(path: Path) -> list[str]:
    relative = path.relative_to(ROOT).as_posix()
    if path.name == "dev_secrets.json" or path.name == ".env" or (
        path.name.startswith(".env.") and path.name != ".env.example"
    ) or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return [f"{relative}: private credential file"]
    if relative in SKIP_FILES or path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
        return []
    try:
        return scan_text(relative, path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, OSError):
        return []


def main() -> int:
    hits = [hit for path in tracked_files() for hit in scan_file(path)]
    if hits:
        print("Found items that must not be committed or submitted:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    print("Repository scan clean: no secrets, real e-mails, passport-like numbers or TODOs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
