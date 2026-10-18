"""Conservative Botkeep GitHub-import checks (no dependencies required)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    "out",
    "dist",
    "test-results",
    "playwright-report",
}


def public_files():
    if (ROOT / ".git").exists():
        names = (
            subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
            .decode()
            .split("\0")
        )
        return sorted(ROOT / n for n in names if n and (ROOT / n).is_file())
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not SKIP.intersection(p.relative_to(ROOT).parts)
        and (
            "data" not in p.relative_to(ROOT).parts
            or p.relative_to(ROOT).parts[:2] == ("ml", "data")
        )
    )


def main():
    files = public_files()
    assert (ROOT / "main.py") in files, "main.py must be committed at repository root"
    assert len(files) <= 950, f"Too many files: {len(files)} (safety ceiling 950)"
    total = 0
    for path in files:
        name = path.name
        assert name != ".env" and not (
            name.startswith(".env.") and name != ".env.example"
        ), "Private environment file must not be committed"
        assert name != "dev_secrets.json" and path.suffix.lower() not in {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".pem",
            ".key",
            ".pfx",
            ".p12",
        }, "Private/runtime file must not be committed"
        size = path.stat().st_size
        assert size <= 3_800_000, (
            f"File exceeds safe per-file limit: {path.relative_to(ROOT)}"
        )
        total += size
    assert total <= 18_000_000, f"Repository exceeds safe total size: {total}"
    print(
        f"GitHub importer checks passed: {len(files)} files; {total:,} raw bytes; every file under 3.8 MB."
    )


if __name__ == "__main__":
    main()
