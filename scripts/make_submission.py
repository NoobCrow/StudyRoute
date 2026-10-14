"""Build a clean source archive for the submission e-mail.

    python scripts/make_submission.py          # writes dist/studyroute-submission.zip

Refuses to run if the repository scan finds secrets, real e-mails, passport-like numbers or
TODOs. Contains only files git would track: nothing from .gitignore (.env, data/, node_modules,
databases, virtual environments) can end up in the archive.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_repo

ROOT = scan_repo.ROOT
OUT = ROOT / "dist" / "studyroute-submission.zip"
TOP = "studyroute"
NEVER = (".env", "dev_secrets.json")


def archive_members() -> list[Path]:
    files = []
    for path in scan_repo.tracked_files():
        relative = path.relative_to(ROOT)
        if not path.is_file() or relative.parts[0] == "dist":
            continue
        if path.name in NEVER or path.suffix in {".db", ".pem", ".key"}:
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    hits = [hit for path in scan_repo.tracked_files() for hit in scan_repo.scan_file(path)]
    if hits:
        print("Refusing to build: the repository scan found problems:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    members = archive_members()
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, f"{TOP}/{path.relative_to(ROOT).as_posix()}")
    size_kb = OUT.stat().st_size // 1024
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(members)} files, {size_kb} KB. Scan clean.")
    print("Unzip it somewhere else and run `docker compose up --build` once before sending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
