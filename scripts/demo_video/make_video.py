#!/usr/bin/env python3
"""Make the demo video in one command, from fresh synthetic data on this computer only.

    python scripts/demo_video/make_video.py                  # record the ten scenes, build the videos and the cue sheet
    python scripts/demo_video/make_video.py --dry            # rehearse: play every scene, save a screenshot of each, no video
    python scripts/demo_video/make_video.py --assemble-only  # build the videos again from the frames already recorded

Steps: (1) a new synthetic database, (2) the API and the built web UI on loopback ports, the UI served with the real
content-security policy, (3) record.mjs plays submission/VIDEO_SCRIPT.md in three browser sessions (parent, bank reviewer,
student), (4) assemble.py builds the silent video, the narrator's guide video, the captions and the cue sheet, (5) the servers stop.

Needs backend/.venv, `cd web && npm ci && npm run build`, Node 20 or later, Google Chrome and ffmpeg (scripts/demo_video/README.md).
Nothing here reaches the internet and no real data is used: it refuses to run against anything but 127.0.0.1.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Self

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT / "backend"
SERVER = ROOT / "scripts" / "security" / "prod_like_server.mjs"
# A cloud model would make the assistant's wording differ from take to take; the video uses the local trained models only.
CLOUD_SETTINGS = (
    "LLM_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "HF_TOKEN", "HF_SPACE_URL", "HF_SPACE_APP_SECRET",
    "ASSISTANT_CLOUD_ENABLED",
)  # fmt: skip


def venv_python() -> Path:
    path = (
        BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not path.exists():
        raise SystemExit(
            "backend/.venv is missing: create it first (README, 'Run it without Docker')."
        )
    return path


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def stop(proc: subprocess.Popen[bytes]) -> None:
    """End a server and the processes it started (the Windows venv launcher starts a second python)."""
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_ready(url: str, logs: Path, seconds: int = 120) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as reply:
                if reply.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"{url} did not answer within {seconds} s; see the logs in {logs}")


class Stack:
    """The API and the web UI, both on loopback, on a database made new for this take."""

    def __init__(self, work: Path, api_port: int, web_port: int) -> None:
        self.work, self.api_port, self.web_port = work, api_port, web_port
        self.procs: list[subprocess.Popen[bytes]] = []
        base = f"http://127.0.0.1:{web_port}"
        self.env = {k: v for k, v in os.environ.items() if k not in CLOUD_SETTINGS} | {
            "DATA_DIR": str(work / "data"),
            "WEBHOOK_BASE_URL": base,
            "CORS_ORIGINS": base,
            "RATE_LIMIT_ENABLED": "false",
            "PYTHONUNBUFFERED": "1",
        }

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"

    def _spawn(self, name: str, cmd: list[str], cwd: Path) -> None:
        log = (self.work / f"{name}.log").open("wb")
        self.procs.append(
            subprocess.Popen(
                cmd, cwd=cwd, env=self.env, stdout=log, stderr=subprocess.STDOUT
            )
        )

    def __enter__(self) -> Self:
        for port in (self.api_port, self.web_port):
            if port_in_use(port):
                raise SystemExit(
                    f"port {port} is already in use: stop that server (or pass other --api-port/--web-port)."
                )
        if not (ROOT / "web" / "out" / "index.html").exists():
            raise SystemExit(
                "web/out is missing: run `cd web && npm ci && npm run build` first."
            )
        node = shutil.which("node")
        if not node:
            raise SystemExit("Node is not installed (needed for the recorder).")
        shutil.rmtree(self.work / "data", ignore_errors=True)
        (self.work / "data").mkdir(parents=True)
        py = str(venv_python())
        subprocess.run(
            [py, "-m", "app.scripts.seed", "--reset"],
            cwd=BACKEND,
            env=self.env,
            check=True,
            capture_output=True,
        )
        api = [
            py,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.api_port),
        ]
        self._spawn("api", api, BACKEND)
        self._spawn(
            "web",
            [node, str(SERVER), str(self.web_port), str(self.api_port)],
            ROOT / "web",
        )
        wait_ready(f"{self.base}/api/v1/health", self.work)
        wait_ready(f"{self.base}/login/", self.work)
        return self

    def __exit__(self, *exc: object) -> None:
        for proc in reversed(self.procs):
            stop(proc)


def run(cmd: list[str], **kw: object) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)  # type: ignore[call-overload]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "demo-video")
    parser.add_argument("--api-port", type=int, default=8120)
    parser.add_argument("--web-port", type=int, default=8190)
    parser.add_argument(
        "--dry",
        action="store_true",
        help="rehearse every scene and save a screenshot of each",
    )
    parser.add_argument(
        "--only", help="with --dry, play just these scenes, for example 4,5,6,7"
    )
    parser.add_argument(
        "--assemble-only",
        action="store_true",
        help="build the videos from the frames already recorded",
    )
    parser.add_argument("--no-assemble", action="store_true", help="record only")
    args = parser.parse_args()
    out: Path = args.out.resolve()
    work, frames, scenes = out / "work", out / "frames", out / "scenes.json"
    work.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(HERE / "script_scenes.py"), str(scenes)])

    if not args.assemble_only:
        with Stack(work, args.api_port, args.web_port) as stack:
            record = [
                "node",
                str(HERE / "record.mjs"),
                "--base",
                stack.base,
                "--out",
                str(frames),
                "--scenes",
                str(scenes),
            ]
            run(
                [
                    *record,
                    "--python",
                    str(venv_python()),
                    *(["--dry"] if args.dry else []),
                    *(["--only", args.only] if args.only else []),
                ],
                cwd=ROOT,
            )
    if args.dry or args.no_assemble:
        print(
            f"Rehearsal screenshots are in {frames / 'dry'}"
            if args.dry
            else f"Frames are in {frames}"
        )
        return 0
    run(
        [
            sys.executable,
            str(HERE / "assemble.py"),
            "--frames",
            str(frames),
            "--scenes",
            str(scenes),
            "--out",
            str(out),
        ]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
