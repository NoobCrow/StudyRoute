#!/usr/bin/env python3
"""Build the demo videos, the captions and the narrator's cue sheet from the frames the recorder saved.

    python scripts/demo_video/assemble.py --frames dist/demo-video/frames --scenes dist/demo-video/scenes.json --out dist/demo-video

Writes into --out:
  StudyRoute_Demo_Video_SILENT.mp4    the picture only (1920 x 1080, 30 fps), exactly as long as the script: the voice-over goes on this
  StudyRoute_Demo_Video_GUIDE.mp4     the same picture with the script's words under it, lighting up as they fall due (for the narrator)
  StudyRoute_Demo_Video_captions.srt  the script's words timed to the scenes (subtitles for the final video; adjust to the real voice)
  NARRATOR_CUE_SHEET.md               per scene: time, who is on screen, what happens when, the words and the pace
  timeline.json                       where every scene and cue landed in the video

Every scene is cut to the length the script gives it (a scene that ran long is sped up a little, a short one holds its last picture),
so the voice-over can follow the script's time marks. The bar under the picture says who is on screen and that this is a sandbox.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

WIDTH, PICTURE, BAR, PANEL, FPS = 1920, 1020, 60, 200, 30
NAVY, PANEL_NAVY = "0B1220", "111C2E"
AMBER, WHITE, MUTED = "F4B942", "FFFFFF", "9FB0C8"
ROLE_COLOUR = {"parent": "2DD4BF", "reviewer": "A78BFA", "student": "38BDF8"}
ROLE_LABEL = {
    "parent": "PARENT  ·  Dhaka",
    "reviewer": "BANK REVIEWER  ·  the sandbox bank",
    "student": "STUDENT  ·  abroad",
}
FONT_FAMILY = "Segoe UI" if os.name == "nt" else "DejaVu Sans"
FONT_FILES = (
    ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
    if os.name == "nt"
    else [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
)
# Seconds: before the first word of a scene, after its last word, and how early a chunk of words appears.
LEAD_IN, LEAD_OUT, PREVIEW = 0.7, 1.0, 0.3


@dataclass
class Placed:
    number: int
    title: str
    role: str
    start: float
    window: float
    on_screen: str
    say: str
    real: float
    squeeze: float
    frames: list[tuple[str, float]]
    # What happens when: (seconds from the start of the video, text).
    marks: list[tuple[float, str]] = field(default_factory=list)


# --------------------------------------------------------------------------------------------------------------------
# Placing the recorded scenes on the script's timeline
# --------------------------------------------------------------------------------------------------------------------
def place(manifest: dict, scenes: list[dict]) -> list[Placed]:
    by_number = {s["number"]: s for s in scenes}
    placed: list[Placed] = []
    clock = 0.0
    for rec in sorted(manifest["scenes"], key=lambda r: r["number"]):
        sc = by_number[rec["number"]]
        if not rec["frames"]:
            raise SystemExit(
                f"scene {rec['number']} has no frames: this was a rehearsal (--dry). Record again without it."
            )
        if abs(sc["start"] - clock) > 0.01:
            raise SystemExit(
                f"scene {rec['number']} starts at {sc['start']} s but the scenes before it add up to {clock} s."
            )
        t0 = min(rec["started"], rec["frames"][0]["t"])
        real = rec["ended"] - t0
        window = float(sc["window"])
        squeeze = window / real if real > window else 1.0
        times = [f["t"] for f in rec["frames"]]
        times[0] = t0
        times.append(rec["ended"])
        frames: list[tuple[str, float]] = []
        for index, frame in enumerate(rec["frames"]):
            duration = (times[index + 1] - times[index]) * squeeze
            path = f"{rec['dir']}/{frame['file']}"
            if duration < 0.004 and frames:
                frames[-1] = (frames[-1][0], frames[-1][1] + duration)
            else:
                frames.append((path, duration))
        short = window - sum(d for _, d in frames)
        if short > 0:
            frames[-1] = (frames[-1][0], frames[-1][1] + short)
        marks = [
            (clock + max(0.0, (m["at"] - t0) * squeeze), m["label"])
            for m in rec.get("marks", [])
        ]
        placed.append(
            Placed(
                number=rec["number"],
                title=sc["title"],
                role=sc["role"],
                start=clock,
                window=window,
                on_screen=sc["on_screen"],
                say=sc["say"],
                real=real,
                squeeze=squeeze,
                frames=frames,
                marks=marks,
            )
        )
        clock += window
    return placed


def write_concat(placed: list[Placed], path: Path) -> float:
    """The frame list ffmpeg reads. Boundaries are rounded, not durations, so thousands of frames do not drift."""
    lines = ["ffconcat version 1.0"]
    elapsed, written, last = 0.0, 0.0, ""
    for scene in placed:
        for rel, duration in scene.frames:
            elapsed += duration
            step = round(elapsed, 4) - written
            written += step
            lines += [f"file '{rel}'", f"duration {step:.4f}"]
            last = rel
    # ffmpeg ignores the duration of the final entry, so the last frame is listed once more.
    lines.append(f"file '{last}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


# --------------------------------------------------------------------------------------------------------------------
# Words and their timing (the guide's lit-up text and the captions)
# --------------------------------------------------------------------------------------------------------------------
@dataclass
class Chunk:
    start: float  # when the first word falls due
    end: float  # when the last word is done
    shown_from: float
    shown_to: float
    words: list[tuple[str, float]]  # word, seconds it takes


def weight(word: str) -> float:
    base = len(re.sub(r"\W", "", word)) + 2.0
    if word.endswith((".", "?", "!")):
        return base + 5.0
    if word.endswith((",", ";", ":")):
        return base + 2.0
    return base


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def pack(text: str, limit: int = 235) -> list[list[str]]:
    """Whole sentences, joined while they fit under the limit, each as a list of words."""
    groups: list[str] = []
    for sentence in sentences(text):
        if groups and len(groups[-1]) + 1 + len(sentence) <= limit:
            groups[-1] += " " + sentence
        else:
            groups.append(sentence)
    return [g.split() for g in groups]


def chunks(scene: Placed) -> list[Chunk]:
    groups = pack(scene.say)
    usable = max(1.0, scene.window - LEAD_IN - LEAD_OUT)
    total = sum(weight(w) for g in groups for w in g)
    unit = usable / total
    clock = scene.start + LEAD_IN
    out: list[Chunk] = []
    for group in groups:
        words = [(w, weight(w) * unit) for w in group]
        end = clock + sum(d for _, d in words)
        out.append(Chunk(clock, end, 0.0, 0.0, words))
        clock = end
    for index, chunk in enumerate(out):
        chunk.shown_from = max(scene.start, chunk.start - PREVIEW)
        following = (
            out[index + 1].start - PREVIEW
            if index + 1 < len(out)
            else scene.start + scene.window
        )
        chunk.shown_to = max(chunk.end, following)
    return out


# --------------------------------------------------------------------------------------------------------------------
# ASS subtitles: the bar under the picture, the dips between windows and (guide only) the lit-up words
# --------------------------------------------------------------------------------------------------------------------
def colour(rgb: str) -> str:
    """An ASS colour (opaque): blue, green, red, in the order ASS wants."""
    return f"&H{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&"


def stamp(seconds: float) -> str:
    cs = round(max(0.0, seconds) * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def mmss(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def rect(x: float, y: float, w: float, h: float) -> str:
    return rf"{{\p1}}m 0 0 l {w:g} 0 {w:g} {h:g} 0 {h:g}{{\p0}}"


def disc(radius: float) -> str:
    k = 0.5523 * radius
    r = radius
    return (
        rf"{{\p1}}m {r:g} 0 b {r + k:g} 0 {2 * r:g} {r - k:g} {2 * r:g} {r:g} b {2 * r:g} {r + k:g} {r + k:g} {2 * r:g} {r:g} {2 * r:g} "
        rf"b {r - k:g} {2 * r:g} 0 {r + k:g} 0 {r:g} b 0 {r - k:g} {r - k:g} 0 {r:g} 0{{\p0}}"
    )


def event(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{stamp(start)},{stamp(end)},{style},,0,0,0,,{text}"


def header(height: int) -> str:
    def style(
        name: str,
        size: int,
        primary: str,
        secondary: str,
        bold: int,
        align: int,
        margin_v: int = 0,
    ) -> str:
        return (
            f"Style: {name},{FONT_FAMILY},{size},{colour(primary)},{colour(secondary)},&H00000000&,&H00000000&,{bold},0,0,0,"
            f"100,100,0,0,1,0,0,{align},60,60,{margin_v},1"
        )

    return "\n".join(
        [
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {height}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding"
            ),
            style("Bar", 29, WHITE, WHITE, 1, 4),
            style("Dim", 24, MUTED, MUTED, 0, 4),
            style("Say", 37, AMBER, WHITE, 0, 7, PICTURE + BAR + 62),
            "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )  # fmt: skip


def bar_events(placed: list[Placed], total: float) -> list[str]:
    top = PICTURE
    lines = [
        event(
            0,
            0,
            total,
            "Bar",
            rf"{{\an7\pos(0,{top})\1c{colour(NAVY)}\bord0\shad0}}"
            + rect(0, 0, WIDTH, BAR),
        )
    ]
    for scene in placed:
        end = scene.start + scene.window
        tint = colour(ROLE_COLOUR[scene.role])
        lines.append(
            event(
                1,
                scene.start,
                end,
                "Bar",
                rf"{{\an7\pos(0,{top})\1c{tint}\bord0\shad0}}" + rect(0, 0, WIDTH, 3),
            )
        )
        lines.append(
            event(
                1,
                scene.start,
                end,
                "Bar",
                rf"{{\an7\pos(46,{top + 19})\1c{tint}\bord0\shad0}}" + disc(11),
            )
        )
        lines.append(
            event(
                2,
                scene.start,
                end,
                "Bar",
                rf"{{\an4\pos(82,{top + 32})}}{ROLE_LABEL[scene.role]}",
            )
        )
        name = scene.title.split(": ", 1)[-1]
        name = name[:1].upper() + name[1:]
        lines.append(
            event(
                2,
                scene.start,
                end,
                "Dim",
                rf"{{\an5\pos(1180,{top + 32})}}Scene {scene.number}   ·   {name}",
            )
        )
        lines.append(
            event(
                2,
                scene.start,
                end,
                "Dim",
                rf"{{\an6\pos(1872,{top + 32})\1c{colour(AMBER)}}}SANDBOX  ·  synthetic data",
            )
        )
    return lines


def dip_events(placed: list[Placed], total: float, height: int) -> list[str]:
    black = rf"{{\an7\pos(0,0)\1c{colour('000000')}\bord0\shad0}}" + rect(
        0, 0, WIDTH, height
    )
    lines = [
        event(9, 0, 0.5, "Bar", rf"{{\fad(0,500)}}{black}"),
        event(9, total - 0.9, total, "Bar", rf"{{\fad(900,0)}}{black}"),
    ]
    for before, after in pairwise(placed):
        if (
            before.role != after.role
        ):  # a different window comes up: dip to black and back, like a cut between two screens
            lines.append(
                event(
                    9,
                    after.start - 0.22,
                    after.start + 0.22,
                    "Bar",
                    rf"{{\fad(220,220)}}{black}",
                )
            )
    return lines


def guide_events(placed: list[Placed], total: float) -> list[str]:
    panel = PICTURE + BAR
    lines = [
        event(
            0,
            0,
            total,
            "Bar",
            rf"{{\an7\pos(0,{panel})\1c{colour(PANEL_NAVY)}\bord0\shad0}}"
            + rect(0, 0, WIDTH, PANEL),
        )
    ]
    for scene in placed:
        end = scene.start + scene.window
        label = f"SCENE {scene.number}  ·  {mmss(scene.start)} to {mmss(end)}  ·  {scene.window} s  ·  {scene.title}"
        lines.append(
            event(2, scene.start, end, "Dim", rf"{{\an4\pos(60,{panel + 22})}}{label}")
        )
        lines.append(
            event(
                1,
                scene.start,
                end,
                "Bar",
                rf"{{\an7\pos(60,{panel + 42})\1c{colour('26364F')}\bord0\shad0}}"
                + rect(0, 0, 1800, 4),
            )
        )
        tint = colour(ROLE_COLOUR[scene.role])
        shrink = rf"{{\an7\pos(60,{panel + 42})\1c{tint}\bord0\shad0\t(0,{int(scene.window * 1000)},\fscx0.5)}}"
        lines.append(event(2, scene.start, end, "Bar", shrink + rect(0, 0, 1800, 4)))
        for chunk in chunks(scene):
            lead = round((chunk.start - chunk.shown_from) * 100)
            body = "".join(
                rf"{{\kf{max(1, round(d * 100))}}}{w} " for w, d in chunk.words
            ).rstrip()
            lines.append(
                event(
                    3,
                    chunk.shown_from,
                    chunk.shown_to,
                    "Say",
                    rf"{{\an7\k{lead}}}{body}",
                )
            )
    for second in range(int(total)):
        stamp_text = f"{mmss(second)} / {mmss(total)}"
        lines.append(
            event(
                2,
                second,
                second + 1,
                "Dim",
                rf"{{\an6\pos(1860,{panel + 22})}}{stamp_text}",
            )
        )
    return lines


def write_ass(path: Path, placed: list[Placed], total: float, guide: bool) -> None:
    height = PICTURE + BAR + (PANEL if guide else 0)
    events = (
        bar_events(placed, total)
        + (guide_events(placed, total) if guide else [])
        + dip_events(placed, total, height)
    )
    path.write_text(header(height) + "\n" + "\n".join(events) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------------------------------
# Captions and the cue sheet
# --------------------------------------------------------------------------------------------------------------------
def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path: Path, placed: list[Placed]) -> None:
    timed = [(chunk, scene) for scene in placed for chunk in chunks(scene)]
    cues: list[str] = []
    for index, (chunk, scene) in enumerate(timed):
        following = (
            timed[index + 1][0].start
            if index + 1 < len(timed)
            else scene.start + scene.window
        )
        end = min(chunk.end + 0.3, following - 0.02)
        text = " ".join(w for w, _ in chunk.words)
        cues.append(
            f"{index + 1}\n{srt_time(chunk.start)} --> {srt_time(end)}\n{text}\n"
        )
    path.write_text("\n".join(cues), encoding="utf-8")


def pace_note(words: int, window: float) -> str:
    wpm = words / max(window - LEAD_IN - LEAD_OUT, 1) * 60
    if wpm > 150:
        return f"{wpm:.0f} wpm: brisk, read steadily and do not pause"
    if wpm > 135:
        return f"{wpm:.0f} wpm: a little quick"
    return f"{wpm:.0f} wpm: comfortable"


def tenths(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def write_cue_sheet(
    path: Path, placed: list[Placed], total: float, names: dict[str, str]
) -> None:
    intro = (
        f"The picture is **{mmss(total)}** long (the limit is 5:00) and it is silent. Each scene is fixed to the script's "
        "time marks, so if you start each scene's words at the time shown, the voice and the picture line up."
    )
    how = [
        (
            f"1. Play **{names['guide']}** and read along. The words under the picture light up as they fall due; the thin "
            "bar above them shrinks to show how long the scene has left. Do one rehearsal first."
        ),
        (
            f"2. Record your voice while **{names['silent']}** plays (headphones on, so the speaker does not leak into the "
            "microphone), or record each scene separately and place it at the scene's start time."
        ),
        (
            "3. Join them with `python mix_voiceover.py your_voice.wav`, or in any editor: put the picture on one track, your "
            "voice on another, export MP4 (H.264) under 5:00."
        ),
        (
            "4. Name the result **StudyRoute_Demo_Video.mp4**. Say the numbers exactly as written; do not add claims that "
            "are not in the script."
        ),
    ]
    out = [
        "# StudyRoute demo video: narrator's cue sheet",
        "",
        intro,
        "",
        "## How to record the voice-over",
        "",
        *how,
        "",
    ]
    out += ["## The words, scene by scene", ""]
    for scene in placed:
        end = scene.start + scene.window
        words = len(scene.say.split())
        role = ROLE_LABEL[scene.role].replace("  ·  ", ", ")
        out += [
            f"### {scene.number}. {scene.title}  ({mmss(scene.start)} to {mmss(end)}, {scene.window:g} s)",
            "",
            f"- On screen: **{role}**",
            f"- Words: {words}. Pace: {pace_note(words, scene.window)}.",
        ]
        if scene.marks:
            out.append("- What happens when (so your words can land on it):")
            out += [f"  - {tenths(at)}  {label}" for at, label in scene.marks]
        out += ["", f"> {scene.say}", ""]
    closing = (
        "Scenes are fixed, not your voice. If a sentence runs a second or two over, finish it and begin the next scene's "
        "words on time; a scene's picture does not wait. If you are early, stop and let the picture finish. Do not speed up "
        "the video."
    )
    out += ["## If a scene runs short or long", "", closing]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------------------------------------------------
def find_ffmpeg(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if candidate:
            return candidate
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        raise SystemExit(
            "ffmpeg was not found: install it, or pass --ffmpeg PATH (or set FFMPEG)."
        ) from None


def stage_fonts(work: Path) -> str | None:
    fonts = work / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    kept = 0
    for name in FONT_FILES:
        if Path(name).exists():
            shutil.copy(name, fonts / Path(name).name)
            kept += 1
    return "fonts" if kept else None


def duration_of(ffmpeg: str, video: Path) -> float:
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    found = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not found:
        raise SystemExit(f"cannot read the length of {video}")
    return int(found.group(1)) * 3600 + int(found.group(2)) * 60 + float(found.group(3))


def render(
    ffmpeg: str,
    concat: Path,
    work: Path,
    ass_name: str,
    fonts: str | None,
    height: int,
    total: float,
    target: Path,
) -> None:
    subtitles = f"ass={ass_name}" + (f":fontsdir={fonts}" if fonts else "")
    chain = (
        f"fps={FPS},scale={WIDTH}:{PICTURE}:flags=lanczos:in_range=pc:out_range=tv:out_color_matrix=bt709,"
        f"pad={WIDTH}:{height}:0:0:color=0x{NAVY},format=yuv420p,{subtitles}"
    )
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-stats", "-stats_period", "15", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-vf", chain, "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-an",
        "-fps_mode", "cfr", "-r", str(FPS),
        "-movflags", "+faststart", str(target),
    ]  # fmt: skip
    print("+", target.name, flush=True)
    subprocess.run(cmd, cwd=work, check=True)


def print_timing(scenes: list[dict]) -> None:
    """When each sentence falls due in its scene: the times the recorder's at() cues are taken from."""
    for scene in scenes:
        parts = sentences(scene["say"])
        usable = max(1.0, scene["window"] - LEAD_IN - LEAD_OUT)
        total = sum(weight(w) for part in parts for w in part.split())
        clock = LEAD_IN
        print(f"scene {scene['number']} ({scene['window']} s): {scene['title']}")
        for part in parts:
            span = sum(weight(w) for w in part.split()) / total * usable
            print(f"  {clock:5.1f} to {clock + span:5.1f}  {part[:72]}")
            clock += span


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "dist" / "demo-video"
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=Path, default=root / "frames")
    parser.add_argument("--scenes", type=Path, default=root / "scenes.json")
    parser.add_argument("--out", type=Path, default=root)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--prefix", default="StudyRoute_Demo_Video")
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="write only the captions, the cue sheet and the timeline",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="print when each sentence falls due in its scene, then stop",
    )
    args = parser.parse_args()

    scenes = json.loads(args.scenes.read_text(encoding="utf-8"))
    if args.timing:
        print_timing(scenes["scenes"])
        return 0
    manifest = json.loads((args.frames / "manifest.json").read_text(encoding="utf-8"))
    placed = place(manifest, scenes["scenes"])
    total = float(scenes["total"])
    if abs(sum(p.window for p in placed) - total) > 0.01:
        raise SystemExit("the recorded scenes do not add up to the script's length")
    out, work = args.out.resolve(), args.out.resolve() / "work"
    work.mkdir(parents=True, exist_ok=True)
    names = {"silent": f"{args.prefix}_SILENT.mp4", "guide": f"{args.prefix}_GUIDE.mp4"}

    write_srt(out / f"{args.prefix}_captions.srt", placed)
    write_cue_sheet(out / "NARRATOR_CUE_SHEET.md", placed, total, names)
    (out / "timeline.json").write_text(
        json.dumps(
            [
                {
                    "scene": p.number, "title": p.title, "role": p.role, "start": p.start, "window": p.window, "recorded_s": round(p.real, 2),
                    "speed": round(p.squeeze, 3), "marks": [{"at": round(a, 2), "label": t} for a, t in p.marks],
                }
                for p in placed
            ],
            indent=1,
        ),
        encoding="utf-8",
    )  # fmt: skip
    for p in placed:
        note = f"  (sped up x{1 / p.squeeze:.2f})" if p.squeeze < 1 else ""
        print(f"scene {p.number}: recorded {p.real:5.1f} s -> {p.window:g} s{note}")
    if args.no_video:
        return 0

    ffmpeg = find_ffmpeg(args.ffmpeg)
    concat = args.frames.resolve() / "video.ffconcat"
    written = write_concat(placed, concat)
    print(f"{sum(len(p.frames) for p in placed)} frames, {written:.2f} s")
    fonts = stage_fonts(work)
    write_ass(work / "bar.ass", placed, total, guide=False)
    write_ass(work / "guide.ass", placed, total, guide=True)
    silent, guide = out / names["silent"], out / names["guide"]
    render(ffmpeg, concat, work, "bar.ass", fonts, PICTURE + BAR, total, silent)
    render(
        ffmpeg, concat, work, "guide.ass", fonts, PICTURE + BAR + PANEL, total, guide
    )
    for video in (silent, guide):
        length = duration_of(ffmpeg, video)
        print(f"{video.name}: {length:.2f} s, {video.stat().st_size / 1e6:.1f} MB")
        if not math.isclose(length, total, abs_tol=0.6):
            raise SystemExit(
                f"{video.name} is {length:.2f} s long, not the script's {total:g} s"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
