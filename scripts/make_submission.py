"""Build a clean source archive for the submission e-mail.

    python scripts/make_submission.py          # writes dist/studyroute-submission.zip

Refuses to run if the repository scan finds secrets, real e-mails, passport-like numbers or
TODOs. Contains only files git would track: nothing from .gitignore (.env, data/, node_modules,
databases, virtual environments) can end up in the archive. Text files are written with LF line
endings whatever the working tree has, because a shell script or nginx config with CRLF fails
inside a Linux container.
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
NUL = b"\x00"
CRLF = b"\r\n"
LF = b"\n"
MODE = 0o100644  # regular file, rw-r--r--


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


def archive_bytes(path: Path) -> bytes:
    """The file as it goes in the zip: text with CRLF turned into LF, binary files untouched."""
    data = path.read_bytes()
    if NUL in data:
        return data
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data.replace(CRLF, LF)


def member_info(path: Path) -> zipfile.ZipInfo:
    """Zip entry for a file, readable by everyone: a COPY into an image keeps the mode, and the
    container's non-root user must be able to read the app and the entrypoint."""
    info = zipfile.ZipInfo.from_file(path, f"{TOP}/{path.relative_to(ROOT).as_posix()}")
    info.external_attr = MODE << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def main(out: Path = OUT) -> int:
    hits = [hit for path in scan_repo.tracked_files() for hit in scan_repo.scan_file(path)]
    if hits:
        print("Refusing to build: the repository scan found problems:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    members = archive_members()
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.writestr(member_info(path), archive_bytes(path))
    size_kb = out.stat().st_size // 1024
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"Wrote {shown}: {len(members)} files, {size_kb} KB. Scan clean.")
    print("Unzip it somewhere else and run `docker compose up --build` once before sending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
