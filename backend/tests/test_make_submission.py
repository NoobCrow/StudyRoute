"""scripts/make_submission.py: the archive a judge unzips must build in a Linux container."""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "make_submission", ROOT / "scripts" / "make_submission.py"
)
assert spec and spec.loader
make_submission = importlib.util.module_from_spec(spec)
sys.modules["make_submission"] = make_submission
spec.loader.exec_module(make_submission)

DOCKER_FILES = (
    "backend/Dockerfile",
    "backend/docker-entrypoint.sh",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "frontend/security_headers.conf",
    "docker-compose.yml",
    ".dockerignore",
)
CR = b"\r"


def test_crlf_text_is_written_with_lf(tmp_path: Path) -> None:
    source = tmp_path / "script.sh"
    source.write_bytes(b"set -eu\r\nexec uvicorn\r\n")
    assert make_submission.archive_bytes(source) == b"set -eu\nexec uvicorn\n"


def test_binary_and_non_utf8_files_are_left_alone(tmp_path: Path) -> None:
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\r\n")
    latin = tmp_path / "old.txt"
    latin.write_bytes(b"caf\xe9\r\n")
    assert make_submission.archive_bytes(png) == png.read_bytes()
    assert make_submission.archive_bytes(latin) == latin.read_bytes()


@pytest.fixture(scope="module")
def archive(tmp_path_factory: pytest.TempPathFactory) -> Iterator[zipfile.ZipFile]:
    out = tmp_path_factory.mktemp("submission") / "studyroute.zip"
    assert make_submission.main(out) == 0
    with zipfile.ZipFile(out) as built:
        yield built


def test_the_docker_files_are_in_the_archive_without_carriage_returns(
    archive: zipfile.ZipFile,
) -> None:
    for name in DOCKER_FILES:
        data = archive.read(f"studyroute/{name}")
        assert data and CR not in data, name


def test_every_member_is_readable_by_the_container_user(archive: zipfile.ZipFile) -> None:
    unreadable = [
        info.filename for info in archive.infolist() if (info.external_attr >> 16) & 0o444 != 0o444
    ]
    assert unreadable == []


def test_no_text_file_in_the_archive_has_windows_line_endings(archive: zipfile.ZipFile) -> None:
    offenders = []
    for info in archive.infolist():
        data = archive.read(info)
        if b"\x00" in data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if CR + b"\n" in data:
            offenders.append(info.filename)
    assert offenders == []
