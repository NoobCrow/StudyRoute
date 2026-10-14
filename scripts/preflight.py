"""Are we ready to submit? One command that separates what is broken from what only you can do.

    python scripts/preflight.py             # exit 1 only if something in the repository is broken
    python scripts/preflight.py --strict    # also exit 1 while any OPEN item remains

Each line is one of:
    OK      checked and fine
    FAIL    something in the repository is broken: fix it before submitting
    OPEN    needs a person (team, registration, GitHub, video, Docker): the script cannot do it
    INFO    for your information

It reads files and runs `git`; it changes nothing and sends nothing. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_repo

ROOT = scan_repo.ROOT
BEIJING = timezone(timedelta(hours=8))
DHAKA = timezone(timedelta(hours=6))
DEADLINE = datetime(2026, 10, 20, 23, 59, tzinfo=BEIJING)
INTERNAL_TARGET = datetime(2026, 10, 19, 20, 0, tzinfo=DHAKA)
OK, FAIL, OPEN, INFO = "OK", "FAIL", "OPEN", "INFO"

DELIVERABLES = {
    "01 technical documentation": "docs/TECHNICAL_DOCUMENTATION.md",
    "02 presentation deck": "submission/StudyRoute_Deck.pptx",
    "03 demo video script": "submission/VIDEO_SCRIPT.md",
    "04 README": "README.md",
    "04 test cases": "docs/TEST_CASES.md",
    "05 security self-assessment": "docs/SECURITY_SELF_ASSESSMENT.md",
    "06 execution evidence": "submission/evidence/sandbox_operation_log.txt",
}
PLACEHOLDER_FILES = (
    "submission/PROJECT_DESCRIPTION.md",
    "submission/DECK_OUTLINE.md",
    "submission/EMAIL_TEMPLATES.md",
)
# What `scripts/personalize.py` fills in. Anything else in square brackets is for you at send time.
PLACEHOLDERS = ("[Team name]", "[team name]", "[repository link]", "[names and universities]")
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def deadline_check(now: datetime) -> Check:
    left = DEADLINE - now
    if left.total_seconds() <= 0:
        return Check(FAIL, "deadline", "The deadline (20 Oct 2026 23:59 Beijing) has passed.")
    days, rest = divmod(int(left.total_seconds()), 86400)
    hours = rest // 3600
    target_left = INTERNAL_TARGET - now
    target = (
        f"internal target (19 Oct evening, Dhaka) is in "
        f"{int(target_left.total_seconds() // 3600)} h"
        if target_left.total_seconds() > 0
        else "the internal target (19 Oct evening, Dhaka) has passed: submit now"
    )
    return Check(
        INFO,
        "deadline",
        f"{days} days {hours} h left until 20 Oct 2026 23:59 Beijing (21:59 Dhaka); {target}.",
    )


def scan_check(root: Path) -> Check:
    hits = [hit for path in scan_repo.tracked_files() for hit in scan_repo.scan_file(path)]
    if hits:
        return Check(FAIL, "secret scan", f"{len(hits)} finding(s), first: {hits[0]}")
    return Check(OK, "secret scan", "no secrets, real e-mails, passport-like numbers or TODOs")


def deliverable_checks(root: Path) -> list[Check]:
    found = []
    for name, relative in DELIVERABLES.items():
        path = root / relative
        if path.is_file() and path.stat().st_size > 100:
            found.append(Check(OK, f"deliverable {name}", relative))
        else:
            found.append(Check(FAIL, f"deliverable {name}", f"{relative} is missing or empty"))
    return found


def evidence_check(root: Path) -> Check:
    folder = root / "submission" / "evidence"
    try:
        verify = json.loads((folder / "audit_verify.json").read_text(encoding="utf-8"))
        log = (folder / "sandbox_operation_log.txt").read_text(encoding="utf-8")
        bank = json.loads((folder / "bank_network.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return Check(FAIL, "execution evidence", f"cannot read the evidence files: {error}")
    failed = [line for line in log.splitlines() if line.strip().startswith("FAIL")]
    problems = []
    if verify.get("status") != "PASS":
        problems.append("the audit chain does not verify")
    if failed:
        problems.append(f"{len(failed)} failed demo check(s)")
    if not bank.get("network", {}).get("all_ok"):
        problems.append("the bank ledger does not balance")
    if problems:
        return Check(FAIL, "execution evidence", "; ".join(problems))
    return Check(OK, "execution evidence", "demo passed, audit chain PASS, bank books balance")


def deck_text(path: Path) -> str:
    """All text on the slides and in the speaker notes."""
    with zipfile.ZipFile(path) as archive:
        parts = [
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if re.match(r"ppt/(slides/slide|notesSlides/notesSlide)\d+\.xml$", name)
        ]
    return " ".join(re.findall(r"<a:t>([^<]*)</a:t>", "".join(parts)))


def deck_check(root: Path) -> Check:
    path = root / "submission" / "StudyRoute_Deck.pptx"
    try:
        with zipfile.ZipFile(path) as archive:
            slides = [n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
            notes = [
                n
                for n in archive.namelist()
                if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)
            ]
    except (OSError, zipfile.BadZipFile) as error:
        return Check(FAIL, "deck", f"not a readable .pptx: {error}")
    if len(slides) != 11 or len(notes) != 11:
        return Check(
            FAIL, "deck", f"{len(slides)} slides and {len(notes)} notes, expected 11 and 11"
        )
    return Check(OK, "deck", "11 slides with speaker notes (about 8.5 minutes of speech)")


def find_placeholders(root: Path) -> dict[str, list[str]]:
    """Placeholder -> files that still contain it, in the documents and the deck."""
    found: dict[str, list[str]] = {}
    for relative in PLACEHOLDER_FILES:
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        for placeholder in PLACEHOLDERS:
            if placeholder in text:
                found.setdefault(placeholder, []).append(relative)
    deck = root / "submission" / "StudyRoute_Deck.pptx"
    if deck.is_file():
        text = deck_text(deck)
        for placeholder in PLACEHOLDERS:
            if placeholder in text:
                found.setdefault(placeholder, []).append("submission/StudyRoute_Deck.pptx")
    return found


def placeholder_check(root: Path) -> Check:
    found = find_placeholders(root)
    if not found:
        return Check(OK, "team name and repository link", "filled in everywhere")
    where = "; ".join(f"{p} in {len(files)} file(s)" for p, files in sorted(found.items()))
    return Check(
        OPEN,
        "team name and repository link",
        f'{where}. Run: python scripts/personalize.py --team "..." --repo "https://github.com/..."',
    )


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def git_checks(root: Path) -> list[Check]:
    checks = []
    remote = _git(root, "remote", "get-url", "origin")
    if not remote:
        checks.append(
            Check(
                OPEN,
                "GitHub repository",
                "no remote yet: create the repository, then "
                "git remote add origin ... and git push -u origin main",
            )
        )
    else:
        status = _git(root, "status", "-sb") or ""
        ahead = re.search(r"ahead (\d+)", status)
        if ahead:
            checks.append(
                Check(
                    OPEN, "GitHub repository", f"{ahead.group(1)} commit(s) not pushed to {remote}"
                )
            )
        else:
            checks.append(Check(OK, "GitHub repository", f"pushed to {remote}"))
    dirty = _git(root, "status", "--porcelain")
    if dirty:
        checks.append(
            Check(
                OPEN,
                "committed",
                f"{len(dirty.splitlines())} uncommitted change(s): "
                "commit before building the archive",
            )
        )
    elif dirty == "":
        checks.append(Check(OK, "committed", "the working tree is clean"))
    tag = _git(root, "describe", "--tags", "--exact-match")
    checks.append(
        Check(OK, "release tag", f"HEAD is tagged {tag}")
        if tag
        else Check(
            OPEN, "release tag", "tag the commit you submit, for example: git tag submission-1"
        )
    )
    return checks


def docker_check() -> Check:
    if shutil.which("docker"):
        return Check(
            OK,
            "Docker",
            "found; run `docker compose up --build` once from a clean clone, "
            "then `python scripts/docker_smoke.py`",
        )
    return Check(
        OPEN,
        "Docker",
        "not installed on this machine. The stack was run for real in a Linux VM (docs/DOCKER.md); "
        "to repeat it here install Docker Desktop (Windows needs WSL 2), then run "
        "`docker compose up --build` and `python scripts/docker_smoke.py`",
    )


def video_check(root: Path) -> Check:
    videos = [p for p in (root / "submission").rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES]
    if videos:
        return Check(OK, "demo video", ", ".join(p.name for p in videos))
    return Check(
        OPEN,
        "demo video",
        "record it (under 5 minutes) from submission/VIDEO_SCRIPT.md; "
        "the evidence rule asks for it",
    )


def archive_check(root: Path) -> Check:
    archive = root / "dist" / "studyroute-submission.zip"
    if not archive.is_file():
        return Check(OPEN, "submission archive", "build it with: python scripts/make_submission.py")
    stamp = _git(root, "log", "-1", "--format=%ct")
    if stamp and archive.stat().st_mtime < int(stamp):
        return Check(
            OPEN,
            "submission archive",
            "older than the last commit: rebuild with python scripts/make_submission.py",
        )
    return Check(
        OK,
        "submission archive",
        f"dist/studyroute-submission.zip ({archive.stat().st_size // 1024} KB)",
    )


def manual_checks() -> list[Check]:
    return [
        Check(
            OPEN,
            "team",
            "2 to 5 full-time students outside Mainland China, Hong Kong, Macao and Taiwan, "
            "at least 60% non-Chinese. A one-person entry is not allowed",
        ),
        Check(
            OPEN,
            "registration",
            "send the form and each member's passport page to the organiser "
            "(never put passports in the repository)",
        ),
        Check(
            OPEN,
            "submission e-mail",
            "send the six items in one English e-mail before the deadline "
            "(draft: submission/EMAIL_TEMPLATES.md)",
        ),
    ]


def run_checks(root: Path = ROOT, now: datetime | None = None) -> list[Check]:
    moment = now or datetime.now(UTC)
    return [
        deadline_check(moment),
        scan_check(root),
        *deliverable_checks(root),
        evidence_check(root),
        deck_check(root),
        placeholder_check(root),
        *git_checks(root),
        docker_check(),
        video_check(root),
        archive_check(root),
        *manual_checks(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 while any OPEN is open")
    args = parser.parse_args(argv)
    checks = run_checks()
    for check in checks:
        print(f"[{check.status:<4}] {check.name}: {check.detail}")
    count = {s: sum(1 for c in checks if c.status == s) for s in (OK, FAIL, OPEN, INFO)}
    print(f"\n{count[OK]} OK, {count[FAIL]} FAIL, {count[OPEN]} OPEN (needs you).")
    if count[FAIL]:
        print("Fix every FAIL first: something in the repository is broken.", file=sys.stderr)
        return 1
    if count[OPEN] and args.strict:
        print("Open items need a person. See the OPEN lines above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
