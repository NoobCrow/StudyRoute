"""Create a complete branch-ready ZIP, including the committed public frontend.

python scripts/make_botkeep_branch_zip.py
GitHub deployment uses these extracted files, NOT a ZIP file committed to GitHub.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".next",
    "out",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "playwright-report",
    "test-results",
    ".cache",
    ".tmp",
    "runs",
    ".shots",
}


def source_files():
    for directory, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP]
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(ROOT)
            if path.is_symlink():
                continue
            if "data" in relative.parts and relative.parts[:2] != ("ml", "data"):
                continue
            if (
                name == ".env"
                or (name.startswith(".env.") and name != ".env.example")
                or name == "dev_secrets.json"
                or name == "RELEASE_MANIFEST.sha256"
                or name.endswith(
                    (
                        ".pyc",
                        ".db",
                        ".db-wal",
                        ".db-shm",
                        ".sqlite",
                        ".sqlite3",
                        ".pem",
                        ".key",
                        ".p12",
                        ".pfx",
                        ".zip",
                        ".tsbuildinfo",
                    )
                )
            ):
                continue
            yield path


def main() -> None:
    import sys

    from prepare_botkeep import main as check_site
    from scan_repo import main as scan_source

    sys.argv = [sys.argv[0], "--check"]
    check_site()
    if scan_source() != 0:
        raise SystemExit("Refusing release: source scan failed.")
    target = ROOT / "dist" / "StudyRoute-botkeep-branch.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source_files()):
            relative = path.relative_to(ROOT).as_posix()
            archive.write(path, f"StudyRoute/{relative}")
            manifest.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}\n"
            )
        info = ZipInfo("StudyRoute/RELEASE_MANIFEST.sha256")
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, "".join(manifest))
    print(f"Created {target.name}: {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
