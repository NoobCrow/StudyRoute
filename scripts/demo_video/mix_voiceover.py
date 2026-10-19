#!/usr/bin/env python3
"""Put a recorded voice on the silent demo video and write the final MP4. Needs ffmpeg and nothing else.

    python mix_voiceover.py my_voice.wav
        one recording of the whole narration, starting at 0:00

    python mix_voiceover.py scene0.wav@0 scene1.wav@20 scene2.wav@30 scene3.wav@60 ...
        one recording per scene, each placed at the second the scene starts (the cue sheet lists them)

The voice is levelled (about -16 LUFS, a common level for web video), converted to AAC, and the file ends exactly with the picture.
Options: --video PATH (default: the SILENT video next to this script), --out PATH (default: StudyRoute_Demo_Video.mp4 next to it),
--captions PATH.srt (add the captions as a switch-on/off subtitle track), --ffmpeg PATH.
The result must stay under 5:00; the script refuses to write a longer one.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT_SECONDS = 300.0


def find_ffmpeg(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if candidate:
            return candidate
    raise SystemExit(
        "ffmpeg was not found: install it (https://ffmpeg.org), or pass --ffmpeg PATH."
    )


def length_of(ffmpeg: str, path: Path) -> float:
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    found = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not found:
        raise SystemExit(f"cannot read the length of {path}")
    return int(found.group(1)) * 3600 + int(found.group(2)) * 60 + float(found.group(3))


def parse_voice(item: str) -> tuple[Path, float]:
    name, at, start = item.rpartition("@")
    if at and re.fullmatch(r"\d+(\.\d+)?", start):
        return Path(name), float(start)
    return Path(item), 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "voice",
        nargs="+",
        help="voice file, or file@seconds for one recording per scene",
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=next(iter(sorted(HERE.glob("*SILENT*.mp4"))), HERE / "silent.mp4"),
    )
    parser.add_argument("--out", type=Path, default=HERE / "StudyRoute_Demo_Video.mp4")
    parser.add_argument("--captions", type=Path)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    voices = [parse_voice(v) for v in args.voice]
    for path, _ in voices:
        if not path.exists():
            raise SystemExit(f"voice file not found: {path}")
    if not args.video.exists():
        raise SystemExit(f"video not found: {args.video}")
    total = length_of(ffmpeg, args.video)
    if total > LIMIT_SECONDS:
        raise SystemExit(f"the picture is {total:.0f} s, over the 5:00 limit")

    inputs = ["-i", str(args.video)]
    for path, _ in voices:
        inputs += ["-i", str(path)]
    parts = [
        f"[{i + 1}:a]aresample=48000,adelay={int(start * 1000)}:all=1[v{i}]"
        for i, (_, start) in enumerate(voices)
    ]
    if len(voices) == 1:
        mixed = "[v0]"
    else:
        parts.append(
            "".join(f"[v{i}]" for i in range(len(voices)))
            + f"amix=inputs={len(voices)}:normalize=0[mix]"
        )
        mixed = "[mix]"
    parts.append(
        f"{mixed}loudnorm=I=-16:TP=-1.5:LRA=11,apad,aformat=channel_layouts=stereo[a]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-stats_period",
        "15",
        *inputs,
    ]
    if args.captions:
        cmd += ["-i", str(args.captions)]
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]"]
    if args.captions:
        cmd += [
            "-map",
            f"{len(voices) + 1}:0",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
        ]
    cmd += [
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        str(args.out),
    ]
    subprocess.run(cmd, check=True)
    final = length_of(ffmpeg, args.out)
    print(
        f"{args.out.name}: {final:.1f} s ({int(final // 60)}:{int(final % 60):02d}), {args.out.stat().st_size / 1e6:.1f} MB"
    )
    return 0 if final <= LIMIT_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
