r"""Put your team name and repository link into the submission documents and the deck.

    python scripts/personalize.py --team "Team Alpha" \
        --repo "https://github.com/alpha/studyroute"
    python scripts/personalize.py --team "Team Alpha" \
        --repo "https://github.com/alpha/studyroute" \
        --members "A. Rahman (University X), B. Khan (University Y)"

It replaces the placeholders [Team name], [repository link] and (with --members)
[names and universities] in submission/PROJECT_DESCRIPTION.md, DECK_OUTLINE.md and
EMAIL_TEMPLATES.md, then rebuilds submission/StudyRoute_Deck.pptx with the same values. It never
touches git, the network or an e-mail address. Run it once; to change a value later edit the files
or `git checkout -- submission` and run it again. Check with `python scripts/preflight.py`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "submission/PROJECT_DESCRIPTION.md",
    "submission/DECK_OUTLINE.md",
    "submission/EMAIL_TEMPLATES.md",
)
TEAM_PLACEHOLDERS = ("[Team name]", "[team name]")
REPO_PLACEHOLDER = "[repository link]"
MEMBERS_PLACEHOLDER = "[names and universities]"
REPO_PATTERN = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~/-]+$")


class PersonalizeError(ValueError):
    """A value that cannot safely go into the documents."""


def check_text(label: str, value: str, *, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        raise PersonalizeError(f"{label} must be 1 to {max_length} characters.")
    if any(ch in cleaned for ch in "[]\n\r\t|`") or any(ord(ch) < 32 for ch in cleaned):
        raise PersonalizeError(f"{label} cannot contain brackets, pipes, backticks or line breaks.")
    return cleaned


def check_repo(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not REPO_PATTERN.fullmatch(cleaned):
        raise PersonalizeError(
            "The repository link must be an https:// address, for example https://github.com/you/studyroute"
        )
    return cleaned


def apply(root: Path, team: str, repo: str, members: str | None) -> dict[str, int]:
    """Replace the placeholders in the documents. Returns how many were replaced per file."""
    counts: dict[str, int] = {}
    for relative in FILES:
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        replaced = 0
        for placeholder in TEAM_PLACEHOLDERS:
            replaced += text.count(placeholder)
            text = text.replace(placeholder, team)
        replaced += text.count(REPO_PLACEHOLDER)
        text = text.replace(REPO_PLACEHOLDER, repo)
        if members:
            replaced += text.count(MEMBERS_PLACEHOLDER)
            text = text.replace(MEMBERS_PLACEHOLDER, members)
        if replaced:
            path.write_text(text, encoding="utf-8", newline="\n")
        counts[relative] = replaced
    return counts


def rebuild_deck(root: Path, team: str, repo: str) -> bool:
    deck = root / "submission" / "deck"
    env = {**os.environ, "TEAM_NAME": team, "REPO_LINK": repo}
    try:
        subprocess.run(["node", "build_deck.js"], cwd=deck, env=env, check=True)  # noqa: S607
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--team", required=True, help="your team name")
    parser.add_argument("--repo", required=True, help="the https address of your GitHub repository")
    parser.add_argument(
        "--members", help='for example "A. Rahman (University X), B. Khan (University Y)"'
    )
    parser.add_argument("--no-deck", action="store_true", help="only edit the documents")
    args = parser.parse_args(argv)
    try:
        team = check_text("The team name", args.team, max_length=80)
        repo = check_repo(args.repo)
        members = (
            check_text("The member list", args.members, max_length=300) if args.members else None
        )
    except PersonalizeError as error:
        print(f"Not changed: {error}", file=sys.stderr)
        return 2
    counts = apply(ROOT, team, repo, members)
    for relative, count in counts.items():
        print(f"  {relative}: {count} placeholder(s) replaced")
    if not args.no_deck:
        if rebuild_deck(ROOT, team, repo):
            print("  submission/StudyRoute_Deck.pptx rebuilt with your team name and link")
        else:
            print(
                "  The deck was NOT rebuilt (is Node installed?). Run in submission/deck:\n"
                '  TEAM_NAME="..." REPO_LINK="..." node build_deck.js',
                file=sys.stderr,
            )
            return 1
    print("Done. Check with: python scripts/preflight.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
