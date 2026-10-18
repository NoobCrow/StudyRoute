"""Copy a freshly built frontend into the versioned Botkeep site directory.

npm ci --prefix web
npm run build --prefix web
python scripts/prepare_botkeep.py
python scripts/prepare_botkeep.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "deploy" / "botkeep" / "site"
MANIFEST = SITE.parent / "site-manifest.json"


def source_hash() -> str:
    digest = hashlib.sha256()
    excluded = {
        "node_modules",
        ".next",
        "out",
        "test-results",
        "playwright-report",
        ".shots",
    }
    generated = {"next-env.d.ts", "security_headers.conf"}
    for path in sorted((ROOT / "web").rglob("*")):
        rel = path.relative_to(ROOT / "web")
        if (
            not path.is_file()
            or path.is_symlink()
            or excluded.intersection(rel.parts)
            or path.name in generated
            or path.name.endswith(".tsbuildinfo")
        ):
            continue
        digest.update(rel.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def inventory() -> dict[str, str]:
    return {
        p.relative_to(SITE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(SITE.rglob("*"))
        if p.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if (
            manifest["source_sha256"] != source_hash()
            or manifest["files"] != inventory()
        ):
            raise SystemExit(
                "Botkeep site is stale or changed. Rebuild and prepare it again."
            )
        print(f"Botkeep site verified: {len(manifest['files'])} files.")
        return
    out = ROOT / "web" / "out"
    for required in (out / "login" / "index.html", out / "csp-hashes.json"):
        if not required.is_file():
            raise SystemExit(
                "Build web/ first: npm ci --prefix web && npm run build --prefix web"
            )
    staging = SITE.with_name("site.pending")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(out, staging, symlinks=False)
    if SITE.exists():
        shutil.rmtree(SITE)
    staging.rename(SITE)
    MANIFEST.write_text(
        json.dumps({"source_sha256": source_hash(), "files": inventory()}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Prepared {len(inventory())} public frontend files. Commit deploy/botkeep/.")


if __name__ == "__main__":
    main()
