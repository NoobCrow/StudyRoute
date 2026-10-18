"""Install exact local ONNX artifacts from a GitHub Release, outside repo-import limits.

Only the artifact origin is configurable. Expected archive/file hashes come from the
committed manifest, never from a downloaded release or environment value.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

PREFIXES = (
    "backend/app/ai/nlu/model/",
    "backend/app/ai/explainer/model/",
    "submission/",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def destinations(root: Path, manifest: dict) -> dict[str, Path]:
    result = {}
    for name, expected in manifest["files"].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or not name.startswith(PREFIXES):
            raise RuntimeError("Unsafe model manifest path")
        target = root / name
        # Refuse existing symlinks at every path component.
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise RuntimeError("Model destination contains a symlink")
        if int(expected["size"]) < 0 or not re.fullmatch(
            r"[0-9a-f]{64}", expected["sha256"]
        ):
            raise RuntimeError("Invalid model manifest")
        result[name] = target
    if not result:
        raise RuntimeError("Empty model manifest")
    return result


def installed(root: Path, manifest: dict) -> bool:
    return all(
        path.is_file()
        and path.stat().st_size == manifest["files"][name]["size"]
        and sha256(path) == manifest["files"][name]["sha256"]
        for name, path in destinations(root, manifest).items()
    )


def install_archive(root: Path, archive: Path, manifest: dict) -> None:
    if (
        archive.stat().st_size != manifest["archive_size"]
        or sha256(archive) != manifest["archive_sha256"]
    ):
        raise RuntimeError("Model archive SHA-256/size check failed")
    targets = destinations(root, manifest)
    with ZipFile(archive) as source:
        infos = source.infolist()
        if len(infos) != len(targets) or {i.filename for i in infos} != set(targets):
            raise RuntimeError("Unexpected model archive entries")
        # Verify every entry before writing any model file.
        for info in infos:
            expected = manifest["files"][info.filename]
            if (
                info.file_size != expected["size"]
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise RuntimeError("Invalid model archive entry")
            digest = hashlib.sha256()
            with source.open(info) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                raise RuntimeError("Model file SHA-256 check failed")
        for info in infos:
            target = targets[info.filename]
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_name(target.name + ".pending")
            try:
                with source.open(info) as inp, pending.open("wb") as out:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                        out.write(chunk)
                os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)
    if not installed(root, manifest):
        raise RuntimeError("Installed model integrity check failed")


def download_archive(cache: Path, manifest: dict) -> None:
    import httpx

    repo = os.environ.get("MODEL_GITHUB_REPO") or manifest["repository"]
    tag = manifest["release_tag"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("MODEL_GITHUB_REPO must be owner/repository")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
        raise RuntimeError("Invalid model release tag")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("MODEL_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    temporary = cache.with_suffix(".partial")
    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(120.0, connect=30.0),
        ) as client:
            release = client.get(
                f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
            )
            if release.status_code != 200:
                raise RuntimeError(
                    f"Model release unavailable (HTTP {release.status_code}). Check repository, published release tag and private-repository token."
                )
            assets = [
                a
                for a in release.json().get("assets", [])
                if a.get("name") == manifest["asset_name"]
            ]
            if len(assets) != 1 or assets[0].get("size") != manifest["archive_size"]:
                raise RuntimeError(
                    "Expected model Release asset missing or size differs"
                )
            asset_id = int(assets[0]["id"])
            url = f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}"
            with client.stream(
                "GET", url, headers={"Accept": "application/octet-stream"}
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Model asset download failed (HTTP {response.status_code})"
                    )
                size = 0
                with temporary.open("wb") as out:
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > manifest["archive_size"]:
                            raise RuntimeError("Model download exceeds expected size")
                        out.write(chunk)
        if (
            temporary.stat().st_size != manifest["archive_size"]
            or sha256(temporary) != manifest["archive_sha256"]
        ):
            raise RuntimeError("Downloaded model archive SHA-256/size check failed")
        os.replace(temporary, cache)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_models(root: Path) -> None:
    manifest = json.loads((root / "deploy/botkeep/model-bundle.json").read_text())
    if installed(root, manifest):
        print("Local models: all committed hashes verified.", flush=True)
        return
    data = Path(os.environ.get("DATA_DIR") or str(root / "data")).resolve()
    cache_dir = data / "model-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / manifest["asset_name"]
    if not (
        cache.is_file()
        and cache.stat().st_size == manifest["archive_size"]
        and sha256(cache) == manifest["archive_sha256"]
    ):
        print(
            "Downloading local model Release asset; first startup may take time.",
            flush=True,
        )
        import httpx

        try:
            download_archive(cache, manifest)
        except (
            httpx.HTTPError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ):
            # Never print HTTP request objects/headers or private credentials.
            raise RuntimeError(
                "Local models not ready. Check published Release asset, MODEL_GITHUB_REPO, private MODEL_GITHUB_TOKEN and outbound network. No cloud-only fallback was started."
            ) from None
    install_archive(root, cache, manifest)
    print("Local models installed and SHA-256 verified.", flush=True)
