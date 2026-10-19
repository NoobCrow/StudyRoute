"""Read the demo video script (submission/VIDEO_SCRIPT.md) into scenes: when each starts, how long it runs, who is on screen
and the words to say. The recorder paces itself by these windows and the assembler builds the video, the captions and the
cue sheet from them, so the video can never drift from the script.

    python scripts/demo_video/script_scenes.py [out.json]      # writes the scenes, prints a summary
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "submission" / "VIDEO_SCRIPT.md"

ROW = re.compile(
    r'^\|\s*(\d+):(\d{2})\s*\|\s*\*\*(\d+)\.\s*([^*]+?)\*\*\s*\|(.*)\|\s*"(.*)"\s*\|\s*$'
)
TARGET = re.compile(r"\*\*Target length (\d+):(\d{2})\.")

# Who is on screen in each scene (window A parent, C reviewer, B student), taken from section 1 of the script.
ROLES = {
    0: "parent", 1: "parent", 2: "parent", 3: "parent", 4: "parent",
    5: "reviewer", 6: "parent", 7: "student", 8: "reviewer", 9: "reviewer",
}  # fmt: skip
ROLE_LABEL = {
    "parent": "PARENT  ·  Dhaka",
    "reviewer": "BANK REVIEWER  ·  the sandbox bank",
    "student": "STUDENT  ·  abroad",
}


@dataclass(frozen=True)
class Scene:
    number: int
    title: str
    start: int  # seconds from the start of the video
    window: int  # seconds until the next scene starts
    role: str
    on_screen: str  # the script's "what to do" column, for the cue sheet
    say: str

    @property
    def words(self) -> int:
        return len(self.say.split())


def parse(path: Path = SCRIPT) -> tuple[list[Scene], int]:
    """The scenes in order and the target length in seconds."""
    text = path.read_text(encoding="utf-8")
    target = TARGET.search(text)
    if not target:
        raise SystemExit("the script has no 'Target length m:ss' line")
    total = int(target.group(1)) * 60 + int(target.group(2))
    rows = [
        ROW.match(line)
        for line in text.splitlines()
        if re.match(r"^\|\s*\d+:\d{2}\s*\|", line)
    ]
    if not rows or any(r is None for r in rows):
        raise SystemExit(
            "a scene row of the script does not parse: check the tables in sections 3 and 4"
        )
    starts = [int(r.group(1)) * 60 + int(r.group(2)) for r in rows if r]
    ends = [*starts[1:], total]
    scenes = []
    for row, start, end in zip(rows, starts, ends, strict=True):
        assert row is not None
        number = int(row.group(3))
        scenes.append(
            Scene(
                number=number,
                title=row.group(4).strip(),
                start=start,
                window=end - start,
                role=ROLES[number],
                on_screen=re.sub(r"\s+", " ", row.group(5)).strip(" |"),
                say=re.sub(r"\s+", " ", row.group(6)).strip(),
            )
        )
    if [s.number for s in scenes] != list(range(len(scenes))):
        raise SystemExit("the scenes must be numbered 0, 1, 2, ... in order")
    return scenes, total


def main() -> int:
    scenes, total = parse()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "total": total,
                    "scenes": [asdict(s) | {"words": s.words} for s in scenes],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    print(f"{len(scenes)} scenes, {total} s ({total // 60}:{total % 60:02d})")
    for s in scenes:
        wpm = s.words / max(s.window - 1.6, 1) * 60
        print(
            f"  {s.number}  {s.start // 60}:{s.start % 60:02d}  {s.window:2d} s  {s.role:8s} {s.words:3d} words ({wpm:3.0f} wpm)  {s.title}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
